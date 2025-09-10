# Prerequisites:
# 1. Install requirements.txt
# 2. az login
# 3. connect to VPN
import asyncio
import re
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import pandas as pd
import concurrent.futures
from datetime import datetime

# Import streaming callbacks
from streaming.callbacks import get_current_callbacks

# Kusto/Azure dependencies
try:
    from azure.identity import DefaultAzureCredential
    from azure.kusto.data import KustoClient, KustoConnectionStringBuilder, ClientRequestProperties
    from azure.kusto.data.helpers import dataframe_from_result_table
    from azure.kusto.data.exceptions import KustoServiceError
    KUSTO_AVAILABLE = True
except ImportError:
    print("⚠️ Warning: Azure Kusto dependencies not installed. Team-based routing will be disabled.")
    KUSTO_AVAILABLE = False

# Load environment variables
load_dotenv()

class KustoQueryTool:
    """Tool for querying incident information from IcM database via Azure Kusto - ASYNC VERSION"""
    
    def __init__(self):
        self.cluster = "https://icmcluster.kusto.windows.net"
        self.database = "IcmDataWareHouse"
        self.client = None
        self.available = KUSTO_AVAILABLE
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        
        if KUSTO_AVAILABLE:
            self.client = self._get_kusto_client()
    
    def _get_kusto_client(self):
        """Get authenticated Kusto client"""
        try:
            credential = DefaultAzureCredential()
            kusto_connection_builder = KustoConnectionStringBuilder.with_azure_token_credential(
                self.cluster, credential
            )
            return KustoClient(kusto_connection_builder)
        except Exception as e:
            print(f"❌ Failed to initialize Kusto client: {e}")
            return None
    
    def _clean_html(self, text: str) -> str:
        """Remove HTML tags from text"""
        if not text:
            return ""
        soup = BeautifulSoup(text, 'html.parser')
        return soup.get_text(separator=' ', strip=True)
    
    def extract_incident_id(self, text: str) -> Optional[str]:
        """Extract incident ID from text"""
        if not text:
            return None
        
        patterns = [
            r'incident[:\s]+(\d+)',
            r'ticket[:\s]+(\d+)',  
            r'icm[:\s]*[#]?(\d+)',
            r'#(\d+)',
            r'\b(\d{8,10})\b'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                incident_id = match.group(1)
                if len(incident_id) >= 8:
                    return incident_id
        
        return None
    
    def extract_incident_title(self, text: str) -> Optional[str]:
        """Extract incident title from text"""
        if not text:
            return None
        
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        for line in lines:
            if any(keyword in line.lower() for keyword in ['failed', 'error', 'issue', 'problem', 'outage']):
                if len(line) > 20 and len(line) < 200:
                    return line
        
        if lines:
            return lines[0]
        
        return None

    async def _execute_query_async(self, query: str) -> Optional[pd.DataFrame]:
        """Execute Kusto query asynchronously"""
        if not self.client:
            return None
        
        def _execute_sync():
            response = self.client.execute(self.database, query)
            return dataframe_from_result_table(response.primary_results[0])
        
        try:
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(self.executor, _execute_sync)
            return df
        except Exception as e:
            print(f"❌ Error executing Kusto query: {e}")
            return None

    async def query_owning_team(self, incident_id: str) -> List[str]:
        """
        Query owning team information for incident routing
        
        Args:
            incident_id (str): IcM ticket ID
            
        Returns:
            List[str]: List of team information, or empty list if not found
        """
        if not self.available or not self.client:
            print("🔧 Kusto not available, skipping team query")
            return []
        
        # Get callbacks for streaming
        callbacks = get_current_callbacks()
        
        try:
            query = f"""
            cluster('icmcluster.kusto.windows.net').database('IcmDataWareHouse').Incidents
            | where IncidentId == {incident_id}
            | project OwningTeamId
            | distinct OwningTeamId
            """
            
            # Stream tool start
            if callbacks:
                await callbacks.on_tool_start("Kusto Tool", "Kusto Query", {
                    "query_type": "owning_team",
                    "incident_id": incident_id,
                    "query": query.strip()
                })
            
            print(f"🔍 Query: {query}")
            df = await self._execute_query_async(query)
            
            if df is not None and not df.empty:
                teams = []
                for _, row in df.iterrows():
                    # Extract just the team ID for routing logic
                    team_id = str(row.get('OwningTeamId', ''))
                    if team_id and team_id != 'nan' and team_id != 'N/A':
                        teams.append(team_id)
                
                print(f"✅ Found {len(teams)} team IDs: {teams}")
                
                # Stream tool end with formatted result for display
                if callbacks:
                    await callbacks.on_tool_end("Kusto Tool", "Kusto Query", f"Found {len(teams)} team IDs: {teams}")
                
                return teams
            else:
                print("📋 No team information found")
                
                # Stream tool end with empty result
                if callbacks:
                    await callbacks.on_tool_end("Kusto Tool", "Kusto Query", [])
                
                return []
                
        except Exception as ex:
            print(f"❌ Error in query_owning_team: {ex}")
            
            # Stream tool end with error
            if callbacks:
                await callbacks.on_tool_end("Kusto Tool", "Kusto Query", f"Error: {str(ex)}")
            
            return []

    async def query_ticket_title(self, incident_id: str) -> str:
        """
        Query ticket title by incident ID
        
        Args:
            incident_id (str): IcM ticket ID
            
        Returns:
            str: Ticket title or empty string if not found
        """
        if not self.available or not self.client:
            return ""

        # Get callbacks for streaming
        callbacks = get_current_callbacks()
        
        try:
            query = f"""
            cluster('icmcluster.kusto.windows.net').database('IcmDataWareHouse').table('Incidents')
            | where IncidentId == {incident_id}
            | summarize arg_max(Lens_IngestionTime, *) by IncidentId
            | project Title
            | limit 1
            """
            
            # Stream tool start
            if callbacks:
                await callbacks.on_tool_start("Kusto Tool", "Query Ticket Title", {
                    "incident_id": incident_id,
                    "query": query.strip()
                })
            
            print(f"🔍 Querying ticket title for incident {incident_id}...")
            
            df = await self._execute_query_async(query)
            
            if df is not None and not df.empty:
                title = str(df.iloc[0]['Title'])
                print(f"✅ Found title: {title}")
                
                if callbacks:
                    await callbacks.on_tool_end("Kusto Tool", "Query Ticket Title", {
                        "incident_id": incident_id,
                        "title": title
                    })
                
                return title
            else:
                print(f"❌ No title found for incident {incident_id}")
                if callbacks:
                    await callbacks.on_tool_end("Kusto Tool", "Query Ticket Title", {
                        "incident_id": incident_id,
                        "title": "",
                        "error": "No title found"
                    })
                return ""
                
        except Exception as e:
            print(f"❌ Error querying ticket title for {incident_id}: {e}")
            if callbacks:
                await callbacks.on_tool_end("Kusto Tool", "Query Ticket Title", {
                    "incident_id": incident_id,
                    "error": str(e)
                })
            return ""

    async def query_ticket_category(self, incident_id: str) -> List[str]:
        """
        Query ticket categories for incident classification
        
        Args:
            incident_id (str): IcM ticket ID
            
        Returns:
            List[str]: List of category information, or empty list if not found
        """
        if not self.available or not self.client:
            print("🔧 Kusto not available, skipping category query")
            return []
        
        # Get callbacks for streaming
        callbacks = get_current_callbacks()
        
        try:
            query = f"""
            cluster('icmcluster.kusto.windows.net').database('IcmDataWareHouse').IncidentCustomFieldEntries
            | where IncidentId == {incident_id}
            | where DisplayName == "Issue Details"
            | project Value
            """
            
            # Stream tool start
            if callbacks:
                await callbacks.on_tool_start("Kusto Tool", "Kusto Query", {
                    "query_type": "ticket_category", 
                    "incident_id": incident_id,
                    "query": query.strip()
                })
            
            print(f"🔍 Query: {query}")
            df = await self._execute_query_async(query)
            
            if df is not None and not df.empty:
                categories = []
                for _, row in df.iterrows():
                    category_info = f"Category: {row.get('Value', 'Unknown')}"
                    categories.append(category_info)
                
                print(f"✅ Found {len(categories)} category entries")
                
                # Stream tool end with result
                if callbacks:
                    await callbacks.on_tool_end("Kusto Tool", "Kusto Query", categories)
                
                return categories
            else:
                print("📋 No category information found")
                
                # Stream tool end with empty result
                if callbacks:
                    await callbacks.on_tool_end("Kusto Tool", "Kusto Query", [])
                
                return []
                
        except Exception as ex:
            print(f"❌ Error in query_ticket_category: {ex}")
            
            # Stream tool end with error
            if callbacks:
                await callbacks.on_tool_end("Kusto Tool", "Kusto Query", f"Error: {str(ex)}")
            
            return []

    async def query_incident_details(self, incident_id: str) -> Dict[str, Any]:
        """
        Query comprehensive incident information including title, description, and team info
        
        Args:
            incident_id (str): IcM ticket ID
            
        Returns:
            Dict[str, Any]: Complete incident details dictionary
        """
        if not self.available or not self.client:
            return {
                "incident_id": incident_id, 
                "title": "Unknown", 
                "description": "", 
                "owning_teams": [],
                "summary": "",
                "severity": "",
                "routing_id": ""
            }

        # Get callbacks for streaming
        callbacks = get_current_callbacks()
        
        try:
            query = f"""
            let incidentsData = 
                cluster('icmcluster.kusto.windows.net').database('IcmDataWareHouse').table('Incidents')
                | where IncidentId == {incident_id}
                | summarize arg_max(Lens_IngestionTime, *) by IncidentId
                | project SourceCreateDate, IncidentId, Title, RoutingId, OccurringDeviceName, 
                         Severity, TsgId, MonitorId, Summary, OwningTeamName, OwningTeamId;
            let incidentDescription = 
                cluster('icmcluster.kusto.windows.net').database('IcmDataWareHouse').IncidentDescriptions
                | where IncidentId == {incident_id}
                | summarize arg_max(Lens_IngestionTime, *) by DescriptionId
                | project DescriptionId, IncidentId, Text, Lens_IngestionTime
                | summarize TextList = make_list(Text) by IncidentId
                | extend MergedText = replace("['|']", " ", tostring(TextList))
                | project IncidentId, MergedText;
            incidentsData 
            | join kind = leftouter (incidentDescription) on IncidentId
            | project SourceCreateDate, IncidentId, Title, RoutingId, OccurringDeviceName, 
                     Severity, TsgId, MonitorId, Summary, MergedText, OwningTeamName, OwningTeamId
            | limit 1
            """
            
            # Stream tool start with the actual query
            if callbacks:
                await callbacks.on_tool_start("Kusto Tool", "Kusto Query", {
                    "query_type": "incident_details",
                    "incident_id": incident_id,
                    "query": query.strip()
                })
            
            print(f"🔍 Query: {query}")
            df = await self._execute_query_async(query)
            
            if df is not None and not df.empty:
                row = df.iloc[0]
                incident_details = {
                    "IncidentId": row.get('IncidentId'),
                    "Title": row.get('Title', ''),
                    "IncidentTitle": row.get('Title', ''),  # Backward compatibility
                    "RoutingId": row.get('RoutingId', ''),
                    "OccurringDeviceName": row.get('OccurringDeviceName', ''),
                    "Severity": row.get('Severity', ''),
                    "TsgId": row.get('TsgId', ''),
                    "MonitorId": row.get('MonitorId', ''),
                    "Summary": self._clean_html(row.get('Summary', '')),
                    "MergedText": self._clean_html(row.get('MergedText', '')),
                    "OwningTeamName": row.get('OwningTeamName', ''),
                    "OwningTeamId": row.get('OwningTeamId', ''),
                    "SourceCreateDate": row.get('SourceCreateDate', '')
                }
                
                print(f"✅ Retrieved incident details for {incident_id}")
                
                # Stream tool end with result summary
                if callbacks:
                    await callbacks.on_tool_end("Kusto Tool", "Kusto Query", {
                        "incident_id": incident_details["IncidentId"],
                        "title": incident_details["Title"][:100] + "..." if len(incident_details["Title"]) > 100 else incident_details["Title"],
                        "severity": incident_details["Severity"],
                        "team": incident_details["OwningTeamName"],
                        "Summary": incident_details["Summary"][:300],
                        "MergedText": incident_details["MergedText"][:300],
                    })
                
                return incident_details
            else:
                print(f"📋 No incident details found for {incident_id}")
                
                # Stream tool end with empty result
                if callbacks:
                    await callbacks.on_tool_end("Kusto Tool", "Kusto Query", f"No details found for incident {incident_id}")
                
                return {
                    "IncidentId": incident_id,
                    "Title": "Not Found",
                    "IncidentTitle": "Not Found",
                    "Summary": "",
                    "Severity": "",
                    "RoutingId": "",
                    "OccurringDeviceName": "",
                    "TsgId": "",
                    "MonitorId": "",
                    "MergedText": "",
                    "OwningTeamName": "",
                    "OwningTeamId": "",
                    "SourceCreateDate": ""
                }
                
        except Exception as ex:
            print(f"❌ Error in query_incident_details: {ex}")
            
            # Stream tool end with error
            if callbacks:
                await callbacks.on_tool_end("Kusto Tool", "Kusto Query", f"Error: {str(ex)}")
            
            return {
                "IncidentId": incident_id,
                "Title": f"Error: {str(ex)}",
                "IncidentTitle": f"Error: {str(ex)}",
                "Summary": "",
                "Severity": "",
                "RoutingId": "",
                "OccurringDeviceName": "",
                "TsgId": "",
                "MonitorId": "",
                "MergedText": "",
                "OwningTeamName": "",
                "OwningTeamId": "",
                "SourceCreateDate": ""
            }

    async def query_runner_logs(self, runner_type: str, start_time: datetime, end_time: datetime, region: str, test_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Query runner logs within a time window
        
        Args:
            start_time (datetime): Start of time window
            end_time (datetime): End of time window  
            test_name (Optional[str]): Optional test name filter
            
        Returns:
            List[Dict[str, Any]]: List of log entries
        """
        if not self.available or not self.client:
            print("🔧 Kusto not available, skipping runner logs query")
            return []
        
        # Get callbacks for streaming
        callbacks = get_current_callbacks()

        print(f"🔍 Runner type: {runner_type}")
        if runner_type == "pipeline-runner":
            runner_str = "PipelineRunnerLog"
        elif runner_type == "pipeline-mfe-runner":
            runner_str = "PipelineMFERunnerLog"
        elif runner_type == "sdk-cli-v2-pipeline-sdk-runner":
            runner_str = "SDKV2PipelineRunnerLog"
        elif runner_type == "sdk-cli-v2-pipeline-cli-runner":
            runner_str = "CLIV2PipelineRunnerLog"
        elif runner_type == "sdk-cli-v2-schedule-sdk-runner":
            runner_str = "SDKV2ScheduleRunnerLog"
        elif runner_type == "sdk-cli-v2-pipelines-schedule-sdk-runner":
            runner_str = "CLIV2ScheduleRunnerLog"
        else:
            runner_str = "PipelineRunnerLog"

        
        try:
            query = f"""
            cluster('viennause2.kusto.windows.net').database('Vienna').{runner_str}(datetime({start_time.isoformat()}), datetime({end_time.isoformat()}), "{region}", "{test_name}", "False")
            """
            
            # Stream tool start
            if callbacks:
                await callbacks.on_tool_start("Kusto Tool", "Kusto Query", {
                    "query_type": "runner_logs",
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                    "test_name": test_name,
                    "query": query.strip()
                })
            
            print(f"🔍 Query: {query}")
            df = await self._execute_query_async(query)
            
            if df is not None and not df.empty:
                logs = df.to_dict('records')
                print(f"✅ Found {len(logs)} runner log entries")
                
                # Stream tool end with result summary and sample log
                if callbacks:
                    result_info = {
                        "summary": f"Found {len(logs)} runner log entries",
                        "total_logs": len(logs)
                    }
                    
                    # Include first log entry as sample
                    if logs:
                        sample_log = logs[0]
                        # Truncate long values for display
                        sample_log_display = {}
                        for key, value in sample_log.items():
                            if value is not None:
                                value_str = str(value)
                                # Truncate if too long
                                # if len(value_str) > 500:
                                #     sample_log_display[key] = value_str[:500] + "..."
                                # else:
                                sample_log_display[key] = value_str
                        result_info["sample_log"] = sample_log_display
                    
                    await callbacks.on_tool_end("Kusto Tool", "Kusto Query", result_info)
                
                return logs
            else:
                print("📋 No runner logs found")
                
                # Stream tool end with empty result
                if callbacks:
                    await callbacks.on_tool_end("Kusto Tool", "Kusto Query", "No runner logs found")
                
                return []
                
        except Exception as ex:
            print(f"❌ Error in query_runner_logs: {ex}")
            
            # Stream tool end with error
            if callbacks:
                await callbacks.on_tool_end("Kusto Tool", "Kusto Query", f"Error: {str(ex)}")
            
            return []

# Create singleton instance
kusto_tool = KustoQueryTool()
