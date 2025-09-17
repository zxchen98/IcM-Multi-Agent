import os
import re
from typing import Literal, Dict, Any, List
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from langgraph.types import Command
from langgraph.graph import END
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import MessagesState
from pydantic import BaseModel

# Import tools
from tools.kusto_query_tool import kusto_tool
from tools.find_similar_tickets_tool import find_similar_tickets
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

class SimpleTicketAnalysis(BaseModel):
    problem_stage: str
    key_log: str
    conclusion: str

def determine_product_from_messages(state: MessagesState) -> str:
    """
    Determine product type based on routing messages in the conversation
    
    Args:
        state: Current conversation state
        
    Returns:
        str: Product type (pipeline, promptflow, prs)
    """
    # Check messages for routing information (most recent first)
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage):
            content = msg.content.lower()
            # Check for specific supervisor routing messages
            if "routing to others_agent" in content:
                if "promptflow supervisor" in content:
                    return "promptflow"
                elif "prs supervisor" in content:
                    return "prs"
                elif "pipeline agent" in content:
                    return "pipeline"
    
    # Secondary check - look for any supervisor mentions
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage):
            content = msg.content.lower()
            if "promptflow supervisor" in content:
                return "promptflow"
            elif "prs supervisor" in content:
                return "prs"
            elif "pipeline agent" in content:
                return "pipeline"
    
    # Tertiary check - look for agent mentions
    for msg in state["messages"]:
        if isinstance(msg, AIMessage):
            content = msg.content.lower()
            if "promptflow" in content and ("agent" in content or "analysis" in content):
                return "promptflow"
            elif "prs" in content and ("agent" in content or "analysis" in content):
                return "prs"
            elif "pipeline" in content and ("agent" in content or "analysis" in content):
                return "pipeline"
    
    # Final fallback to pipeline
    print("⚠️ Others Agent: Could not determine product from messages, defaulting to 'pipeline'")
    return "pipeline"

def simple_analyze_ticket(incident_details: Dict[str, Any]) -> SimpleTicketAnalysis:
    # Format incident details for analysis
    formatted_content = f"""
    Incident ID: {incident_details.get('IncidentId', 'Unknown')}
    Title: {incident_details.get('Title', 'Unknown')}
    Summary: {incident_details.get('Summary', 'No summary available')}
    MergedText: {incident_details.get('MergedText', 'No additional details available')}
    """
    
    analysis_prompt = f"""
    Please analyze this technical support ticket and extract key information:

    Ticket Content:
    {formatted_content}

    Please extract the following information:
    - problem_stage: At what stage did the problem occur - e.g.: deployment stage, runtime, configuration stage, etc.
    - key_log: What is the most critical log - key error messages or log entries from the ticket
    - conclusion: What is the conclusion of the problem - root cause analysis

    If information is not available, provide a reasonable inference or state "Not available".
    """
    
    try:
        response = model.with_structured_output(SimpleTicketAnalysis).invoke([
            HumanMessage(content=analysis_prompt)
        ])    
        print(f"🔍 Simple ticket Analysis completed")
        print(f"   Problem Stage: {response.problem_stage}")
        print(f"   Key Log: {response.key_log}")
        print(f"   Conclusion: {response.conclusion}")
        return response
    except Exception as e:
        print(f"❌ Error in simple ticket analysis: {e}")
        return SimpleTicketAnalysis(
            problem_stage="Analysis failed",
            key_log="Analysis failed",
            conclusion="Analysis failed"
        )

async def others_agent(state: MessagesState) -> Command[Literal["__end__"]]:
    """
    Others Agent: Handles incidents that don't match specific categories by finding similar historical tickets
    """
    callbacks = get_current_callbacks()
    
    if callbacks:
        await callbacks.on_agent_start("Others Agent", "Processing general incident analysis")
    
    print("\n" + "="*60)
    print("🔍 Others Agent: Processing general incident...")
    
    # Extract incident ID from messages
    incident_id = None
    
    # Check user messages first
    for msg in state["messages"]:
        if isinstance(msg, HumanMessage):
            incident_id = kusto_tool.extract_incident_id(msg.content)
            if incident_id:
                break
    
    # Check AI messages for incident ID
    if not incident_id:
        for msg in reversed(state["messages"]):
            if isinstance(msg, AIMessage) and "Incident ID:" in msg.content:
                match = re.search(r'Incident ID: (\w+)', msg.content)
                if match:
                    incident_id = match.group(1)
                    break
    
    if not incident_id:
        print("❌ Others Agent: No incident ID found")
        error_msg = "Others Agent: No incident ID found for analysis."
        if callbacks:
            await callbacks.on_agent_end("Others Agent", error_msg)
        return Command(
            goto=END,
            update={"messages": [AIMessage(content=error_msg)]}
        )
    
    print(f"📋 Others Agent: Analyzing incident {incident_id}")
    if callbacks:
        await callbacks.on_agent_message("Others Agent", f"📋 Analyzing incident {incident_id}")
    
    # Get incident details from Kusto
    incident_details = await kusto_tool.query_incident_details(incident_id)
    
    if not incident_details or incident_details.get('Title') == 'Unknown':
        print("❌ Others Agent: Unable to retrieve incident details")
        error_msg = f"Others Agent: Unable to retrieve details for incident {incident_id}"
        if callbacks:
            await callbacks.on_agent_end("Others Agent", error_msg)
        return Command(
            goto=END,
            update={"messages": [AIMessage(content=error_msg)]}
        )
    
    # Extract relevant information for similarity search
    title = incident_details.get('Title', '')  # Use uppercase field name
    summary = incident_details.get('Summary', '')  # Use uppercase field name
    incident_description = f"{title} {summary}".strip()
    
    print(f"🔍 Others Agent: Searching for TSGs...")
    print(f"📝 Incident Description: {incident_description}")
    
    # if callbacks:
    # await callbacks.on_agent_message("Others Agent", f"🔍 Searching for TSGs...")

    # # Also search TSG vector store for relevant solutions
    # print(f"🔍 Others Agent: Searching TSG vector store...")
    # tsg_result = None
    # try:
    #     tsg_result = await search_tsg_for_ticket(title, summary)
    #     if tsg_result:
    #         similarity_percent = tsg_result.get('similarity', 0) * 100
    #         print(f"✅ Others Agent: Found TSG match with {similarity_percent:.1f}% confidence")
    #     else:
    #         print("📝 Others Agent: No relevant TSGs found")
    # except Exception as e:
    #     print(f"⚠️ Others Agent: TSG search failed: {e}")
    #     tsg_result = None

    if callbacks:
        await callbacks.on_agent_message("Others Agent", f"🔍 Searching for similar tickets...")
    
    # Determine product based on which team routed to this agent
    product = determine_product_from_messages(state)
    print(f"🏷️ Others Agent: Using product '{product}' for similarity search")
    
    analysis = simple_analyze_ticket(incident_details)
    print(f"🔍 Others Agent: Simple ticket Analysis completed")
    
    # Find similar tickets using the find_similar_tickets tool
    try:
        similar_tickets = await find_similar_tickets(
            incident_description=incident_description,
            current_incident_id=incident_id,
            product=product,
            ai_problem_stage=analysis.problem_stage,
            ai_key_log=analysis.key_log,
            ai_conclusion=analysis.conclusion
        )
        
        print(f"✅ Others Agent: Found {len(similar_tickets)} similar tickets")
        
        # Generate comprehensive report
        report = generate_others_report(incident_details, similar_tickets)

        return Command(
            goto=END,
            update={"messages": [AIMessage(content=report)]}
        )
        
    except Exception as e:
        print(f"❌ Others Agent: Error finding similar tickets: {e}")
        if callbacks:
            await callbacks.on_agent_message("Others Agent", f"⚠️ Error finding similar tickets, using fallback analysis")
        
        # Fallback to general analysis
        fallback_report = generate_fallback_report(incident_details)
        
        if callbacks:
            await callbacks.on_agent_end("Others Agent", "Completed with fallback analysis")
        
        return Command(
            goto=END,
            update={"messages": [AIMessage(content=fallback_report)]}
        )


def generate_others_report(incident_details: Dict[str, Any], similar_tickets: List, tsg_result: Dict = None) -> str:
    """
    Generate comprehensive report with similar tickets analysis and TSG information
    
    Args:
        incident_details: Original incident data
        similar_tickets: List of similar tickets found
        tsg_result: TSG search result (optional)
        
    Returns:
        str: Formatted report
    """
    report = f"""
🎫 **GENERAL INCIDENT ANALYSIS REPORT**
================================================

📋 **Incident Information:**
- Incident ID: {incident_details.get('IncidentId', 'Unknown')}
- Title: {incident_details.get('Title', 'Unknown')}
- Summary: {incident_details.get('Summary', 'No summary available')}

"""
    
    # Add TSG information if available
    if tsg_result:
        similarity_percent = tsg_result.get('similarity', 0) * 100
        report += f"""
📚 **TSG KNOWLEDGE BASE MATCH:**
- **Best Match:** {tsg_result.get('title', 'Unknown TSG')}
- **Similarity Score:** {similarity_percent:.1f}%
- **TSG Path:** {tsg_result.get('path', 'Unknown path')}

📖 **TSG Overview:**
{tsg_result.get('overview', 'No overview available')}

💡 **TSG Recommended Solution:**
{tsg_result.get('solution', 'No solution content available')}

"""
    else:
        report += """
📚 **TSG KNOWLEDGE BASE:**
No relevant TSG documents found for this incident.

"""
    
    if similar_tickets:
        report += f"""
🔍 **SIMILAR HISTORICAL TICKETS FOUND:**
Found {len(similar_tickets)} similar tickets that can provide insights:

"""
        for i, ticket in enumerate(similar_tickets, 1):
            report += f"\n**{i}. Incident ID: {ticket.incident_id}** (Similarity: {ticket.similarity_score}%)\n"
            report += f"   **Title:** {ticket.title}\n"
            report += f"   **Reason:** {ticket.similarity_reason}\n"
            report += f"   **AI Conclusion:** {ticket.ai_conclusion}\n"
            report += f"   **Human Investigation:** {ticket.investigation}\n"        
    
    else:
        report += """
⚠️ **NO SIMILAR TICKETS FOUND:**
No similar historical tickets were found in the database. This might be:
- A new type of incident
- An incident with unique characteristics
- A data availability issue

"""
    
    return report

def generate_fallback_report(incident_details: Dict[str, Any]) -> str:
    """
    Generate fallback report when similar tickets search fails
    
    Args:
        incident_details: Original incident data
        
    Returns:
        str: Formatted fallback report
    """
    report = f"""
🎫 **GENERAL INCIDENT ANALYSIS REPORT**
================================================

📋 **Incident Information:**
- Incident ID: {incident_details.get('IncidentId', 'Unknown')}
- Title: {incident_details.get('Title', 'Unknown')}
- Summary: {incident_details.get('Summary', 'No summary available')}
- Severity: {incident_details.get('Severity', 'Unknown')}
- Owning Team: {incident_details.get('OwningTeamName', 'Unknown')}

⚠️ **ANALYSIS NOTE:**
Similar tickets search was not available. Providing general analysis based on incident details.

🔍 **GENERAL ANALYSIS:**
Based on the incident information provided, this appears to be a general incident that requires manual investigation. 

💡 **RECOMMENDED ACTIONS:**

1. **Immediate Response:**
   - Assess the impact and severity of the incident
   - Check system monitoring dashboards
   - Review recent changes or deployments

2. **Investigation:**
   - Examine system logs and error messages
   - Check for patterns in monitoring data
   - Verify service dependencies and connectivity

3. **Next Steps:**
   - Document investigation findings
   - Implement appropriate fixes or workarounds
   - Consider escalation if needed

================================================
"""
    
    return report
