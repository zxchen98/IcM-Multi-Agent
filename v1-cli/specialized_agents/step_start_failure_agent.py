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

class RootCauseAnalysis(BaseModel):
    """Structure for root cause analysis results"""
    failed_step: str
    immediate_cause: str
    step_cause: str
    confidence_score: float

class TSGMatchResult(BaseModel):
    """Structure for TSG matching results"""
    matched_tsg: str
    action_required: str
    transfer_to: str
    match_confidence: float

class StepStartFailureAnalyzer:
    """Specialized analyzer for step start failure incidents"""
    
    def __init__(self):
        self.tsg_rules = [
            {
                "failed_step": "Submit APCloud Job",
                "pattern": "Retriable exception occured while running job, will retry in the next round",
                "root_cause": "APCloud job failed to submit",
                "action": "Transfer to Aether team",
                "transfer_to": "AEther/AEther",
                "description": "APCloud submission failure requiring Aether team intervention"
            }
        ]
    
    def analyze_root_cause(self, incident_details: Dict[str, Any]) -> RootCauseAnalysis:
        """
        Use LLM to analyze incident details and identify root cause
        
        Args:
            incident_details: Complete incident information from Kusto
            
        Returns:
            RootCauseAnalysis: Structured analysis results
        """
        analysis_prompt = f"""
        You are an expert in diagnosing step start failure incidents. Analyze the following incident details and extract information EXACTLY from the provided logs/data.

        INCIDENT DETAILS:
        - ID: {incident_details.get('incident_id', 'Unknown')}
        - Title: {incident_details.get('title', 'Unknown')}
        - Summary: {incident_details.get('summary', 'No summary')}
        - Description: {incident_details.get('description', 'No description')}
        - Severity: {incident_details.get('severity', 'Unknown')}

        Please analyze this incident and provide:
        1. In what step the failure occurred (The call stack). The value should be in [Get Obtoken, Submit APCloud Job]
        2. Immediate cause (detailed specific error message, must be in the logs), like "The SSL connection could not be established"
        3. Step cause (error message for the step, must be in the logs), like "Retriable exception occured while running job"
        4. Confidence score (0.0-1.0) for your analysis
        """
        
        try:
            response = model.with_structured_output(RootCauseAnalysis).invoke([
                HumanMessage(content=analysis_prompt)
            ])    
            print(f"🔍 Root Cause Analysis completed with confidence: {response.confidence_score}")
            return response
        except Exception as e:
            print(f"❌ Error in root cause analysis: {e}")
            return RootCauseAnalysis(
                failed_step="Analysis failed",
                immediate_cause="Analysis failed",
                step_cause="Analysis failed",
                confidence_score=0.0
            )
    
    def match_tsg_rules(self, root_cause_analysis: RootCauseAnalysis) -> TSGMatchResult:
        """
        Match incident against TSG rules to determine actions
        
        Args:
            incident_details: Incident information
            root_cause_analysis: LLM analysis results
            
        Returns:
            TSGMatchResult: Matching results and recommended actions
        """

        for rule in self.tsg_rules:
            if rule["failed_step"].lower() == root_cause_analysis.failed_step.lower() \
                and (root_cause_analysis.step_cause.lower() in rule["pattern"].lower() \
                     or root_cause_analysis.immediate_cause.lower() in rule["pattern"].lower()):
                print(f"✅ TSG Rule matched: {rule['description']}")
                return TSGMatchResult(
                    matched_tsg=rule["description"],
                    action_required=rule["action"],
                    transfer_to=rule["transfer_to"],
                    match_confidence=0.9
                )
        
        # No specific TSG rule matched
        print("📋 No specific TSG rule matched, providing general guidance")
        return TSGMatchResult(
            matched_tsg="General step start failure handling",
            action_required="Manual investigation required",
            transfer_to="pipeline_team",
            match_confidence=0.3
        )
    
    def generate_final_report(self, incident_details: Dict[str, Any], 
                            root_cause: RootCauseAnalysis, 
                            tsg_result: TSGMatchResult) -> str:
        """
        Generate comprehensive final report with recommendations
        
        Args:
            incident_details: Original incident data
            root_cause: LLM analysis results
            tsg_result: TSG matching results
            
        Returns:
            str: Formatted final report
        """
        report = f"""
🎫 **STEP START FAILURE ANALYSIS REPORT**
================================================

📋 **Incident Information:**
- Incident ID: {incident_details.get('incident_id', 'Unknown')}
- Title: {incident_details.get('title', 'Unknown')}
- Severity: {incident_details.get('severity', 'Unknown')}

🔍 **Root Cause Analysis:**
- **Failed Step:** {root_cause.failed_step}
- **Immediate Cause:** {root_cause.immediate_cause}
- **Step Cause:** {root_cause.step_cause}
- **Confidence:** {root_cause.confidence_score:.1%}


⚡ **TSG Rule Match:**
- **Matched Rule:** {tsg_result.matched_tsg}
- **Match Confidence:** {tsg_result.match_confidence:.1%}

🎯 **Recommended Action:**
- **Action:** {tsg_result.action_required}
- **Transfer To:** {tsg_result.transfer_to}

================================================
"""
        return report

def step_start_failure_agent(state: MessagesState) -> Command[Literal[END]]:
    """
    Step Start Failure Agent: Specialized in analyzing and resolving step start failure incidents
    """
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
        return Command(
            goto=END,
            update={"messages": [AIMessage(content="Step Start Failure Agent: No incident ID found for analysis.")]}
        )
    
    print("\n\n")
    print("=" * 60)
    print(f"🔧 Step Start Failure Agent analyzing incident: {incident_id}")
    
    try:
        # Initialize analyzer
        analyzer = StepStartFailureAnalyzer()
        
        # Step 1: Query detailed incident information
        print("\n📋 Step 1: Querying incident details...")
        incident_details = kusto_tool.query_incident_details(incident_id)
        
        if not incident_details or incident_details.get('title') == 'Unknown':
            return Command(
                goto=END,
                update={"messages": [AIMessage(content=f"Step Start Failure Agent: Unable to retrieve details for incident {incident_id}")]}
            )
        
        # Step 2: LLM Root Cause Analysis
        print("\n🔍 Step 2: Performing root cause analysis...")
        root_cause_analysis = analyzer.analyze_root_cause(incident_details)
        
        # Step 3: TSG Rule Matching
        print("\n⚡ Step 3: Matching against TSG rules...")
        tsg_result = analyzer.match_tsg_rules(root_cause_analysis)
        
        # Step 4: Generate Final Report
        print("\n📄 Step 4: Generating final report...")
        final_report = analyzer.generate_final_report(incident_details, root_cause_analysis, tsg_result)
        
        print("\n✅ Step Start Failure analysis completed!")
        
        return Command(
            goto=END,
            update={"messages": [AIMessage(content=f"Step Start Failure Agent Analysis:\n{final_report}")]}
        )
        
    except Exception as e:
        print(f"❌ Step Start Failure Agent error: {e}")
        return Command(
            goto=END,
            update={"messages": [AIMessage(content=f"Step Start Failure Agent: Analysis failed - {str(e)}")]}
        )
    
