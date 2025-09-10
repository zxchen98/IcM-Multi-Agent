"""
LangGraph workflow assembly and runner utilities.
Extracted from integrated_websocket_server.py - FULLY ASYNC VERSION
"""

from langgraph.graph import StateGraph, MessagesState, START, END
from agents.master_agent import master_agent_with_streaming
from agents.specialized_agents.runners_agent import runners_agent_with_streaming
from agents.product_agents.pipeline_agent import pipeline_team_graph
from agents.product_agents.promptflow_agent import promptflow_team_graph
from agents.product_agents.prs_agent import prs_team_graph


def create_streaming_multi_agent_system(callbacks=None, session_id=None):
    """
    Create the multi-agent system workflow with streaming support - FULLY ASYNC

    Args:
        callbacks: Optional streaming callbacks instance
        session_id: Session ID for callback isolation

    Returns:
        Compiled LangGraph workflow
    """
    # Create the workflow graph
    workflow = StateGraph(MessagesState)

    # Add nodes - use async functions directly (LangGraph supports this!)
    workflow.add_node("master_agent", master_agent_with_streaming)
    workflow.add_node("runners_agent", runners_agent_with_streaming)
    
    # Product team subgraphs as callable nodes (these are already compiled sync graphs)
    workflow.add_node("pipeline_team", pipeline_team_graph.invoke)
    workflow.add_node("promptflow_team", promptflow_team_graph.invoke)
    workflow.add_node("prs_team", prs_team_graph.invoke)

    # Add edges - Master Agent will use Command.goto for dynamic routing
    workflow.add_edge(START, "master_agent")

    # Note: No static edges to END for specialized agents
    # They use Command(goto=END) for dynamic routing

    # Compile the workflow
    app = workflow.compile()

    return app


async def run_workflow_async(app, initial_input: str):
    """
    Run the workflow asynchronously - NATIVE ASYNC VERSION
    
    This version uses LangGraph's native async support, eliminating the need for
    thread pools and sync wrappers.

    Args:
        app: Compiled LangGraph workflow
        initial_input: Initial user input

    Returns:
        Final result from the workflow
    """
    # Use LangGraph's async invoke method
    result = await app.ainvoke({"messages": [{"role": "user", "content": initial_input}]})
    return result
