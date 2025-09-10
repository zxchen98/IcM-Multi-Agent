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
    pattern_similarity: float  # Similarity to known patterns
    reasoning: str  # AI reasoning for the match

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
    
    async def analyze_incident_and_match_tsg(self, incident_details: Dict[str, Any]) -> TSGMatchResult:
        """
        Match incident against TSG rules to determine actions
        
        Args:
            incident_details: Complete incident information from Kusto
            
        Returns:
            TSGMatchResult: AI-matched TSG results with confidence metrics
        """
        # Prepare known TSG patterns for AI analysis
        known_patterns = []
        for rule in self.tsg_rules:
            known_patterns.append({
                "pattern": rule["pattern"],
                "failed_step": rule["failed_step"],
                "description": rule["description"],
                "action": rule["action"],
                "transfer_to": rule["transfer_to"]
            })
        
        incident_summary = f"""
        - ID: {incident_details.get('IncidentId', 'Unknown')}
        - Title: {incident_details.get('Title', 'Unknown')}
        - Summary: {incident_details.get('Summary', 'No summary')}
        - Description: {incident_details.get('MergedText', 'No description')}
        - Severity: {incident_details.get('Severity', 'Unknown')}
        """
        
        tsg_analysis_prompt = f"""
        You are an expert step start failure incident analyzer. Analyze the incident directly against known TSG patterns and provide comprehensive diagnosis.

        INCIDENT INFORMATION:
        {incident_summary}

        KNOWN TSG PATTERNS:
        {chr(10).join([f"- Pattern: {p['pattern']}" + chr(10) + f"  Failed Step: {p['failed_step']}" + chr(10) + f"  Description: {p['description']}" + chr(10) + f"  Action: {p['action']}" + chr(10) + f"  Transfer To: {p['transfer_to']}" + chr(10) for p in known_patterns])}

        INSTRUCTIONS:
        1. Directly analyze incident symptoms, error messages, and log content
        2. Compare and match against known TSG patterns based on:
           - Error message keyword matching
           - Semantic similarity of failure symptoms
           - Technology stack and component matching
           - Error occurrence context environment
        3. Provide confidence scoring (0.0-1.0):
           - match_confidence: Overall TSG matching confidence
           - pattern_similarity: Similarity to known patterns
        4. If no strong match (confidence < 0.6), suggest general handling approach
        5. Provide detailed analysis reasoning process

        RESPONSE FORMAT (JSON):
        {{
            "matched_tsg": "Matched TSG description or 'General step start failure handling'",
            "action_required": "Specific action to take",
            "transfer_to": "Team to transfer to (e.g.: 'AEther/AEther', 'pipeline_team')",
            "match_confidence": 0.0-1.0,
            "pattern_similarity": 0.0-1.0,
            "reasoning": "Detailed explanation of why this TSG was selected and confidence reasoning",
            "root_cause_summary": "Brief root cause analysis summary"
        }}
        """
        
        try:
            print("🤖 AI analyzing incident and matching TSG...")
            response = await model.ainvoke([HumanMessage(content=tsg_analysis_prompt)])
            
            # Parse AI response
            import json
            import re
            
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
            if json_match:
                ai_result = json.loads(json_match.group())
                
                result = TSGMatchResult(
                    matched_tsg=ai_result.get("matched_tsg", "General step start failure handling"),
                    action_required=ai_result.get("action_required", "Manual investigation required"),
                    transfer_to=ai_result.get("transfer_to", "pipeline_team"),
                    match_confidence=float(ai_result.get("match_confidence", 0.3)),
                    pattern_similarity=float(ai_result.get("pattern_similarity", 0.0)),
                    reasoning=ai_result.get("reasoning", "AI analysis completed")
                )
                
                print(f"🎯 AI Direct TSG Match: {result.matched_tsg}")
                print(f"📊 Confidence: {result.match_confidence:.2f}, Similarity: {result.pattern_similarity:.2f}")
                print(f"💡 Reasoning: {result.reasoning}")
                
                # Save root cause analysis summary for report
                self.root_cause_summary = ai_result.get("root_cause_summary", "AI direct analysis completed")
                
                return result
            else:
                raise ValueError("Could not parse AI response as JSON")
                
        except Exception as e:
            print(f"❌ AI direct TSG analysis failed: {e}")
            # Fallback to simple rule-based matching
            return await self._fallback_incident_matching(incident_details)
    
    async def _fallback_incident_matching(self, incident_details: Dict[str, Any]) -> TSGMatchResult:
        """Fallback rule-based incident matching when AI fails"""
        print("🔄 Using fallback rule-based incident matching...")
        
        # Simple keyword matching
        title = incident_details.get('Title', '').lower()
        summary = incident_details.get('Summary', '').lower()
        description = incident_details.get('MergedText', '').lower()
        
        combined_text = f"{title} {summary} {description}"
        
        for rule in self.tsg_rules:
            pattern_keywords = rule["pattern"].lower().split()
            matches = sum(1 for keyword in pattern_keywords if keyword in combined_text)
            
            if matches >= len(pattern_keywords) * 0.5:  # At least 50% keyword match
                print(f"✅ Fallback rule matched: {rule['description']}")
                return TSGMatchResult(
                    matched_tsg=rule["description"],
                    action_required=rule["action"],
                    transfer_to=rule["transfer_to"],
                    match_confidence=0.6,  # Medium confidence
                    pattern_similarity=0.5,
                    reasoning="Using fallback keyword matching rule"
                )
        
        # No matching rules found
        print("📋 No TSG rules matched in fallback mode")
        return TSGMatchResult(
            matched_tsg="General step start failure handling",
            action_required="Manual investigation required",
            transfer_to="pipeline_team",
            match_confidence=0.3,
            pattern_similarity=0.0,
            reasoning="No specific TSG pattern found in fallback mode, using general handling approach"
        )

    async def _fallback_tsg_matching(self, root_cause_analysis: RootCauseAnalysis) -> TSGMatchResult:
        """Fallback rule-based TSG matching when AI fails"""
        print("🔄 Using fallback rule-based TSG matching...")
        
        for rule in self.tsg_rules:
            if rule["failed_step"].lower() == root_cause_analysis.failed_step.lower() \
                and (root_cause_analysis.step_cause.lower() in rule["pattern"].lower() \
                     or root_cause_analysis.immediate_cause.lower() in rule["pattern"].lower()):
                print(f"✅ Fallback TSG Rule matched: {rule['description']}")
                return TSGMatchResult(
                    matched_tsg=rule["description"],
                    action_required=rule["action"],
                    transfer_to=rule["transfer_to"],
                    match_confidence=0.8,  # Lower confidence for rule-based
                    pattern_similarity=0.7,
                    reasoning="Matched using fallback rule-based pattern matching"
                )
        
        # No specific TSG rule matched
        print("📋 No TSG rule matched in fallback mode")
        return TSGMatchResult(
            matched_tsg="General step start failure handling",
            action_required="Manual investigation required",
            transfer_to="pipeline_team",
            match_confidence=0.3,
            pattern_similarity=0.0,
            reasoning="No specific TSG pattern matched, using general handling approach"
        )
    
    def generate_final_report(self, incident_details: Dict[str, Any], 
                            tsg_result: TSGMatchResult) -> str:
        """
        Generate comprehensive final report with recommendations
        
        Args:
            incident_details: Original incident data
            tsg_result: TSG matching results (includes root cause analysis summary)
            
        Returns:
            str: Formatted final report
        """
        report = f"""
🎫 **STEP START FAILURE ANALYSIS REPORT**
================================================

📋 **Incident Information:**
- Incident ID: {incident_details.get('IncidentId', 'Unknown')}
- Title: {incident_details.get('Title', 'Unknown')}
- Severity: {incident_details.get('Severity', 'Unknown')}

🔍 **AI Root Cause Analysis Summary:**
{getattr(self, 'root_cause_summary', 'AI direct analysis completed')}

⚡ **AI TSG Analysis:**
- **Matched Rule:** {tsg_result.matched_tsg}
- **Match Confidence:** {tsg_result.match_confidence:.1%}
- **Pattern Similarity:** {tsg_result.pattern_similarity:.1%}
- **AI Reasoning:** {tsg_result.reasoning}

🎯 **Recommended Action:**
- **Action:** {tsg_result.action_required}
- **Transfer To:** {tsg_result.transfer_to}

================================================
"""
        return report

async def step_start_failure_agent_with_streaming(state: MessagesState) -> Command[Literal["__end__"]]:
    """
    Step Start Failure Agent: Specialized in analyzing and resolving step start failure incidents
    """
    # Import streaming callbacks
    from streaming.callbacks import get_current_callbacks
    callbacks = get_current_callbacks()
    
    if callbacks:
        await callbacks.on_agent_start("Step Start Failure Agent", "🔧 Analyzing step start failure incident")
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
        error_msg = "Step Start Failure Agent: No incident ID found for analysis."
        if callbacks:
            await callbacks.on_agent_end("Step Start Failure Agent", error_msg)
        return Command(
            goto=END,
            update={"messages": [AIMessage(content=error_msg)]}
        )
    
    print("\n\n")
    print("=" * 60)
    print(f"🔧 Step Start Failure Agent analyzing incident: {incident_id}")
    
    if callbacks:
        await callbacks.on_agent_message("Step Start Failure Agent", f"🔧 Analyzing incident {incident_id}")
    
    try:
        # Initialize analyzer
        analyzer = StepStartFailureAnalyzer()
        
        # Step 1: Query detailed incident information
        print("\n📋 Step 1: Querying incident details...")
        incident_details = await kusto_tool.query_incident_details(incident_id)
        
        if not incident_details or incident_details.get('title') == 'Unknown':
            error_msg = f"Step Start Failure Agent: Unable to retrieve details for incident {incident_id}"
            if callbacks:
                await callbacks.on_agent_end("Step Start Failure Agent", error_msg)
            return Command(
                goto=END,
                update={"messages": [AIMessage(content=error_msg)]}
            )
        
        # Step 2: Direct incident analysis and TSG matching (combined root cause analysis and TSG matching)
        print("\n🤖 Step 2: AI directly analyzing incident and matching TSG...")
        tsg_result = await analyzer.analyze_incident_and_match_tsg(incident_details)
        
        # Step 3: Generate Final Report
        print("\n📄 Step 3: Generating final report...")
        final_report = analyzer.generate_final_report(incident_details, tsg_result)
        
        print("\n✅ Step Start Failure analysis completed!")
        
        if callbacks:
            await callbacks.on_agent_end("Step Start Failure Agent", "Analysis completed successfully")
        
        return Command(
            goto=END,
            update={"messages": [AIMessage(content=f"Step Start Failure Agent Analysis:\n{final_report}")]}
        )
        
    except Exception as e:
        print(f"❌ Step Start Failure Agent error: {e}")
        error_msg = f"Step Start Failure Agent: Analysis failed - {str(e)}"
        if callbacks:
            await callbacks.on_agent_end("Step Start Failure Agent", error_msg)
        return Command(
            goto=END,
            update={"messages": [AIMessage(content=error_msg)]}
        )
    
