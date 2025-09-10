"""
Runners Agent with Streaming Support - Updated with v1 logic
============================================================

Enhanced with improved logic from v1 and streaming callbacks for real-time output.
"""

import re
import json
import os
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Literal, Tuple
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import MessagesState, END
from langgraph.types import Command
from pydantic import BaseModel

# Import tools
from tools.kusto_query_tool import kusto_tool
from tools.azure_cli_tool import azure_cli_tool

# Import streaming callbacks
from streaming.callbacks import get_current_callbacks

# Load environment variables
load_dotenv()

# Initialize Azure OpenAI model for AI analysis
model = AzureChatOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
)

# Valid resource groups and runner types
valid_regions = [
    "australiaeast", "australiasoutheast", "brazilsouth", "canadacentral", 
    "canadaeast", "centralindia", "centralus", "centraluseuap", "chinaeast2", 
    "chinaeast3", "chinanorth3", "eastasia", "eastus2euap", "eastus2", "eastus",
    "francecentral", "germanywestcentral", "israelcentral", "italynorth", 
    "japaneast", "japanwest", "jioindiawest", "koreacentral", "northcentralus", 
    "northeurope", "norwayeast", "polandcentral", "qatarcentral", "southafricanorth", 
    "southcentralus", "southeastasia", "southindia", "spaincentral", "swedencentral", 
    "switzerlandnorth", "switzerlandwest", "uaenorth", "uksouth", "ukwest", 
    "usgovarizona", "usgovvirginia", "westcentralus", "westeurope", "westus3", 
    "westus2", "westus"
]

valid_runner_types = [
    "pipeline-runner", "pipeline-mfe-runner", "promptflow-runner", 
    "sdk-cli-v2-pipeline-cli-runner", "sdk-cli-v2-pipeline-sdk-runner", 
    "sdk-cli-v2-pipelines-schedule-runner", "sdk-cli-v2-schedule-sdk-runner"
]

valid_runner_types_mapping = {
    "PipelineRunner":"pipeline-runner",
    "PipelineMFERunner":"pipeline-mfe-runner",
    "PromptFlow":"promptflow-runner",
    "SDKV2PipelineRunner":"sdk-cli-v2-pipeline-sdk-runner",
    "CLIV2PipelineRunner":"sdk-cli-v2-pipeline-cli-runner",
    "SDKV2ScheduleRunner":"sdk-cli-v2-schedule-sdk-runner",
    "CLIV2ScheduleRunner":"sdk-cli-v2-pipelines-schedule-sdk-runner"
}

class RunnerAnalysis(BaseModel):
    """Structure for runner analysis results"""
    resource_group: str
    runner_type: str
    test_name: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None

class LogAnalysis(BaseModel):
    """Structure for runner log analysis results (aligned with v1)"""
    error_summary: str
    error_patterns: List[str]
    recommended_action: str
    confidence_score: float

class RunnerAgent:
    """Agent for analyzing runner incidents with streaming support - Thread-safe implementation"""
    
    def __init__(self, session_id: str = None):
        self.model = model
        self.session_id = session_id or str(__import__('uuid').uuid4())[:8]
        # Create dedicated logger for this instance
        self._log_prefix = f"[Session {self.session_id}]"
    
    def _log(self, message: str):
        """Thread-safe logging with session prefix"""
        print(f"{self._log_prefix} {message}")
    
    def truncate_text(self, text: str, max_length: int = 1000) -> str:
        """Return only the last max_length characters (most recent part) with a prefix marker.

        Rationale: For logs / status JSON the most recent lines near the end are usually
        the most relevant for diagnosis. We keep exactly the tail portion without
        attempting sentence-boundary alignment (simpler & deterministic).
        """
        if not text or len(text) <= max_length:
            return text
        tail = text[-max_length:]
        return f"...[truncated tail]...\n{tail}"
    
    def extract_runner_info(self, incident_title: str) -> RunnerAnalysis:
        """
        Extract resource group and runner type from incident title using LLM
        
        Args:
            incident_title: Incident title
            
        Returns:
            RunnerAnalysis: Extracted information
        """
        # Truncate potentially long fields to avoid token limits
        title = self.truncate_text(incident_title, 500)

        prompt = f"""
        You are an expert at analyzing Azure incident reports to extract runner container information.
        
        Given the following incident title:
        {title}
        
        Please extract:
        1. **Region**: Look for Azure regions like westus, eastus, centralus, etc.
        2. **Runner Type**: Identify the runner type from these options:
           - pipeline-runner (for Pipeline/PipelineRunner)
           - pipeline-mfe-runner (for PipelineMFE/PipelineMFERunner)
           - promptflow-runner (for PromptFlow/Promptflow)
           - sdk-cli-v2-pipeline-cli-runner (for CLIV2Pipeline)
           - sdk-cli-v2-pipeline-sdk-runner (for SDKV2Pipeline)
           - sdk-cli-v2-pipelines-schedule-runner (for CLIV2Schedule)
           - sdk-cli-v2-schedule-sdk-runner (for SDKV2Schedule)
        3. **Test Name**: Extract test name patterns like test_xxx, TestClass.test_method, etc.
        4. **Time Range**: Look for time patterns like "from X to Y" or specific timestamps
        
        Valid regions: {', '.join(valid_regions[:10])}... (and others)
        
        Return JSON format:
        {{
            "region": "region_name",
            "runner_type": "runner_type_name",
            "test_name": "extracted_test_name or null",
            "start_time": "ISO8601_start_time or null",
            "end_time": "ISO8601_end_time or null"
        }}
        
        DO NOT use default values - if you cannot find clear indicators, set the value to None
        """
        
        try:
            response = self.model.invoke([HumanMessage(content=prompt)])
            response_text = response.content.strip()
            
            # Clean up response if wrapped in code blocks
            if response_text.startswith('```json'):
                response_text = response_text[7:-3].strip()
            elif response_text.startswith('```'):
                response_text = response_text[3:-3].strip()
            
            result = json.loads(response_text)
            
            # Extract and validate results
            region = result.get("region", "westus")
            runner_type = result.get("runner_type", "pipeline-runner")
            test_name = result.get("test_name")
            start_time = result.get("start_time")
            end_time = result.get("end_time")
            
            # Ensure region is valid
            if region not in valid_regions:
                region = "westus"  # fallback
            
            # Ensure runner type is valid
            if runner_type not in valid_runner_types:
                runner_type = "pipeline-runner"  # fallback
            
            return RunnerAnalysis(
                resource_group=f"runners-{region}",
                runner_type=runner_type,
                test_name=test_name,
                start_time=start_time,
                end_time=end_time
            )
            
        except Exception as e:
            print(f"⚠️ AI extraction failed, using fallback: {e}")
            # Fallback to simple pattern matching
            return self._fallback_extraction(incident_title)
    
    def _fallback_extraction(self, incident_title: str) -> RunnerAnalysis:
        """Enhanced fallback extraction using precise patterns based on real ticket formats"""
        
        # Extract runner type first (most reliable pattern)
        runner_type = "pipeline-runner"  # default
        runner_type_patterns = [
            (r'\[PipelineMFERunner\]', "pipeline-mfe-runner"),
            (r'\[PipelineRunner\]', "pipeline-runner"),
            (r'\[SDKV2PipelineRunner\]', "sdk-cli-v2-pipeline-sdk-runner"),
            (r'\[CLIV2PipelineRunner\]', "sdk-cli-v2-pipeline-cli-runner"),
            (r'\[SDKV2ScheduleRunner\]', "sdk-cli-v2-schedule-sdk-runner"),
            (r'\[CLIV2ScheduleRunner\]', "sdk-cli-v2-pipelines-schedule-runner"),
            (r'PromptflowRunner|PromptFlowAutomaticRuntimeRunner', "promptflow-runner")
        ]
        
        for pattern, rtype in runner_type_patterns:
            if re.search(pattern, incident_title, re.IGNORECASE):
                runner_type = rtype
                break
        
        # Extract region with improved precision
        region = "westus"  # default
        region_patterns = [
            r'\[([a-z]+[0-9]*(?:euap)?)\]',  # [eastus2euap], [westus], etc.
            r'\[([a-z]+[0-9]*(?:euap)?)-aci\]',  # [eastus2euap-aci]
            r'{Region}([a-z]+[0-9]*(?:euap)?)',  # {Region}westus
            r'runner-test-([a-z]+[0-9]*(?:euap)?)'  # runner-test-westus
        ]
        
        for pattern in region_patterns:
            matches = re.findall(pattern, incident_title, re.IGNORECASE)
            for match in matches:
                if match in valid_regions:
                    region = match
                    break
            if region != "westus":  # found valid region
                break
        
        # Extract test name with comprehensive patterns
        test_name = None
        test_name_patterns = [
            # Complete test name patterns (keep full match including test_ prefix)
            (r'(test_[a-zA-Z0-9_]+)', 1),  # test_xxx - capture group 1
            (r'([A-Z][A-Za-z]+\.[A-Z][A-Za-z]+\.test_[a-zA-Z0-9_\[\]]+)', 1),  # PJ.TestClass.test_method[params] - capture group 1
            (r'[a-z0-9]+-aci_(test_[a-zA-Z0-9_]+)', 1),  # eastus2euap-aci_test_simple_async_run - capture group 1
            # Placeholder patterns
            (r'{Monitor\.Dimension\.test_name}', 0),  # Keep placeholder as-is
            (r'{test_name}', 0),  # Keep placeholder as-is
            # Special cases
            (r'Pipeline MFE runner heartbeat', -1),  # Special handling
        ]
        
        for pattern, group_index in test_name_patterns:
            match = re.search(pattern, incident_title, re.IGNORECASE)
            if match:
                if group_index == -1:  # Special case
                    test_name = "pipeline_mfe_heartbeat"
                elif group_index == 0:  # Full match
                    test_name = match.group(0)
                else:  # Use specific group
                    test_name = match.group(group_index)
                break
        
        # Extract time range if present with improved pattern to handle AM/PM
        start_time = None
        end_time = None
        # Pattern to match datetime formats including AM/PM
        time_pattern = r'from\s+(.*?(?:AM|PM|am|pm)?)\s+to\s+(.*?)(?:\s*$)'
        time_match = re.search(time_pattern, incident_title, re.IGNORECASE)
        if time_match:
            start_time = time_match.group(1).strip()
            end_time = time_match.group(2).strip()
        
        return RunnerAnalysis(
            resource_group=f"runners-{region}",
            runner_type=runner_type,
            test_name=test_name,
            start_time=start_time,
            end_time=end_time
        )

    def analyze_container_status(self, container_info: Dict[str, Any]) -> Dict[str, Any]:
        """
    Analyze container status with LLM and return a recommendation.
        """
        # container_text = json.dumps(container_info, indent=2)
        # if len(container_text) > 3000:
        #     container_text = self.truncate_text(container_text, 3000)
        containers = container_info.get("containers", [])

        prompt = f"""
        You are an expert in Azure Container Instances and need to analyze the following container status information to determine if a restart is needed.

        Container Information:
        {containers}

        Please analyze this container's status and determine:
        1. This container is in "Running" state or "Waiting" state or "Terminated" state.
        2. If this container is NOT in "Running" state, it NEEDS to be restarted.
        3. The reason for your decision, in which line of the container_text is the reason.
        4. The confidence of your decision.

        Please return the status of the container and the log around it as evidence. Evidence must be the quote from the container_text.

        Respond in JSON format with the following structure:
        {{
            "needs_restart": true/false,
            "reason": "the current status of the container is Running/Waiting/other state",
            "confidence": 0.0-1.0,
            "evidence": ["short quote of the container_text"]
        }}

        Only return the JSON, no additional text.
        """

        try:
            response = self.model.invoke([HumanMessage(content=prompt)])
            response_text = response.content.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:-3].strip()
            elif response_text.startswith('```'):
                response_text = response_text[3:-3].strip()

            ai_analysis = json.loads(response_text)
            required_fields = ["needs_restart", "reason", "confidence", "evidence"]
            if not all(field in ai_analysis for field in required_fields):
                raise ValueError(f"Missing required fields in AI response. Got: {list(ai_analysis.keys())}, Expected: {required_fields}")

            return {
                "success": True,
                "needs_restart": ai_analysis["needs_restart"],
                "reason": ai_analysis["reason"],
                "confidence": ai_analysis["confidence"],
                "ai_analysis": True,
                "evidence": ai_analysis.get("evidence", [])
            }

        except Exception as e:
            print(f"⚠️ AI analysis failed: {e}")
            # Fallback simple heuristic
            text = json.dumps(container_info, indent=2)
            if len(text) > 3000:
                text = self.truncate_text(text, 3000)
            fallback_needs_restart = ("Waiting" in text) and ("Running" not in text)
            return {
                "success": True,
                "needs_restart": fallback_needs_restart,
                "reason": "AI analysis failed, using fallback logic",
                "confidence": 0.5,
                "ai_analysis": False,
                "ai_error": str(e),
                "evidence": []
            }

    async def check_container_needs_restart(self, container_name: str, resource_group: str, subscription: str) -> Dict[str, Any]:
        """
        Fetch container details and analyze status to decide restart.
        Enhanced with timeout and error handling for high concurrency.
        """
        try:
            # Add timeout to prevent hanging in high concurrency scenarios
            self._log(f"Checking container status for {container_name}")
            container_details = await asyncio.wait_for(
                azure_cli_tool.show_container(container_name, resource_group, subscription),
                timeout=30.0  # 30 second timeout
            )
            
            if not container_details:
                self._log(f"Failed to get container details for {container_name}")
                return {
                    "success": False,
                    "needs_restart": False,
                    "reason": "Failed to get container details",
                    "session_id": self.session_id
                }
            
            result = self.analyze_container_status(container_details)
            result["container_info"] = container_details
            result["session_id"] = self.session_id
            self._log(f"Container status analysis complete for {container_name}")
            return result
            
        except asyncio.TimeoutError:
            self._log(f"Timeout while checking container {container_name}")
            return {
                "success": False,
                "needs_restart": False,
                "reason": "Timeout while checking container status",
                "session_id": self.session_id
            }
        except Exception as e:
            self._log(f"Error checking container {container_name}: {str(e)}")
            return {
                "success": False,
                "needs_restart": False,
                "reason": f"Error checking container: {str(e)}",
                "session_id": self.session_id
            }

    async def analyze_runner_logs(self, test_name: Optional[str], runner_type: str, region: str, explicit_start: Optional[str] = None, explicit_end: Optional[str] = None) -> Optional[LogAnalysis]:
        """
        Simplified runner log analysis with enhanced error handling and timeouts
        """
        try:
            self._log(f"Starting log analysis for {runner_type} test: {test_name}")
            
            # Simple time range: use explicit times or default to last 48 hours
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=48)  # default
            
            if explicit_start and explicit_end:
                try:
                    start_time = datetime.fromisoformat(explicit_start.replace('Z', '+00:00'))
                    end_time = datetime.fromisoformat(explicit_end.replace('Z', '+00:00'))
                except:
                    self._log("Failed to parse explicit time range, using defaults")
                    pass  # use defaults
            
            self._log(f"Analyzing {runner_type} logs from {start_time.isoformat()} to {end_time.isoformat()}")
            
            # Add timeout for log queries
            logs = await asyncio.wait_for(
                kusto_tool.query_runner_logs(runner_type, start_time, end_time, region, test_name),
                timeout=60.0  # 60 second timeout for log queries
            )

            if not logs:
                self._log("No logs found for analysis")
                return None

            # Simple log summary
            log_summary = f"Found {len(logs)} log entries for {test_name or 'unknown test'} in {runner_type}:\n\n"
            
            # Show first 3 logs only
            for i, log in enumerate(logs[:3]):
                log_summary += f"Log {i+1}:\n"
                for key, value in log.items():
                    if value:
                        val = str(value)[:500]  # truncate long values
                        log_summary += f"  {key}: {val}\n"
                log_summary += "\n"
            
            if len(logs) > 3:
                log_summary += f"... and {len(logs) - 3} more entries\n"

            # Simple AI analysis with timeout
            analysis_prompt = f"""
            Analyze these {runner_type} logs for issues:

            {log_summary}

            Provide:
            1. error_summary: Brief summary of any errors found
            2. error_patterns: List of error patterns (max 3)
            3. recommended_action: What should be done
            4. confidence_score: Your confidence (0.0-1.0)
            """

            response = await asyncio.wait_for(
                self.model.with_structured_output(LogAnalysis).ainvoke([
                    HumanMessage(content=analysis_prompt)
                ]),
                timeout=30.0  # 30 second timeout for AI analysis
            )
            
            self._log(f"Log analysis completed successfully")
            return response

        except asyncio.TimeoutError:
            self._log(f"Timeout during log analysis for {runner_type}")
            return None
        except Exception as e:
            self._log(f"Failed to analyze runner logs: {e}")
            return None

async def runners_agent_with_streaming(state: MessagesState) -> Command[Literal["__end__"]]:
    """
    Runners Agent: Specialized in managing runner containers with streaming support
    Enhanced for high concurrency scenarios with session-based callbacks
    """
    callbacks = get_current_callbacks()
    
    # Generate unique session identifier for this execution
    import uuid
    session_id = str(uuid.uuid4())[:8]
    
    try:
        if callbacks:
            await callbacks.on_agent_start("Runners Agent", f"🏃 Starting runner container management analysis (Session: {session_id})")
        
        print(f"\n[Session {session_id}] " + "="*60)
        print(f"🏃 Runners Agent: Processing runner container management...")
        print("="*60)
        
        # Get incident ID from messages
        user_input = ""
        for msg in reversed(state["messages"]):
            if isinstance(msg, HumanMessage):
                user_input = msg.content
                break
        
        # Extract incident ID
        incident_id = kusto_tool.extract_incident_id(user_input)
        incident_title = kusto_tool.extract_incident_title(user_input)
        
        if not incident_id:
            error_msg = f"Runners Agent (Session {session_id}): No incident ID found in input"
            if callbacks:
                await callbacks.on_agent_end("Runners Agent", error_msg)
            return Command(
                goto=END,
                update={"messages": [AIMessage(content=error_msg)]}
            )
        
        # Initialize async tools if needed (thread-safe check)
        if azure_cli_tool.available is None:
            try:
                await azure_cli_tool.async_init()
            except Exception as init_error:
                error_msg = f"Runners Agent (Session {session_id}): Failed to initialize Azure CLI tool - {str(init_error)}"
                if callbacks:
                    await callbacks.on_agent_end("Runners Agent", error_msg)
                return Command(
                    goto=END,
                    update={"messages": [AIMessage(content=error_msg)]}
                )
        
        # Get incident details early so it's available in all branches
        print(f"\n[Session {session_id}] 🔍 Getting incident details...")
        if callbacks:
            await callbacks.on_agent_message("Runners Agent", f"🔍 Retrieving incident details for {incident_id}...")
        
        try:
            incident_details = await kusto_tool.query_incident_details(incident_id)
        except Exception as query_error:
            error_msg = f"Runners Agent (Session {session_id}): Failed to query incident details - {str(query_error)}"
            if callbacks:
                await callbacks.on_agent_end("Runners Agent", error_msg)
            return Command(
                goto=END,
                update={"messages": [AIMessage(content=error_msg)]}
            )

        if not incident_details or incident_details.get('Title') == None:
            error_msg = f"Runners Agent (Session {session_id}): Unable to retrieve details for incident {incident_id}"
            if callbacks:
                await callbacks.on_agent_end("Runners Agent", error_msg)
            return Command(
                goto=END,
                update={"messages": [AIMessage(content=error_msg)]}
            )
        
        # Step 1: Extract all runner information with single AI call
        print(f"\n[Session {session_id}] 🔍 Step 1: Extracting all runner information with AI...")
        if callbacks:
            await callbacks.on_agent_message("Runners Agent", "🔍 Step 1: Extracting runner information, test name, and time range...")
        
        # Create separate RunnerAgent instance for this session to avoid shared state
        runner = RunnerAgent(session_id=session_id)
        try:
            runner_analysis = runner.extract_runner_info(incident_title)
            if callbacks:
                await callbacks.on_agent_message("Runners Agent", f"✅ Extracted: {runner_analysis.runner_type} in {runner_analysis.resource_group}, test: {runner_analysis.test_name or 'N/A'}")
        except Exception as e:
            print(f"[Session {session_id}] ❌ Failed to extract runner information: {e}")
            error_msg = f"Runners Agent (Session {session_id}): Failed to extract runner information - {str(e)}"
            if callbacks:
                await callbacks.on_agent_end("Runners Agent", error_msg)
            return Command(
                goto=END,
                update={"messages": [AIMessage(content=error_msg)]}
            )
        
        # Step 2: Check container status
        print(f"\n[Session {session_id}] 🔍 Step 2: Checking container status...")
        if callbacks:
            await callbacks.on_agent_message("Runners Agent", "🔍 Step 2: Checking container status...")

        # Step 2.1: Find container name
        print(f"\n[Session {session_id}] 🔍 Step 2.1: Finding container name...")
        if callbacks:
            await callbacks.on_agent_message("Runners Agent", f"🔍 Step 2.1: Finding container for {runner_analysis.runner_type}...")
        
        subscription = "fecca740-22f4-4154-81d8-6ab94324e349"  # Default subscription for runners
        try:
            container_name = await azure_cli_tool.find_container_by_type(runner_analysis.resource_group, runner_analysis.runner_type, subscription)
        except Exception as find_error:
            error_msg = f"Runners Agent (Session {session_id}): Failed to find container - {str(find_error)}"
            if callbacks:
                await callbacks.on_agent_end("Runners Agent", error_msg)
            return Command(
                goto=END,
                update={"messages": [AIMessage(content=error_msg)]}
            )
        
        if not container_name:
            error_msg = f"Runners Agent (Session {session_id}): No container found for runner type '{runner_analysis.runner_type}' in resource group '{runner_analysis.resource_group}'"
            if callbacks:
                await callbacks.on_agent_end("Runners Agent", error_msg)
            return Command(
                goto=END,
                update={"messages": [AIMessage(content=error_msg)]}
            )
        
        if callbacks:
            await callbacks.on_agent_message("Runners Agent", f"✅ Found container: {container_name}")
        
        # Step 2.2: Check container status using AI analysis
        print(f"\n[Session {session_id}] 📊 Step 2.2: Checking container status with AI analysis...")
        if callbacks:
            await callbacks.on_agent_message("Runners Agent", "📊 Step 2.2: Analyzing container status with AI...")

        try:
            # Create new instance for thread safety
            status_analyzer = RunnerAgent(session_id=session_id)
            status_result = await status_analyzer.check_container_needs_restart(container_name, runner_analysis.resource_group, subscription)
        except Exception as status_error:
            error_msg = f"Runners Agent (Session {session_id}): Failed to check container status - {str(status_error)}"
            if callbacks:
                await callbacks.on_agent_end("Runners Agent", error_msg)
            return Command(
                goto=END,
                update={"messages": [AIMessage(content=error_msg)]}
            )

        if callbacks:
            # Emit an explicit decision message for clarity 
            decision_text = "AI decision: restart is REQUIRED" if status_result.get("needs_restart") else "AI decision: restart is NOT needed"
            reason = status_result.get("reason", "Unknown reason")
            evidence = status_result.get("evidence", [])
            await callbacks.on_agent_message("Runners Agent", f"{decision_text}, reason: {reason}, evidence: {evidence}")

        if not status_result.get("success", False):
            error_msg = f"Runners Agent (Session {session_id}): Failed to check container status: {status_result.get('reason', 'Unknown error')}"
            if callbacks:
                await callbacks.on_agent_end("Runners Agent", error_msg)
            return Command(
                goto=END,
                update={"messages": [AIMessage(content=error_msg)]}
            )

        # Step 3: Restart if needed, otherwise analyze logs
        restart_attempted = False
        restart_success = False
        log_analysis: Optional[LogAnalysis] = None

        if status_result.get("needs_restart"):
            print(f"\n[Session {session_id}] 🔄 Step 3: Container restart needed, proceeding automatically...")
            restart_attempted = True
            
            if callbacks:
                await callbacks.on_agent_message("Runners Agent", f"⚠️ Container {container_name} needs restart. Proceeding automatically...")
            
            print(f"[Session {session_id}] Starting container restart for {container_name}...")
            try:
                restart_success = await azure_cli_tool.restart_container(container_name, runner_analysis.resource_group, subscription)
                print(f"[Session {session_id}] 🔄 Container restart result: {restart_success}")
            except Exception as restart_error:
                print(f"[Session {session_id}] ❌ Container restart failed: {restart_error}")
                restart_success = False
            
            if callbacks:
                if restart_success:
                    await callbacks.on_agent_message("Runners Agent", f"✅ Container {container_name} restarted successfully")
                else:
                    await callbacks.on_agent_message("Runners Agent", f"❌ Timeout. Checking container status...")
                    try:
                        status_analyzer = RunnerAgent(session_id=session_id)
                        status_result = await status_analyzer.check_container_needs_restart(container_name, runner_analysis.resource_group, subscription)

                        if status_result.get("needs_restart"):
                            await callbacks.on_agent_message("Runners Agent", f"❌ Failed to restart container {container_name}")
                        else:
                            restart_success = True
                            await callbacks.on_agent_message("Runners Agent", f"✅ Container {container_name} restarted successfully")
                    except Exception as recheck_error:
                        await callbacks.on_agent_message("Runners Agent", f"❌ Failed to recheck container status: {str(recheck_error)}")

        else:
            print(f"\n[Session {session_id}] ✅ Step 3: Container restart not needed")
            if callbacks:
                await callbacks.on_agent_message("Runners Agent", "✅ Step 3: Container status is healthy, no restart needed")

            # Use the test name extracted in Step 1
            test_name = runner_analysis.test_name

            if test_name:
                print(f"\n[Session {session_id}] 📊 Step 5b: Analyzing runner logs for test: {test_name}")
                if callbacks:
                    await callbacks.on_agent_message("Runners Agent", f"📊 Analyzing {runner_analysis.runner_type} logs for test: {test_name}")
                # Extract region from resource_group (format: "runners-{region}")
                region = runner_analysis.resource_group.replace("runners-", "") if runner_analysis.resource_group.startswith("runners-") else "westus"
                
                try:
                    # Create new instance for thread safety
                    log_analyzer = RunnerAgent(session_id=session_id)
                    log_analysis = await log_analyzer.analyze_runner_logs(
                        test_name,
                        runner_analysis.runner_type,
                        region,
                        explicit_start=runner_analysis.start_time,
                        explicit_end=runner_analysis.end_time
                    )
                    if callbacks and log_analysis:
                        await callbacks.on_agent_message("Runners Agent", f"📊 Log analysis complete: {log_analysis.error_summary}")
                except Exception as log_error:
                    print(f"[Session {session_id}] ⚠️ Log analysis failed: {log_error}")
                    if callbacks:
                        await callbacks.on_agent_message("Runners Agent", f"⚠️ Log analysis failed: {str(log_error)}")
            else:
                print(f"\n[Session {session_id}] ⚠️ Cannot analyze logs: test_name extraction failed")
                if callbacks:
                    await callbacks.on_agent_message("Runners Agent", "⚠️ Cannot analyze logs: test name extraction failed")

        # Generate final report
        if callbacks:
            await callbacks.on_agent_message("Runners Agent", "📋 Generating comprehensive analysis report...")
        
        try:
            report = generate_runners_report(
                incident_details,
                runner_analysis,
                container_name,
                status_result,
                restart_attempted,
                restart_success,
                log_analysis,
                session_id  # Add session ID to report
            )
        except Exception as report_error:
            error_msg = f"Runners Agent (Session {session_id}): Failed to generate report - {str(report_error)}"
            if callbacks:
                await callbacks.on_agent_end("Runners Agent", error_msg)
            return Command(
                goto=END,
                update={"messages": [AIMessage(content=error_msg)]}
            )

        if callbacks:
            await callbacks.on_agent_message("Runners Agent", f"✅ Analysis completed successfully! Report generated for session {session_id}.")
            await callbacks.on_agent_end("Runners Agent", f"Analysis completed successfully (Session: {session_id})")

        print(f"\n[Session {session_id}] ✅ Runners Agent analysis completed!")
        return Command(
            goto=END,
            update={"messages": [AIMessage(content=report)]}
        )
        
    except Exception as e:
        print(f"[Session {session_id}] ❌ Runners Agent error: {e}")
        error_msg = f"Runners Agent (Session {session_id}): Analysis failed - {str(e)}"
        if callbacks:
            await callbacks.on_agent_end("Runners Agent", error_msg)
        return Command(
            goto=END,
            update={"messages": [AIMessage(content=error_msg)]}
        )

def generate_runners_report(
    incident_details: Dict[str, Any],
    runner_analysis: RunnerAnalysis,
    container_name: str,
    status_result: Dict[str, Any],
    restart_attempted: bool,
    restart_success: bool,
    log_analysis: Optional[LogAnalysis] = None,
    session_id: str = "unknown"
) -> str:
    """Generate a simplified comprehensive report with session tracking."""
    incident_id = (
        incident_details.get('IncidentId')
        or incident_details.get('incident_id')
        or 'Unknown'
    )
    title = (
        incident_details.get('Title')
        or incident_details.get('IncidentTitle')
        or incident_details.get('title')
        or 'Unknown'
    )
    summary = incident_details.get('Summary') or incident_details.get('summary') or 'No summary available'

    # Precompute evidence block to avoid backslashes in f-string expression
    _evidence_list = status_result.get('evidence') or []
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    report = f"""# 🏃 **RUNNERS AGENT ANALYSIS REPORT**

---

## **🔍 Session Information:**
- **Session ID:** {session_id}
- **Timestamp:** {timestamp}
- **Agent:** Runners Agent (High-Concurrency Mode)

## **📋 Incident Information:**

- **Incident ID:** {incident_id}
- **Title:** {title}
- **Summary:** {summary}
- **Resource Group:** {runner_analysis.resource_group}
- **Runner Type:** {runner_analysis.runner_type}
- **Test Name:** {runner_analysis.test_name or 'N/A'}
- **Time Range:** {runner_analysis.start_time or 'N/A'} to {runner_analysis.end_time or 'N/A'}

## **📦 Container Information:**

- **Container Name:** {container_name}
- **Status Check:** {'✅ Success' if status_result.get('success') else '❌ Failed'}
- **Needs Restart:** {'✅ Yes' if status_result.get('needs_restart') else '❌ No'}
- **AI Analysis:** {'✅ Success' if status_result.get('ai_analysis', False) else '❌ Failed/Fallback'}
- **Confidence:** {status_result.get('confidence', 0.5):.1%}
- **Analysis Reason:** {status_result.get('reason', 'N/A')}
- **Evidence (sample):** {_evidence_list}

"""

    if restart_attempted:
        report += f"""
        
## **🔄 Container Restart Action:**
- **Result:** {'✅ Success' if restart_success else '❌ Failed'}

"""
    else:
        report += f"""
        
## **🔄 Container Restart Action:**
- **Status:** No restart needed

"""

        if log_analysis:
            report += f"""


## **📊 Runner Log Analysis:**

- **Error Summary:** {log_analysis.error_summary}
- **Error Patterns:** {', '.join(log_analysis.error_patterns)}
- **Recommended Action:** {log_analysis.recommended_action}
- **Analysis Confidence:** {log_analysis.confidence_score:.1%}

"""
        else:
            report += f"""


## **📊 Runner Log Analysis:**

- **Status:** No error logs found or analysis unavailable

"""

    report += f"""
---
**🎯 Analysis completed for session {session_id} with enhanced concurrency support**
"""

    return report

# Note: In v2-webapp, we use runners_agent_with_streaming directly as an async node
# No need for synchronous wrapper since LangGraph supports async nodes
