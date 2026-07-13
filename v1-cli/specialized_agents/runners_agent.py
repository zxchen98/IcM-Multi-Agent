import os
import re
import json
from datetime import datetime, timedelta
from typing import Literal, Dict, Any, List, Optional
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from langgraph.types import Command
from langgraph.graph import END
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import MessagesState
from pydantic import BaseModel

# Import tools
from tools.kusto_query_tool import kusto_tool
from tools.azure_cli_tool import azure_cli_tool

# Load environment variables
load_dotenv()

# Initialize Azure OpenAI model
model = AzureChatOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
)

class RunnerAnalysis(BaseModel):
    """Structure for runner analysis results"""
    resource_group: str
    runner_type: str
    test_name: Optional[str] = None
    confidence_score: float
    extraction_reason: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None

class LogAnalysis(BaseModel):
    """Structure for runner log analysis results"""
    error_summary: str
    error_patterns: List[str]
    recommended_action: str
    confidence_score: float

class RunnerAgent:
    """Specialized agent for runner container management"""
    
    def __init__(self):
        self.model = model
    
    def truncate_text(self, text: str, max_chars: int = 5000) -> str:
        """
        Truncate text to avoid token limits, keeping the most recent/relevant part
        
        Args:
            text: Text to truncate
            max_chars: Maximum characters to keep
            
        Returns:
            Truncated text
        """
        if not text or len(text) <= max_chars:
            return text
        
        # Take the last max_chars characters to get the most recent information
        truncated = text[-max_chars:]
        
        # Try to start from a complete sentence or line
        # Look for common sentence/line breaks in the last part
        for delimiter in ['\n\n', '\n', '. ', '! ', '? ']:
            idx = truncated.find(delimiter)
            if idx > 100:  # Only if we have enough content after the delimiter
                truncated = truncated[idx + len(delimiter):]
                break
        
        return f"...[truncated]...\n{truncated}"
    
    def extract_runner_info(self, incident_title: str) -> RunnerAnalysis:
        """
        Extract resource group and runner type from incident details using LLM
        
        Args:
            incident_details: Complete incident information
            
        Returns:
            RunnerAnalysis: Extracted information
        """
        # Truncate potentially long fields to avoid token limits
        title = self.truncate_text(incident_title, 500)
        # Valid resource groups and runner types
        valid_regions = [
            "australiaeast", "australiasoutheast", "brazilsouth", "canadacentral", 
            "canadaeast", "centralindia", "centralus", "centraluseuap", "chinaeast2", 
            "chinaeast3", "chinanorth3", "eastasia", "eastus", "eastus2", "eastus2euap", 
            "francecentral", "germanywestcentral", "israelcentral", "italynorth", 
            "japaneast", "japanwest", "jioindiawest", "koreacentral", "northcentralus", 
            "northeurope", "norwayeast", "polandcentral", "qatarcentral", "southafricanorth", 
            "southcentralus", "southeastasia", "southindia", "spaincentral", "swedencentral", 
            "switzerlandnorth", "switzerlandwest", "uaenorth", "uksouth", "ukwest", 
            "usgovarizona", "usgovvirginia", "westcentralus", "westeurope", "westus", 
            "westus2", "westus3"
        ]
        
        valid_runner_types = [
            "pipeline-runner", "pipeline-mfe-runner", "promptflow-runner", 
            "sdk-cli-v2-pipeline-cli-runner", "sdk-cli-v2-pipeline-sdk-runner", 
            "sdk-cli-v2-pipelines-schedule-runner", "sdk-cli-v2-schedule-sdk-runner"
        ]
        
        prompt = f"""
        You are an expert at analyzing Azure incident reports to extract runner container information.
        
        Given the following incident title:
        {title}
        
        Please extract:
        1. Resource group (Azure region) - Look for region indicators like [westus], [eastus], [centralus], etc. in the title
        2. Runner type - Look for runner type indicators like pipeline-runner, pipeline-mfe-runner, etc.
        3. Test Name - Extract test name patterns like test_xxx, TestClass.test_method, etc.
        4. If present, the start and end time of the test run indicated by wording like "from <start> to <end>".
        
        Valid regions: {', '.join(valid_regions)}
        Valid runner types: {', '.join(valid_runner_types)}
        
        Respond in JSON format:
        {{
            "resource_group": "region_name",
            "runner_type": "runner_type_name", 
            "test_name": "extracted_test_name or null",
            "confidence_score": 0.0-1.0,
            "extraction_reason": "Brief explanation of how you identified these values",
            "start_time": "ISO8601 start time if available else null",
            "end_time": "ISO8601 end time if available else null"
        }}
        
        DO NOT use default values - if you cannot find clear indicators, set confidence_score to 0.0 and explain why.
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
            
            # Validate extracted values
            resource_group = result.get("resource_group")
            runner_type = result.get("runner_type")
            
            # Check if resource_group is valid, fallback to regex extraction if needed
            if not resource_group or resource_group not in valid_regions:
                # Try to use regex-extracted region if available
                raise ValueError(f"❌ Invalid or missing resource_group: '{resource_group}'. Valid regions: {valid_regions}")
            
            # Check if runner_type is valid
            if not runner_type or runner_type not in valid_runner_types:
                # Try to infer runner type from title
                if 'pipeline' in title.lower() or 'reliability' in title.lower():
                    runner_type = "pipeline-runner"
                    print(f"✅ Using inferred runner type: {runner_type}")
                else:
                    raise ValueError(f"❌ Invalid or missing runner_type: '{runner_type}'. Valid types: {valid_runner_types}")
            
            test_name = result.get("test_name") or None
            start_time = result.get("start_time") or None
            end_time = result.get("end_time") or None
            # Normalize times if provided
            def _norm(t: Optional[str]) -> Optional[str]:
                if not t or not isinstance(t, str):
                    return None
                t = t.strip().rstrip('.')
                try:
                    dt = datetime.fromisoformat(t.replace('Z', '+00:00'))
                    return dt.isoformat()
                except Exception:
                    return t  # leave as-is
            start_time = _norm(start_time)
            end_time = _norm(end_time)
            return RunnerAnalysis(
                resource_group=f"runners-{resource_group}",
                runner_type=runner_type,
                test_name=test_name,
                confidence_score=result.get("confidence_score", 0.5),
                extraction_reason=result.get("extraction_reason", "LLM extraction"),
                start_time=start_time,
                end_time=end_time
            )
            
        except ValueError as e:
            # Re-raise validation errors (invalid resource_group/runner_type)
            print(f"❌ Validation error: {e}")
            raise
        except Exception as e:
            # Handle other errors (JSON parsing, LLM errors, etc.)
            print(f"❌ Failed to extract runner info: {e}")
            raise ValueError(f"Unable to extract runner information from incident: {str(e)}")
    
    def extract_test_name(self, incident_details: Dict[str, Any]) -> Optional[str]:
        """
        Extract test_name from incident title for PipelineRunnerLog query
        
        Example title: "[PipelineRunner][israelcentral] Reliability Runner failed: test_distributed_component run failed from 7/21/2025 12:47:34 AM to 7/21/2025 3:47:34 AM"
        Expected test_name: "test_distributed_component"
        
        Args:
            incident_details: Complete incident information
            
        Returns:
            Optional[str]: Extracted test_name or None if not found
        """
        title = incident_details.get('title', '') or incident_details.get('Title', '') or incident_details.get('IncidentTitle', '')
        
        if not title:
            print("⚠️ No title found in incident details")
            return None
        
        print(f"🔍 Extracting test_name from title: {title}")
        
        # Try multiple regex patterns for test_name extraction
        patterns = [
            r'Runner failed: (\w+) run failed',              # "Runner failed: test_distributed_component run failed"
            r'failed: (\w+) run failed',                     # "failed: test_distributed_component run failed"  
            r'test: (\w+)',                                  # "test: test_distributed_component"
            r'test_(\w+)',                                   # "test_distributed_component"
            r'Runner failed: ([^\s]+)',                     # More generic pattern
        ]
        
        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                test_name = match.group(1)
                print(f"✅ Extracted test_name: {test_name}")
                return test_name
        
        print("⚠️ Could not extract test_name from title, trying LLM extraction")
        
        # Fallback: Use LLM to extract test_name
        try:
            extraction_prompt = f"""
            Extract the test name from this pipeline runner incident title.
            
            Title: {title}
            
            Look for patterns like:
            - "Runner failed: [test_name] run failed"
            - "test_[something]" 
            - Any test identifier in the title
            
            Return only the test name (without "test_" prefix if present), or "unknown" if you cannot find one.
            """
            
            response = self.model.invoke([HumanMessage(content=extraction_prompt)])
            test_name = response.content.strip().strip('"\'')
            
            if test_name and test_name.lower() != 'unknown':
                print(f"✅ LLM extracted test_name: {test_name}")
                return test_name
                
        except Exception as e:
            print(f"⚠️ LLM extraction failed: {e}")
        
        print("❌ Could not extract test_name from title")
        return None
    
    def analyze_container_status(self, container_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Use AI to analyze container status and determine if restart is needed
        
        Args:
            container_info: Complete container information from Azure CLI
            
        Returns:
            Dict containing AI analysis results
        """
        # Truncate container_info JSON to avoid token limits
        # container_text = json.dumps(container_info, indent=2)
        containers = container_info.get("containers", [])

        prompt = f"""
        You are an expert in Azure Container Instances and need to analyze the following container status information to determine if a restart is needed.

        Container Information:
        {containers}

        Please analyze this container's status and determine:
        1. Are all the containers in this list in "Running" state?
        2. If this container is not in "Running" state, for example, "Waiting" or "Terminated", it needs to be restarted.
        3. The reason for your decision, in which line of the container_text is the reason.
        4. The confidence of your decision.
        5. Key indicators that led to your decision.

        Respond in JSON format with the following structure:
        {{
            "needs_restart": true/false,
            "reason": "the current status of the container is Running or Waiting or other state",
            "confidence": 0.0-1.0,
            "key_indicators": ["list", "of", "key", "status", "indicators"]
        }}

        Only return the JSON, no additional text.
        """
        
        try:
            response = self.model.invoke([HumanMessage(content=prompt)])
            response_text = response.content.strip()
            
            # Try to parse JSON response
            if response_text.startswith('```json'):
                response_text = response_text[7:-3].strip()
            elif response_text.startswith('```'):
                response_text = response_text[3:-3].strip()
            
            ai_analysis = json.loads(response_text)
            
            # Validate required fields
            required_fields = ["needs_restart", "reason", "confidence", "key_indicators"]
            if not all(field in ai_analysis for field in required_fields):
                raise ValueError("Missing required fields in AI response")
            
            return {
                "success": True,
                "needs_restart": ai_analysis["needs_restart"],
                "reason": ai_analysis["reason"],
                "confidence": ai_analysis["confidence"],
                "key_indicators": ai_analysis["key_indicators"],
                "ai_analysis": True
            }
            
        except Exception as e:
            print(f"⚠️ AI analysis failed: {e}")
            # Fallback to simple check if AI fails
            container_text = json.dumps(container_info, indent=2)
            if len(container_text) > 3000:
                container_text = self.truncate_text(container_text, 3000)
            fallback_needs_restart = (
                "pipeline-runner-cronjob-e2e-scenario" in container_text and 
                "Waiting" in container_text
            )
            
            return {
                "success": True,
                "needs_restart": fallback_needs_restart,
                "reason": "AI analysis failed, using fallback logic",
                "confidence": 0.5,
                "key_indicators": ["fallback_analysis"],
                "ai_analysis": False,
                "ai_error": str(e)
            }
    
    def check_container_needs_restart(self, container_name: str, resource_group: str, subscription: str = "fecca740-22f4-4154-81d8-6ab94324e349") -> Dict[str, Any]:
        """
        Check if container needs restart using AI analysis
        
        Args:
            container_name: Container name
            resource_group: Resource group name
            subscription: Azure subscription ID
            
        Returns:
            Dict containing status information and restart recommendation
        """
        # Get container information from Azure CLI tool
        container_details = azure_cli_tool.show_container(container_name, resource_group, subscription)
        
        if not container_details:
            return {
                "success": False, 
                "needs_restart": False, 
                "reason": f"Failed to get container status: Container not found or Azure CLI error"
            }
        
        container_info = container_details
        
        # Use AI to analyze container status
        ai_result = self.analyze_container_status(container_info)
        
        # Add container info to result
        ai_result["container_info"] = container_info
        
        print(f"🤖 AI Container Status Analysis:")
        print(f"   Container: {container_name}")
        print(f"   Needs Restart: {ai_result['needs_restart']}")
        print(f"   Confidence: {ai_result['confidence']:.2f}")
        print(f"   Reason: {ai_result['reason']}")
        print(f"   Key Indicators: {', '.join(ai_result['key_indicators'])}")
        
        return ai_result
    
    def analyze_runner_logs(self, test_name: str, region: str, incident_details: Dict[str, Any], explicit_start: Optional[str] = None, explicit_end: Optional[str] = None) -> Optional[LogAnalysis]:
        """
        Analyze runner logs for error patterns and root cause
        
        Args:
            test_name: Test name extracted from incident title (e.g., "test_distributed_component")
            region: Azure region
            incident_details: Incident information for time context
            
        Returns:
            LogAnalysis: Analysis results or None if no logs found
        """
        try:
            # Determine time range precedence: explicit > incident creation > default 24h
            end_time = datetime.utcnow()
            start_time = None

            def _parse_iso(ts: str) -> Optional[datetime]:
                try:
                    return datetime.fromisoformat(ts.replace('Z', '+00:00'))
                except Exception:
                    return None

            if explicit_start and explicit_end:
                dt_s = _parse_iso(explicit_start)
                dt_e = _parse_iso(explicit_end)
                if dt_s and dt_e:
                    if dt_e < dt_s:
                        dt_s, dt_e = dt_e, dt_s
                    start_time, end_time = dt_s, dt_e
            if start_time is None and incident_details.get('source_create_date'):
                try:
                    start_time = datetime.fromisoformat(incident_details['source_create_date'].replace('Z', '+00:00'))
                except Exception:
                    start_time = None
            if start_time is None:
                start_time = end_time - timedelta(hours=24)

            # Clamp start_time to max 7 days window
            if end_time - start_time > timedelta(days=7):
                start_time = end_time - timedelta(days=7)
            
            print(f"🔍 Analyzing runner logs from {start_time.isoformat()} to {end_time.isoformat()}")
            
            # Query runner logs using test_name (not container_name)
            logs = kusto_tool.query_runner_logs("pipeline-runner", start_time, end_time, region, test_name)
            
            if not logs:
                print("📋 No logs found for analysis")
                return None
            
            # Prepare log data for LLM analysis with truncation to avoid token limits
            log_summary = f"Found {len(logs)} log entry/entries:\n\n"
            
            # Limit the number of logs to analyze (take most recent ones)
            max_logs = 5  # Only analyze the first 5 log entries
            logs_to_analyze = logs[:max_logs]
            
            for i, log in enumerate(logs_to_analyze):
                log_summary += f"Log Entry {i+1}:\n"
                for key, value in log.items():
                    if value:  # Only include non-empty values
                        # Truncate individual log fields
                        value_str = str(value)
                        if len(value_str) > 1000:  # Truncate long values
                            value_str = self.truncate_text(value_str, 1000)
                        log_summary += f"  {key}: {value_str}\n"
                log_summary += "\n"
            
            if len(logs) > max_logs:
                log_summary += f"... and {len(logs) - max_logs} more log entries (showing first {max_logs} for analysis)\n"
            
            # Final safety check: truncate the entire log_summary if still too long
            if len(log_summary) > 4000:
                log_summary = self.truncate_text(log_summary, 4000)
            
            # LLM analysis prompt
            analysis_prompt = f"""
            You are an expert in analyzing Azure pipeline runner logs. Analyze the following log data and provide insights.

            Test Name: {test_name}
            Region: {region}
            Time Range: {start_time.isoformat()} to {end_time.isoformat()}
            
            Log Data:
            {log_summary}
            
            Please analyze the log data and provide:
            1. error_summary: A concise summary of any issues, errors, or notable findings
            2. error_patterns: List of patterns, issues, or anomalies identified in the data
            3. recommended_action: Specific recommended actions based on your analysis
            4. confidence_score: Your confidence in this analysis (0.0-1.0)
            
            Focus on actionable insights and any patterns that might indicate problems or areas for investigation.
            If the log data doesn't contain clear errors, analyze what the data shows about the test execution.
            """
            
            response = self.model.with_structured_output(LogAnalysis).invoke([
                HumanMessage(content=analysis_prompt)
            ])
            
            print(f"📊 Log Analysis Results:")
            print(f"   Error Summary: {response.error_summary}")
            print(f"   Error Patterns: {', '.join(response.error_patterns)}")
            print(f"   Recommended Action: {response.recommended_action}")
            print(f"   Confidence: {response.confidence_score:.2f}")
            
            return response
            
        except Exception as e:
            print(f"⚠️ Failed to analyze runner logs: {e}")
            return None


def runners_agent(state: MessagesState):
    """
    Runners Agent: Specialized in managing runner containers and determining restart needs
    """
    print("\n" + "="*60)
    print("🏃 Runners Agent: Processing runner container management...")
    
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
            update={"messages": [AIMessage(content="Runners Agent: No incident ID found for analysis.")]}
        )
    
    print(f"🎫 Runners Agent: Analyzing incident {incident_id}")
    
    try:
        # Initialize runner agent
        runner = RunnerAgent()
        
        # Step 1: Query incident details
        print("\n📋 Step 1: Querying incident details...")
        incident_details = kusto_tool.query_incident_details(incident_id)
        
        if not incident_details or incident_details.get('Title') == None:
            return Command(
                goto=END,
                update={"messages": [AIMessage(content=f"Runners Agent: Unable to retrieve details for incident {incident_id}")]}
            )
        
        # Step 2: Extract runner information
        print("\n🔍 Step 2: Extracting runner information...")
        try:
            runner_analysis = runner.extract_runner_info(incident_details.get('Title'))
        except ValueError as e:
            print(f"❌ Failed to extract runner information: {e}")
            return Command(
                goto=END,
                update={"messages": [AIMessage(content=f"Runners Agent: Failed to extract runner information - {str(e)}")]}
            )
        
        # Step 3: Find container name
        print("\n🔍 Step 3: Finding container name...")
        subscription = "fecca740-22f4-4154-81d8-6ab94324e349"  # Default subscription for runners
        container_name = azure_cli_tool.find_container_by_type(runner_analysis.resource_group, runner_analysis.runner_type, subscription)
        
        if not container_name:
            return Command(
                goto=END,
                update={"messages": [AIMessage(content=f"Runners Agent: No container found for runner type '{runner_analysis.runner_type}' in resource group '{runner_analysis.resource_group}'")]}
            )
        
        # Step 4: Check container status using AI analysis
        print("\n📊 Step 4: Checking container status with AI analysis...")
        status_result = runner.check_container_needs_restart(container_name, runner_analysis.resource_group, subscription)
        
        if not status_result["success"]:
            return Command(
                goto=END,
                update={"messages": [AIMessage(content=f"Runners Agent: Failed to check container status: {status_result['reason']}")]}
            )
        
        # Step 5: Restart if needed, otherwise analyze logs
        restart_result = None
        log_analysis = None
        
        if status_result["needs_restart"]:
            print("\n🔄 Step 5: Restarting container...")
            restart_success = azure_cli_tool.restart_container(container_name, runner_analysis.resource_group, subscription)
            
            # Create a structured result for consistency with the report function
            restart_result = {
                "success": restart_success,
                "message": f"Container restart {'succeeded' if restart_success else 'failed'}",
                "restart_method": "stop_start"
            }
        else:
            print("\n✅ Step 5: Container restart not needed")
            
            # Use the test name extracted in Step 1 (like v2)
            test_name = runner_analysis.test_name
            
            if test_name:
                print(f"\n📊 Step 5b: Analyzing runner logs for test: {test_name}")
                # Extract region from resource_group (format: "runners-{region}")
                region = runner_analysis.resource_group.replace("runners-", "") if runner_analysis.resource_group.startswith("runners-") else "westus"
                
                log_analysis = runner.analyze_runner_logs(
                    test_name,
                    region,
                    incident_details,
                    explicit_start=runner_analysis.start_time,
                    explicit_end=runner_analysis.end_time
                )
            else:
                print("\n⚠️ Cannot analyze logs: test_name extraction failed")
                log_analysis = None
        
        # Generate final report
        report = generate_runners_report(
            incident_details, 
            runner_analysis, 
            container_name, 
            status_result, 
            restart_result,
            log_analysis
        )
        
        print("\n✅ Runners Agent analysis completed!")
        
        return Command(
            goto=END,
            update={"messages": [AIMessage(content=report)]}
        )
        
    except Exception as e:
        print(f"❌ Runners Agent error: {e}")
        return Command(
            goto=END,
            update={"messages": [AIMessage(content=f"Runners Agent: Analysis failed - {str(e)}")]}
        )

def generate_runners_report(incident_details: Dict[str, Any], 
                          runner_analysis: RunnerAnalysis,
                          container_name: str,
                          status_result: Dict[str, Any],
                          restart_result: Optional[Dict[str, Any]],
                          log_analysis: Optional[LogAnalysis] = None) -> str:
    """
    Generate comprehensive runners agent report
    
    Args:
        incident_details: Original incident data
        runner_analysis: LLM analysis results
        container_name: Found container name
        status_result: Container status check results
        restart_result: Container restart results (if attempted)
        log_analysis: Runner log analysis results (if performed)
        
    Returns:
        str: Formatted final report
    """
    report = f"""
🏃 **RUNNERS AGENT ANALYSIS REPORT**
================================================

📋 **Incident Information:**
- Incident ID: {incident_details.get('IncidentId') or incident_details.get('incident_id', 'Unknown')}
- Title: {incident_details.get('Title') or incident_details.get('IncidentTitle') or incident_details.get('title', 'Unknown')}
- Summary: {incident_details.get('Summary') or incident_details.get('summary', 'No summary available')}

🔍 **Runner Information Extracted:**
- **Resource Group:** {runner_analysis.resource_group}
- **Runner Type:** {runner_analysis.runner_type}
- **Test Name:** {runner_analysis.test_name or 'N/A'}
- **Time Range:** {runner_analysis.start_time or 'N/A'} to {runner_analysis.end_time or 'N/A'}
- **Extraction Confidence:** {runner_analysis.confidence_score:.1%}
- **Extraction Reason:** {runner_analysis.extraction_reason}

📦 **Container Information:**
- **Container Name:** {container_name}
- **Status Check:** {'✅ Success' if status_result['success'] else '❌ Failed'}
- **Needs Restart:** {'✅ Yes' if status_result['needs_restart'] else '❌ No'}
- **AI Analysis:** {'✅ Success' if status_result.get('ai_analysis', False) else '❌ Failed/Fallback'}
- **Confidence:** {status_result.get('confidence', 0.5):.1%}
- **Key Indicators:** {', '.join(status_result.get('key_indicators', []))}
- **Analysis Reason:** {status_result['reason']}

"""
    
    if restart_result:
        report += f"""
🔄 **Container Restart Action:**
- **Restart Attempted:** ✅ Yes
- **Restart Method:** {restart_result.get('restart_method', 'stop_start').replace('_', ' + ').title()}
- **Overall Result:** {'✅ Success' if restart_result['success'] else '❌ Failed'}
- **Message:** {restart_result['message']}

"""
    else:
        report += f"""
🔄 **Container Restart Action:**
- **Restart Attempted:** ❌ No
- **Reason:** Container status indicates restart is not needed

"""
        
        # Add log analysis section if available
        if log_analysis:
            report += f"""
📊 **Runner Log Analysis:**
- **Error Summary:** {log_analysis.error_summary}
- **Error Patterns:** {', '.join(log_analysis.error_patterns)}
- **Recommended Action:** {log_analysis.recommended_action}
- **Analysis Confidence:** {log_analysis.confidence_score:.1%}

"""
        else:
            # Only show this if restart was not attempted
            if not restart_result:
                report += f"""
📊 **Runner Log Analysis:**
- **Status:** No error logs found or analysis unavailable

"""
    
    report += """
================================================
"""
    
    return report 