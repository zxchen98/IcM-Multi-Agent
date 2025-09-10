import os
import re
from typing import Literal
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from langgraph.types import Command
from langgraph.graph import StateGraph, MessagesState, START, END
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import BaseModel

# Import Kusto query tool
from tools.kusto_query_tool import kusto_tool

# Load environment variables
load_dotenv()

# Initialize Azure OpenAI model
model = AzureChatOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
)

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
    
    # Route based on Kusto query results
    if incident_id:
        specialized_agent = route_to_specialized_agent(incident_id)
        
        if specialized_agent:
            print(f"✅ Pipeline Supervisor: Routing to {specialized_agent}")
            return Command(
                goto=specialized_agent,
                update={"messages": [AIMessage(content=f"Pipeline Supervisor: Routing to {specialized_agent}. Incident ID: {incident_id}")]}
            )
    
    # If no specialized agent matched, route to others_agent
    print("📝 Pipeline Supervisor: No specialized agent matched, routing to others_agent")
    return Command(
        goto="others_agent",
        update={"messages": [AIMessage(content=f"Pipeline Supervisor: Routing to others_agent for general analysis. Incident ID: {incident_id}")]}
    )

def route_to_specialized_agent(incident_id: str) -> str:
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