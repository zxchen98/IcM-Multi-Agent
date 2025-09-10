import os
import re
from typing import Literal
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from langgraph.types import Command
from langgraph.graph import MessagesState, END
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

# Define structured output for routing decisions
class RoutingDecision(BaseModel):
    next_agent: Literal["pipeline_team", "promptflow_team", "prs_team", "__end__"]
    reasoning: str

def parse_user_input(user_input: str) -> tuple[str, str]:
    """
    Parse user input to extract incident ID and title
    
    Supports formats like:
    - "Incident 669533608 : [PipelineRunner][westus] Reliability Runner failed: test_distributed_component run failed from 8/12/2025 1:44:20 PM to 8/12/2025 4:44:20 PM"
    - "669533608"
    - "Incident 669533608"
    
    Returns:
        tuple[str, str]: (incident_id, title) - title is empty string if not found in input
    """
    if not user_input:
        return None, ""
    
    # Pattern to match "Incident {id} : {title}" format
    incident_with_title_pattern = r'Incident\s+(\d+)\s*:\s*(.+)'
    match = re.search(incident_with_title_pattern, user_input, re.IGNORECASE)
    
    if match:
        incident_id = match.group(1)
        title = match.group(2).strip()
        print(f"📋 Parsed input - ID: {incident_id}, Title: {title[:100]}{'...' if len(title) > 100 else ''}")
        return incident_id, title
    
    # Fallback: try to extract just incident ID
    incident_id = kusto_tool.extract_incident_id(user_input)
    if incident_id:
        print(f"📋 Parsed input - ID: {incident_id}, Title: (not provided)")
        return incident_id, ""
    
    print(f"📋 No incident ID found in input")
    return None, ""

def has_runner_keyword(title: str) -> bool:
    """
    Check if title contains runner-related keywords
    
    Args:
        title: Title text to check
        
    Returns:
        bool: True if runner keywords found, False otherwise
    """
    if not title:
        return False
    
    title_lower = title.lower()
    runner_keywords = ['runner', 'Runner']
    
    for keyword in runner_keywords:
        if keyword in title_lower:
            print(f"🏃 Runner keyword '{keyword}' found in title")
            return True
    
    return False

def route_by_incident_id(incident_id: str) -> str:
    """
    Route based on incident ID's owning team information
    
    Args:
        incident_id: Incident ID to query for owning team
        
    Returns:
        str: Recommended product team based on owning team, or None if no match
    """
    if not incident_id:
        return None
    
    # Get owning team information
    owning_teams_list = kusto_tool.query_owning_team(incident_id)
    
    if not owning_teams_list:
        return None
    
    # Check each owning team for routing rules
    for owning_team_id in owning_teams_list:
        owning_team_str = str(owning_team_id)
        
        # "PROJECTVIENNASERVICES\Designer" "PROJECTVIENNASERVICES\\AEther"
        if "65287" in owning_team_str or "50151" in owning_team_str:
            return "pipeline_team"
        # "PROJECTVIENNASERVICES\\Promptflow"
        elif "105839" in owning_team_str:
            return "promptflow_team"
        # "PROJECTVIENNASERVICES\\ParallelComputing" 
        elif "82194" in owning_team_str:
            return "prs_team"
    
    print(f"Team-based routing: OwningTeams '{owning_teams_list}' found but no specific routing rule matched")
    return None

def master_agent(state: MessagesState) -> Command[Literal["pipeline_team", "promptflow_team", "prs_team", "runners_agent", "__end__"]]:
    """
    Master Agent: Intelligent routing with clear priority logic
    
    Priority logic:
    1. Parse user input to extract incident ID and title
    2. If title contains 'runner' keywords -> route to runners_agent
    3. If no title or no runner keywords -> query incident details and check title again
    4. If still no runner keywords -> check owning team ID for routing
    5. Fallback to text analysis if no team routing rules match
    """
    # Get the latest user message
    user_message = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            user_message = msg.content
            break
    
    if not user_message:
        return Command(
            goto=END,
            update={"messages": [AIMessage(content="Master Agent: No user input found")]}
        )
    
    print(f"🎯 Master Agent processing: {user_message[:100]}{'...' if len(user_message) > 100 else ''}")
    
    # Step 1: Parse user input to get incident ID and title
    incident_id, title_from_input = parse_user_input(user_message)
    
    if not incident_id:
        print("📝 No incident ID found, using text analysis routing")
        return text_analysis_routing(user_message)
    
    # Step 2: Check if title from input contains runner keywords
    if title_from_input and has_runner_keyword(title_from_input):
        print(f"🏃 Runner detected in input title, routing to runners_agent")
        context_message = f"Master Agent: Runner keyword detected in input title. Routing to runners_agent. Incident ID: {incident_id}"
        return Command(
            goto="runners_agent",
            update={"messages": [AIMessage(content=context_message)]}
        )
    
    # Step 3: If no title in input or no runner keywords, query incident details
    print(f"🔍 Querying incident details for ID: {incident_id}")
    incident_details = kusto_tool.query_incident_details(incident_id)
    
    if incident_details and incident_details.get('Title'):
        detailed_title = incident_details.get('Title', '')
        print(f"📋 Retrieved title: {detailed_title[:100]}{'...' if len(detailed_title) > 100 else ''}")
        
        # Check if detailed title contains runner keywords
        if has_runner_keyword(detailed_title):
            print(f"🏃 Runner detected in detailed title, routing to runners_agent")
            context_message = f"Master Agent: Runner keyword detected in incident title. Routing to runners_agent. Incident ID: {incident_id}"
            return Command(
                goto="runners_agent", 
                update={"messages": [AIMessage(content=context_message)]}
            )
    
    # Step 4: No runner keywords found, check owning team ID for routing
    print(f"🏢 No runner keywords found, checking owning team for routing")
    team_decision = route_by_incident_id(incident_id)
    
    if team_decision:
        print(f"👥 Team-based routing decision: {team_decision}")
        context_message = f"Master Agent: Team-based routing to {team_decision}. Incident ID: {incident_id}"
        return Command(
            goto=team_decision,
            update={"messages": [AIMessage(content=context_message)]}
        )
    else:
        print("🏢 No team routing rule matched, falling back to text analysis")
    
    # Step 5: Fallback to text analysis
    return text_analysis_routing(user_message, incident_id)

def text_analysis_routing(user_message: str, incident_id: str = None) -> Command:
    """
    Fallback text analysis routing when incident-based routing fails
    """
    print("📝 Using text analysis routing")
    
    text_routing_prompt = f"""
    You are an intelligent router. Based on the user input text, select the most appropriate team:

    1. **pipeline_team**: CI/CD pipelines, builds, deployments, DevOps-related issues
    2. **promptflow_team**: Prompt Flow, AI workflows, prompt engineering-related issues  
    3. **prs_team**: Pull Requests, code reviews, Git-related issues

    User input: {user_message}

    If you cannot determine the appropriate category, select "__end__".
    """
    
    try:
        response = model.with_structured_output(RoutingDecision).invoke([
            HumanMessage(content=text_routing_prompt)
        ])
        
        print(f"🎯 Text analysis routing decision: {response.next_agent}")
        print(f"📝 Decision reasoning: {response.reasoning}")
        
        if response.next_agent == "__end__":
            return Command(
                goto=END,
                update={"messages": [AIMessage(content=f"Master Agent: Unable to determine appropriate team. Reason: {response.reasoning}")]}
            )
        
        context_message = f"Master Agent: Text-based routing to {response.next_agent}. Incident ID: {incident_id or 'None'}. Reason: {response.reasoning}"
        
        return Command(
            goto=response.next_agent,
            update={"messages": [AIMessage(content=context_message)]}
        )
        
    except Exception as e:
        print(f"❌ Master Agent error: {e}")
        return Command(
            goto=END,
            update={"messages": [AIMessage(content=f"Master Agent processing error: {str(e)}")]}
        ) 
