"""
IcM Multi-Agent System with Hierarchical LangGraph Architecture
==============================================================

A three-tier hierarchical incident management system that intelligently routes 
tickets through a structured agent hierarchy.

Architecture:
- Top Level: Master Agent (routes to product teams)
- Middle Level: Product Team Supervisors (pipeline, promptflow, prs teams)
- Bottom Level: Specialized Agents (step_start_failure_agent, etc.)

Features:
- Hierarchical agent routing with team-based organization
- IcM database integration via Kusto queries  
- Team-based incident assignment with fallback routing
- Specialized agent handling for specific incident types
"""

import os
import sys
from typing import Literal
from dotenv import load_dotenv
from langgraph.graph import StateGraph, MessagesState, START, END
from master_agent import master_agent
from product_agents.pipeline_agent import pipeline_team_graph
from product_agents.promptflow_agent import promptflow_team_graph  
from product_agents.prs_agent import prs_team_graph
from specialized_agents.runners_agent import runners_agent

# Load environment variables
load_dotenv()

# Check required environment variables
required_env_vars = [
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY", 
    "AZURE_OPENAI_API_VERSION",
    "AZURE_OPENAI_DEPLOYMENT_NAME"
]

missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
    print("Please check your .env file and ensure all variables are set.")
    sys.exit(1)


def create_hierarchical_multi_agent_system():
    """Create and configure the hierarchical multi-agent system graph"""
    
    # Create the top-level state graph
    workflow = StateGraph(MessagesState)
    
    # Add top-level supervisor
    workflow.add_node("master_agent", master_agent)
    
    # Add specialized agents that can be directly routed to
    workflow.add_node("runners_agent", runners_agent)
    
    # Add team graphs as nodes
    workflow.add_node("pipeline_team", pipeline_team_graph)
    workflow.add_node("promptflow_team", promptflow_team_graph)
    workflow.add_node("prs_team", prs_team_graph)
    
    # Define routing from start to master agent
    workflow.add_edge(START, "master_agent")
    
    # Master agent uses Command objects for routing, so no conditional edges needed
    # All specialized agents and team graphs end their execution
    workflow.add_edge("runners_agent", END)
    workflow.add_edge("pipeline_team", END)
    workflow.add_edge("promptflow_team", END) 
    workflow.add_edge("prs_team", END)
    
    return workflow.compile()

def main():
    """Main function to run the hierarchical multi-agent system"""
    
    print("🚀 IcM Hierarchical Multi-Agent System Starting...")
    print("=" * 60)
    print("📊 Architecture: Master Agent → Product Teams → Specialized Agents")
    print("=" * 60)
    
    # Create the hierarchical multi-agent system
    app = create_hierarchical_multi_agent_system()
    
    # Main interaction loop
    while True:
        print("\n📝 Please enter an incident ID (or 'quit' to exit):")
        user_input = input("> ").strip()
        
        if user_input.lower() in ['quit', 'exit', 'q']:
            print("👋 Goodbye!")
            break
            
        if not user_input:
            print("⚠️ Please enter a valid incident ID")
            continue
        
        try:
            print(f"\n🎯 Processing incident: {user_input}")
            print("=" * 60)
            
            # Process the incident through the hierarchical multi-agent system
            result = app.invoke({
                "messages": [{"role": "user", "content": user_input}]
            })
            
            # Display results
            print("\n📊 Hierarchical Analysis Results:")
            print("=" * 60)
            
            # Show all agent responses with hierarchy indicators
            for i, msg in enumerate(result["messages"]):
                # Handle LangChain message objects (HumanMessage, AIMessage)
                if hasattr(msg, 'content'):
                    # This is a LangChain message object
                    content = msg.content
                    msg_type = type(msg).__name__
                    
                    # Only show AI agent responses, skip user input
                    if msg_type == 'AIMessage':
                        # Add hierarchy level indicators
                        if "Master Agent:" in content:
                            print(f"🎯 [TOP LEVEL] {content}\n")
                        elif "Supervisor:" in content:
                            print(f"👥 [TEAM LEVEL] {content}\n")
                        elif any(agent in content for agent in ["Pipeline Agent", "PromptFlow Agent", "PRS Agent"]):
                            print(f"🛠️ [PRODUCT LEVEL] {content}\n")
                        elif "Runners Agent:" in content:
                            print(f"🏃 [SPECIALIZED] {content}\n")
                        elif "Failure Agent:" in content:
                            print(f"🔧 [SPECIALIZED] {content}\n")
                        else:
                            print(f"📝 {content}\n")
                
                # Handle dictionary format messages (if any)
                elif isinstance(msg, dict) and msg.get("role") == "assistant":
                    content = msg['content']
                    
                    # Add hierarchy level indicators
                    if "Master Agent:" in content:
                        print(f"🎯 [TOP LEVEL] {content}\n")
                    elif "Supervisor:" in content:
                        print(f"👥 [TEAM LEVEL] {content}\n")
                    elif any(agent in content for agent in ["Pipeline Agent", "PromptFlow Agent", "PRS Agent"]):
                        print(f"🛠️ [PRODUCT LEVEL] {content}\n")
                    elif "Runners Agent:" in content:
                        print(f"🏃 [SPECIALIZED] {content}\n")
                    elif "Failure Agent:" in content:
                        print(f"🔧 [SPECIALIZED] {content}\n")
                    else:
                        print(f"📝 {content}\n")
            
        except Exception as e:
            print(f"❌ Error processing incident: {e}")
            import traceback
            print("📋 Full error trace:")
            traceback.print_exc()
        
        print("\n" + "=" * 60)

if __name__ == "__main__":
    main()

# Test incident IDs for reference:
# Incident 631600195 : [ModelFun] - The scope module in AML cannot be started