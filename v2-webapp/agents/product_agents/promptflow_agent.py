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

async def promptflow_supervisor_with_streaming(state: MessagesState) -> Command[Literal["others_agent", END]]:
    """
    PromptFlow Team Supervisor: Routes AI/ML workflow incidents to specialized agents
    """
    callbacks = get_current_callbacks()
    
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
    
    if callbacks:
        await callbacks.on_agent_start("PromptFlow Supervisor", f"Processing AI/ML workflow incident {incident_id}")
    
    print(f"🤖 PromptFlow Supervisor: Processing incident {incident_id}")
    
    # Currently no specialized agents, route to others_agent for similar tickets analysis
    print("📝 PromptFlow Supervisor: No specialized agent matched, routing to others_agent")
    
    if callbacks:
        await callbacks.on_agent_message("PromptFlow Supervisor", "No specialized PromptFlow agents available, routing to general analysis")
        await callbacks.on_handoff("PromptFlow Supervisor", "Others Agent", f"General analysis for PromptFlow incident {incident_id}")
        await callbacks.on_agent_end("PromptFlow Supervisor", "Routing to others_agent for general analysis")
    
    return Command(
        goto="others_agent",
        update={"messages": [AIMessage(content=f"PromptFlow Supervisor: Routing to others_agent for general analysis. Incident ID: {incident_id}")]}
    )

def promptflow_supervisor(state: MessagesState) -> Command[Literal["others_agent", END]]:
    """Synchronous wrapper for the promptflow supervisor"""
    import asyncio
    
    # Run the async function in a new event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(promptflow_supervisor_with_streaming(state))
        return result
    finally:
        loop.close()





def create_promptflow_team_graph():
    """Create the PromptFlow Team sub-graph"""
    
    # Import specialized agents
    from agents.specialized_agents.others_agent import others_agent
    
    # Create promptflow team state graph
    promptflow_builder = StateGraph(MessagesState)
    
    # Create sync wrapper for async agent
    def others_agent_sync(state):
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(others_agent(state))
        finally:
            loop.close()
    
    # Add nodes
    promptflow_builder.add_node("promptflow_supervisor", promptflow_supervisor)
    promptflow_builder.add_node("others_agent", others_agent_sync)
    
    # Add edges
    promptflow_builder.add_edge(START, "promptflow_supervisor")
    
    # Note: No static edges to END for specialized agents
    # The supervisor uses Command objects for dynamic routing
    # Specialized agents use Command(goto=END) for completion
    
    return promptflow_builder.compile()

# Create the promptflow team graph
promptflow_team_graph = create_promptflow_team_graph() 