# Prerequisites:
# 1. Install requirements.txt
# 2. az login
# 3. connect to VPN
import re
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime



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
    """Tool for querying incident information from IcM database via Azure Kusto"""
    
    def __init__(self):
        self.cluster = "https://icmcluster.kusto.windows.net"
        self.database = "IcmDataWareHouse"
        self.client = None
        self.available = KUSTO_AVAILABLE
        
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
    
    def _clean_html(self, raw_text: str) -> str:
        """Clean HTML tags and keep plain text"""
        if not raw_text:
            return ""
        
        try:
            soup = BeautifulSoup(raw_text, 'html.parser')
            return soup.get_text(strip=True)
        except Exception as e:
            print(f"Warning: Failed to clean HTML: {e}")
            return str(raw_text)
    
    def extract_incident_id(self, text: str) -> Optional[str]:
        """Extract incident ID from text using various patterns"""
        if not text:
            return None
        
        incident_patterns = [
            r'Incident\s+(\d+)\s*:\s*.+',  # "Incident 640434731 : [Title] description"
            r'Incident\s+(\d+)',           # "Incident 640434731"
            r'incident\s+(\d+)',           # "Incident 640434731"
            r'ID:?\s*(\d+)',               # "ID: 640434731" or "ID 640434731"
            r'#(\d+)',                     # "#640434731"
            r'(\d{9,})',                   # Direct 9+ digit number
        ]
        
        for pattern in incident_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        return None
    
    def query_owning_team(self, incident_id: str) -> List[str]:
        """
        Query the OwningTeamId for a given incident ID to support team-based routing
        
        Args:
            incident_id (str): IcM ticket ID
            
        Returns:
            List[str]: List of OwningTeamId values, or empty list if not found
        """
        if not self.available or not self.client:
            print("🔧 Kusto not available, skipping team query")
            return []
        
        try:
            query = f"""
            cluster('icmcluster.kusto.windows.net').database('IcmDataWareHouse').Incidents
            | where IncidentId == {incident_id}
            | project OwningTeamId
            | distinct OwningTeamId
            """
            
            print(f"🔍 Query: {query}")
            response = self.client.execute(self.database, query)
            df = dataframe_from_result_table(response.primary_results[0])
            
            if df is not None and not df.empty and 'OwningTeamId' in df.columns:
                owning_team_ids = df['OwningTeamId'].dropna().astype(str).tolist()
                print(f"🔍 Found owning team IDs for incident {incident_id}: {owning_team_ids}")
                return owning_team_ids
            else:
                print(f"🔍 No team information found for incident {incident_id}")
                return []
                
        except Exception as ex:
            print(f"❌ Error in query_owning_team: {ex}")
            return []
    
    def query_ticket_category(self, incident_id: str) -> List[str]:
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
        
        try:
            query = f"""
            cluster('icmcluster.kusto.windows.net').database('IcmDataWareHouse').IncidentCustomFieldEntries
            | where IncidentId == {incident_id}
            | where DisplayName == "Issue Details"
            | project Value
            """
            
            print(f"🔍 Query: {query}")
            response = self.client.execute(self.database, query)
            df = dataframe_from_result_table(response.primary_results[0])
            
            if df is not None and not df.empty:
                categories = []
                for _, row in df.iterrows():
                    category_info = f"Category: {row.get('Value', 'N/A')}"
                    categories.append(category_info)
                
                print(f"🏷️ Found categories for incident {incident_id}: {categories}")
                return categories
            else:
                print(f"🏷️ No issue details found for incident {incident_id}")
                return []
                
        except Exception as ex:
            print(f"❌ Error in query_ticket_category: {ex}")
            return []
    
    def query_incident_details(self, incident_id: str) -> Dict[str, Any]:
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
            
            response = self.client.execute(self.database, query)
            df = dataframe_from_result_table(response.primary_results[0])
            
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
                
                print(f"📋 Retrieved incident details for {incident_id}: {incident_details.get('Title', 'Unknown Title')}")
                return incident_details
            else:
                print(f"📋 No incident details found for {incident_id}")
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

    def query_runner_logs(self, runner_type: str, start_time: datetime, end_time: datetime, region: str, test_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Query runner logs within a time window
        
        Args:
            runner_type (str): Type of runner (e.g., "pipeline-runner")
            start_time (datetime): Start of time window
            end_time (datetime): End of time window  
            region (str): Region filter
            test_name (Optional[str]): Optional test name filter
            
        Returns:
            List[Dict[str, Any]]: List of log entries
        """
        if not self.available or not self.client:
            print("🔧 Kusto not available, skipping runner logs query")
            return []

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
            
            print(f"🔍 Query: {query}")
            response = self.client.execute(self.database, query)
            df = dataframe_from_result_table(response.primary_results[0])
            
            if df is not None and not df.empty:
                logs = df.to_dict('records')
                print(f"✅ Found {len(logs)} runner log entries")
                
                # Print sample log for debugging
                if logs:
                    print("📋 Sample log entry:")
                    sample_log = logs[0]
                    for key, value in sample_log.items():
                        if value is not None:
                            value_str = str(value)
                            print(f"  {key}: {value_str}")
                
                return logs
            else:
                print("📋 No runner logs found")
                return []
                
        except Exception as ex:
            print(f"❌ Error in query_runner_logs: {ex}")
            return []

# Create singleton instance
kusto_tool = KustoQueryTool()