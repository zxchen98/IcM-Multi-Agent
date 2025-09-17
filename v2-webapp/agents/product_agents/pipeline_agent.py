import os
import re
from typing import Literal
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from langgraph.types import Command
from langgraph.graph import StateGraph, MessagesState, START, END
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import BaseModel

# Import Kusto query tool and TSG vector store
from tools.kusto_query_tool import kusto_tool
from tools.tsg_vector_store_tool import search_tsg_for_ticket

# Import streaming callbacks
from streaming.callbacks import get_current_callbacks

# Load environment variables
load_dotenv()

# Initialize Azure OpenAI model
model = AzureChatOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
)

def generate_tsg_report(incident_details: dict, best_tsg: dict) -> str:
    """
    Generate comprehensive TSG report from incident details and matched TSG
    
    Args:
        incident_details: Incident information from Kusto
        best_tsg: Best matching TSG from vector search
        
    Returns:
        str: Formatted TSG report
    """
    similarity_percent = best_tsg.get('similarity', 0) * 100
    
    report = f"""
🎫 **PIPELINE INCIDENT TSG ANALYSIS REPORT**
================================================

📋 **Incident Information:**
- Incident ID: {incident_details.get('IncidentId', 'Unknown')}
- Title: {incident_details.get('Title', 'Unknown')}
- Severity: {incident_details.get('Severity', 'Unknown')}
- Summary: {incident_details.get('Summary', 'No summary available')[:300]}...

🔍 **TSG Vector Search Results:**
- **Best Match:** {best_tsg.get('title', 'Unknown TSG')}
- **Similarity Score:** {similarity_percent:.1f}%
- **TSG Path:** {best_tsg.get('path', 'Unknown path')}

📖 **TSG Overview:**
{best_tsg.get('overview', 'No overview available')}

💡 **Recommended Solution:**
{best_tsg.get('solution', 'No solution content available')}

🎯 **Next Steps:**
Based on the TSG match with {similarity_percent:.1f}% confidence:
- Review the recommended solution above
- Follow the TSG procedures if similarity > 70%
- Consider manual investigation if similarity < 70%
- Escalate to appropriate team if needed

================================================
"""
    
    return report

async def pipeline_supervisor_with_streaming(state: MessagesState) -> Command[Literal["step_start_failure_agent", "others_agent", END]]:
    """
    Pipeline Agent: Routes pipeline incidents to specialized agents based on Kusto queries
    """
    callbacks = get_current_callbacks()
    
    # Extract incident ID from messages
    incident_id = None
    
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            incident_id = kusto_tool.extract_incident_id(msg.content)
            break
        elif isinstance(msg, AIMessage) and "Incident ID:" in msg.content:
            match = re.search(r'Incident ID: (\w+)', msg.content)
            if match:
                incident_id = match.group(1)
    
    if callbacks:
        await callbacks.on_agent_start("Pipeline Agent", f"Processing pipeline incident {incident_id}")
    
    print("\n\n")
    print("=" * 60)
    print(f"🔧 Pipeline Agent: Processing incident {incident_id}")
    
    # First check TSG vector store for immediate solutions
    print("🔍 Pipeline Agent: Checking TSG vector store...")
    if incident_id:
        # Get incident details for TSG search
        incident_details = await kusto_tool.query_incident_details(incident_id)
        if incident_details and incident_details.get('Title') != 'Unknown':
            # Search TSG vector store
            title = incident_details.get('Title', '')
            summary = incident_details.get('Summary', '')
            best_tsg = await search_tsg_for_ticket(title, summary)
            
            if best_tsg and best_tsg.get('similarity', 0) > 0.7:  # High confidence TSG match
                print("✅ Pipeline Agent: Found high-confidence TSG match, returning TSG report")
                tsg_report = generate_tsg_report(incident_details, best_tsg)
                
                if callbacks:
                    await callbacks.on_agent_end("Pipeline Agent", "TSG solution found and provided")
                
                return Command(
                    goto=END,
                    update={"messages": [AIMessage(content=tsg_report)]}
                )
            elif best_tsg:
                print(f"📝 Pipeline Agent: Found TSG match but low confidence ({best_tsg.get('similarity', 0)*100:.1f}%), routing to specialized agent")
            else:
                print("📝 Pipeline Agent: No relevant TSGs found, routing to specialized agent")
        else:
            print("❌ Pipeline Agent: Unable to get incident details for TSG search")
    
    # Route based on Kusto query results if no high-confidence TSG match
    if incident_id:
        specialized_agent = await route_to_specialized_agent(incident_id)

        if specialized_agent:
            print(f"✅ Pipeline Agent: Routing to {specialized_agent}")
            
            # Add handoff notification
            if callbacks:
                agent_name_map = {
                    "step_start_failure_agent": "Step Start Failure Agent",
                    "others_agent": "Others Agent"
                }
                display_name = agent_name_map.get(specialized_agent, specialized_agent)
                await callbacks.on_handoff("Pipeline Agent", display_name, f"Category-based routing for incident {incident_id}")
                await callbacks.on_agent_end("Pipeline Agent", f"Routing to {specialized_agent}")
            
            return Command(
                goto=specialized_agent,
                update={"messages": [AIMessage(content=f"Pipeline Agent: Routing to {specialized_agent}. Incident ID: {incident_id}")]}
            )
    
    # If no specialized agent matched, route to others_agent
    print("📝 Pipeline Agent: No specialized agent matched, routing to others_agent")
    
    if callbacks:
        await callbacks.on_handoff("Pipeline Agent", "Others Agent", f"No specialized category match for incident {incident_id}")
        await callbacks.on_agent_end("Pipeline Agent", "No specialized agent matched, routing to others_agent")
    
    return Command(
        goto="others_agent",
        update={"messages": [AIMessage(content=f"Pipeline Agent: Routing to others_agent for general analysis. Incident ID: {incident_id}")]}
    )

def pipeline_supervisor(state: MessagesState) -> Command[Literal["step_start_failure_agent", "others_agent", END]]:
    """Synchronous wrapper for the pipeline agent"""
    import asyncio
    
    # Run the async function in a new event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(pipeline_supervisor_with_streaming(state))
        return result
    finally:
        loop.close()

async def route_to_specialized_agent(incident_id: str) -> str:
    """
    Query Kusto and route to appropriate specialized agent based on incident characteristics
    
    Args:
        incident_id: The incident ID to analyze
    
    Returns:
        str: Name of specialized agent to route to, or None if no match
    """
    if not incident_id:
        return None
    
    print(f"🔍 Analyzing incident {incident_id} for specialized routing...")

    # return "others_agent"
    
    # Query ticket categories from Kusto
    ticket_categories = await kusto_tool.query_ticket_category(incident_id)
    
    if ticket_categories:
        print(f"🏷️ Found categories: {ticket_categories}")
        
        # Route based on specific category patterns
        for category in ticket_categories:
            category_lower = category.lower()
            
            # Step start failure specialized agent
            if "step start failure" in category_lower:
                print(f"🎯 Category match: '{category}' → step_start_failure_agent")
                return "step_start_failure_agent"
            
            # Future: Add more specialized agents based on categories
            # elif "resource allocation" in category_lower:
            #     return "resource_allocation_agent"
    
    print("❌ No specialized agent pattern matched")
    return "others_agent"



def create_pipeline_team_graph():
    """Create the Pipeline Agent sub-graph"""
    
    # Import specialized agents
    from agents.specialized_agents.step_start_failure_agent import step_start_failure_agent_with_streaming as step_start_failure_agent
    from agents.specialized_agents.others_agent import others_agent
    
    # Create pipeline agent state graph
    pipeline_builder = StateGraph(MessagesState)
    
    # Create sync wrappers for async agents
    def step_start_failure_agent_sync(state):
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(step_start_failure_agent(state))
        finally:
            loop.close()
    
    def others_agent_sync(state):
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(others_agent(state))
        finally:
            loop.close()
    
    # Add nodes
    pipeline_builder.add_node("pipeline_supervisor", pipeline_supervisor)
    pipeline_builder.add_node("step_start_failure_agent", step_start_failure_agent_sync)
    pipeline_builder.add_node("others_agent", others_agent_sync)
    
    # Add edges
    pipeline_builder.add_edge(START, "pipeline_supervisor")
    
    # Note: No static edges to END for specialized agents
    # The supervisor uses Command objects for dynamic routing
    # Specialized agents also use Command(goto=END) for completion
    
    return pipeline_builder.compile()

# Create the pipeline agent graph
pipeline_team_graph = create_pipeline_team_graph() 
