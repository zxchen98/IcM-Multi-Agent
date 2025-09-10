import os
import re
from typing import Literal
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from langgraph.types import Command
from langgraph.graph import StateGraph, MessagesState, START, END
from langchain_core.messages import HumanMessage, AIMessage

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

# PRS routing is now handled directly, no structured output needed

def prs_supervisor(state: MessagesState) -> Command[Literal["others_agent", END]]:
    """
    PRS Team Supervisor: Routes pull request and code review incidents to specialized agents
    Currently routes to others_agent, but ready for specialized agent expansion
    """
    # Extract incident ID from messages
    incident_id = None
    user_message = ""
    
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            user_message = msg.content
            incident_id = kusto_tool.extract_incident_id(msg.content)
            break
        elif isinstance(msg, AIMessage) and "Incident ID:" in msg.content:
            match = re.search(r'Incident ID: (\w+)', msg.content)
            if match:
                incident_id = match.group(1)
    
    print(f"🔄 PRS Supervisor: Processing incident {incident_id}")
    
    # Currently no specialized agents, route to others_agent for similar tickets analysis
    print("📝 PRS Supervisor: No specialized agent matched, routing to others_agent")
    return Command(
        goto="others_agent",
        update={"messages": [AIMessage(content=f"PRS Supervisor: Routing to others_agent for general analysis. Incident ID: {incident_id}")]}
    )



def create_prs_team_graph():
    """Create the PRS Team sub-graph"""
    
    # Import specialized agents
    from specialized_agents.others_agent import others_agent
    
    # Create prs team state graph
    prs_builder = StateGraph(MessagesState)
    
    # Add nodes
    prs_builder.add_node("prs_supervisor", prs_supervisor)
    prs_builder.add_node("others_agent", others_agent)
    
    # Add edges
    prs_builder.add_edge(START, "prs_supervisor")
    
    # Supervisor routes to others_agent (can be extended for specialized agents)
    prs_builder.add_edge("others_agent", END)
    
    return prs_builder.compile()

# Create the prs team graph
prs_team_graph = create_prs_team_graph() 