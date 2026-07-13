import os
import re
import json
from typing import Literal
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from langchain_openai.embeddings import AzureOpenAIEmbeddings
from langgraph.types import Command
from langgraph.graph import StateGraph, MessagesState, START, END
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import BaseModel

# Import Kusto query tool and TSG vector store tools
from tools.kusto_query_tool import kusto_tool
from tools.tsg_vector_store_tool import search_tsg_for_ticket

# Load environment variables
load_dotenv()

# Initialize Azure OpenAI model
chat_model = AzureChatOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
)

def generate_tsg_report(incident_details: dict, best_tsg: dict) -> str:
    """
    Generate TSG analysis report based on search results
    
    Args:
        incident_details: Original incident data
        best_tsg: Best TSG result from search_tsg_for_ticket
        
    Returns:
        str: Formatted TSG report
    """
    incident_id = incident_details.get('IncidentId', 'Unknown')
    title = incident_details.get('Title', 'Unknown')
    summary = incident_details.get('Summary', 'No summary available')
    
    report = f"""
🎫 **PIPELINE INCIDENT TSG ANALYSIS**
================================================

📋 **Incident Information:**
- Incident ID: {incident_id}
- Title: {title}
- Summary: {summary}

"""
    
    if best_tsg:
        report += f"✅ **FOUND THE CLOSEST MATCHING TROUBLESHOOTING GUIDE:**\n\n"

        similarity_percent = best_tsg.get('similarity', 0) * 100
        report += f"**{best_tsg.get('title', 'Unknown TSG')}** (Similarity: {similarity_percent:.1f}%)\n"
        report += f"   📁 **Path:** {best_tsg.get('path', 'N/A')}\n"
        report += f"   🆔 **TSG ID:** {best_tsg.get('id', 'N/A')}\n"
            
        solution = best_tsg.get('solution', '').strip()
        if solution:
            report += f"   \n   **📋 Solution:**\n```\n{solution}\n```\n\n"
        else:
            report += f"   ⚠️ **No solution content found**\n\n"
        
        report += "================================================"
    else:
        report += """❌ **NO RELEVANT TSG FOUND:**

💡 **RECOMMENDED ACTIONS:**

1. **Manual Investigation:**
   - No specific TSG available for this incident type
   - Proceed with general troubleshooting approaches
   - Review system logs and monitoring data

2. **Escalation:**
   - Route to specialized agents for detailed analysis
   - Consider creating new TSG if this becomes a recurring issue

================================================
"""
    
    return report

def pipeline_supervisor(state: MessagesState) -> Command[Literal["step_start_failure_agent", "others_agent", END]]:
    """
    Pipeline Team Supervisor: Routes pipeline incidents to specialized agents based on Kusto queries
    """
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
    print("\n\n")
    print("=" * 60)
    print(f"🔧 Pipeline Supervisor: Processing incident {incident_id}")

    
    # print("🔍 Pipeline Supervisor: Checking TSG vector store...")
    # if incident_id:
    #     # Get incident details for TSG search
    #     incident_details = kusto_tool.query_incident_details(incident_id)
    #     if incident_details and incident_details.get('Title') != 'Unknown':
    #         # Search TSG vector store
    #         title = incident_details.get('Title', '')
    #         summary = incident_details.get('Summary', '')
    #         best_tsg = search_tsg_for_ticket(title, summary)
            
    #         if best_tsg:
    #             print("✅ Pipeline Supervisor: Found relevant TSGs, returning TSG report")
    #             tsg_report = generate_tsg_report(incident_details, best_tsg)
    #             return Command(
    #                 goto=END,
    #                 update={"messages": [AIMessage(content=tsg_report)]}
    #             )
    #         else:
    #             print("📝 Pipeline Supervisor: No relevant TSGs found, routing to others_agent")
    #     else:
    #         print("❌ Pipeline Supervisor: Unable to get incident details, routing to others_agent")
    

    # Route based on Kusto query results
    if incident_id:
        specialized_agent = route_to_specialized_agent(incident_id)
        
        if specialized_agent:
            print(f"✅ Pipeline Supervisor: Routing to {specialized_agent}")
            return Command(
                goto=specialized_agent,
                update={"messages": [AIMessage(content=f"Pipeline Supervisor: Routing to {specialized_agent}. Incident ID: {incident_id}")]}
            )
    print("📝 Pipeline Supervisor: Routing to others_agent for general analysis")
    
    # If no TSG found or incident details unavailable, route to others_agent
    return Command(
        goto="others_agent",
        update={"messages": [AIMessage(content=f"Pipeline Supervisor: No TSG found, routing to others_agent for general analysis. Incident ID: {incident_id}")]}
    )

def f(incident_id: str) -> str:
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
    ticket_categories = kusto_tool.query_ticket_category(incident_id)
    
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
    """Create the Pipeline Team sub-graph"""
    
    # Import specialized agents
    from specialized_agents.step_start_failure_agent import step_start_failure_agent
    from specialized_agents.others_agent import others_agent
    
    # Create pipeline team state graph
    pipeline_builder = StateGraph(MessagesState)
    
    # Add nodes
    pipeline_builder.add_node("pipeline_supervisor", pipeline_supervisor)
    pipeline_builder.add_node("step_start_failure_agent", step_start_failure_agent)
    pipeline_builder.add_node("others_agent", others_agent)
    
    # Add edges
    pipeline_builder.add_edge(START, "pipeline_supervisor")
    
    # No conditional edges needed - supervisor uses Command objects for direct routing
    # All specialized agents end their execution
    pipeline_builder.add_edge("step_start_failure_agent", END)
    pipeline_builder.add_edge("others_agent", END)
    
    return pipeline_builder.compile()

# Create the pipeline team graph
pipeline_team_graph = create_pipeline_team_graph() 