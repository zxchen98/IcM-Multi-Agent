import pandas as pd
import os
from typing import List, Dict, Optional
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()

class SimilarTicket(BaseModel):
    incident_id: str
    title: str
    investigation: str
    ai_conclusion: str
    ai_solution: str
    ai_transferred_to: str
    similarity_score: float
    similarity_reason: str

class SimilarTicketSearchTool:
    def __init__(self):
        self.model = AzureChatOpenAI(
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
            azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
        )
        self.excel_file_path = "data/past_tickets_with_ai_summary.xlsx"
        self.tickets_df = None
        self._load_tickets()
    
    def _load_tickets(self):
        """Load tickets from Excel file"""
        try:
            if os.path.exists(self.excel_file_path):
                self.tickets_df = pd.read_excel(self.excel_file_path)
                print(f"✅ Loaded {len(self.tickets_df)} tickets from {self.excel_file_path}")
                print(f"📊 Available columns: {list(self.tickets_df)}")
            else:
                print(f"❌ Excel file not found: {self.excel_file_path}")
        except Exception as e:
            print(f"❌ Error loading tickets: {e}")
    
    def find_similar_tickets(self, incident_description: str, current_incident_id: str = None, product: str = None, 
                           ai_problem_stage: str = None, ai_key_log: str = None, ai_conclusion: str = None) -> List[SimilarTicket]:
        """
        Find similar tickets based on incident description and AI-generated fields
        
        Args:
            incident_description: Description of the current incident (Title)
            current_incident_id: ID of current incident to exclude from results
            product: Product name to filter tickets by (required)
            ai_problem_stage: AI-generated problem stage for similarity comparison
            ai_key_log: AI-generated key log for similarity comparison  
            ai_conclusion: AI-generated conclusion for similarity comparison
            
        Returns:
            List of similar tickets with IncidentId, Title, Investigation, AI_Conclusion, AI_Solution, AI_TransferredTo
        """
        if self.tickets_df is None:
            print("❌ No tickets data loaded")
            return []
        
        # Product filtering is required
        if not product:
            print("❌ Product parameter is required for similarity search")
            return []
        
        # Check if required columns exist for similarity comparison
        similarity_columns = ['Title', 'AI_ProblemStage', 'AI_KeyLog', 'AI_Conclusion']
        output_columns = ['IncidentId', 'Title', 'Product', 'Investigation', 'AI_Conclusion', 'AI_Solution', 'AI_TransferredTo']
        
        missing_similarity_cols = [col for col in similarity_columns if col not in self.tickets_df.columns]
        missing_output_cols = [col for col in output_columns if col not in self.tickets_df.columns]
        
        if missing_similarity_cols:
            print(f"❌ Missing similarity columns in Excel file: {missing_similarity_cols}")
            print(f"📊 Available columns: {list(self.tickets_df.columns)}")
            return []
            
        if missing_output_cols:
            print(f"❌ Missing output columns in Excel file: {missing_output_cols}")
            print(f"📊 Available columns: {list(self.tickets_df.columns)}")
            return []
        
        # Filter out the current incident if provided
        filtered_df = self.tickets_df.copy()
        if current_incident_id:
            filtered_df = filtered_df[filtered_df['IncidentId'] != current_incident_id]
        
        # Filter by product (required)
        product_filtered = filtered_df[filtered_df['Product'] == product]
        
        if len(product_filtered) == 0:
            print(f"⚠️ No tickets found for product: {product}")
            print(f"📊 Available products: {filtered_df['Product'].value_counts().to_dict()}")
            return []
        
        filtered_df = product_filtered
        print(f"🔍 Filtered to {len(filtered_df)} tickets for product: {product}")
        
        # Take a sample of tickets for analysis (limit to avoid token limits)
        sample_size = min(50, len(filtered_df))
        sample_df = filtered_df.sample(n=sample_size, random_state=42) if len(filtered_df) > sample_size else filtered_df
        
        # Prepare tickets data for similarity analysis using only specified columns
        tickets_data = []
        for _, row in sample_df.iterrows():
            ticket_info = {
                'IncidentId': str(row['IncidentId']),
                'Title': str(row['Title']) if pd.notna(row['Title']) else '',
                'AI_ProblemStage': str(row['AI_ProblemStage']) if pd.notna(row['AI_ProblemStage']) else '',
                'AI_KeyLog': str(row['AI_KeyLog']) if pd.notna(row['AI_KeyLog']) else '',
                'AI_Conclusion': str(row['AI_Conclusion']) if pd.notna(row['AI_Conclusion']) else '',
                'Investigation': str(row['Investigation']) if pd.notna(row['Investigation']) else '',
                'AI_Solution': str(row['AI_Solution']) if pd.notna(row['AI_Solution']) else '',
                'AI_TransferredTo': str(row['AI_TransferredTo']) if pd.notna(row['AI_TransferredTo']) else ''
            }
            tickets_data.append(ticket_info)
        
        # Use LLM to find similar tickets based on specified columns
        current_ticket_data = {
            'Title': incident_description,
            'AI_ProblemStage': ai_problem_stage or '',
            'AI_KeyLog': ai_key_log or '', 
            'AI_Conclusion': ai_conclusion or ''
        }
        
        similar_tickets = self._analyze_similarity_with_llm(current_ticket_data, tickets_data)
        
        return similar_tickets
    
    def _analyze_similarity_with_llm(self, current_ticket_data: Dict, tickets_data: List[Dict]) -> List[SimilarTicket]:
        """Use LLM to analyze similarity between current incident and historical tickets based on specific columns"""
        
        system_prompt = """
        You are an expert at analyzing technical incidents and finding similar historical cases.
        
        Your task is to:
        1. Analyze the current incident data based on these fields:
           - Title: The incident title/description
           - AI_ProblemStage: AI-identified stage of the problem
           - AI_KeyLog: AI-extracted key log information
           - AI_Conclusion: AI-generated conclusion about the incident
           
        2. Compare it with historical tickets using ONLY the same four fields
        3. Find the TOP 3 most similar tickets based on these specific criteria:
           - Similar problem stages or failure patterns
           - Matching key log patterns or error signatures
           - Similar conclusions or root causes
           - Related titles or incident descriptions
        
        4. For each similar ticket, provide:
           - IncidentId
           - Title
           - Investigation details
           - AI_Conclusion
           - AI_Solution  
           - AI_TransferredTo
           - Similarity score (0-100)
           - Brief reason for similarity
        
        Focus on technical similarities in the specified fields only. Ignore any other information.
        
        Return your analysis as a JSON array with exactly 3 tickets (or fewer if less than 3 are truly similar with score >= 60).
        """
        
        user_prompt = f"""
        Current Incident Data (for comparison):
        - Title: {current_ticket_data.get('Title', '')}
        - AI_ProblemStage: {current_ticket_data.get('AI_ProblemStage', '')}
        - AI_KeyLog: {current_ticket_data.get('AI_KeyLog', '')}
        - AI_Conclusion: {current_ticket_data.get('AI_Conclusion', '')}
        
        Historical Tickets to Compare (same product only):
        {json.dumps(tickets_data, indent=2, ensure_ascii=False)}
        
        Please analyze and return the top 3 most similar tickets in this JSON format:
        [
            {{
                "incident_id": "ticket_id",
                "title": "ticket_title",
                "investigation": "investigation_details",
                "ai_conclusion": "ai_conclusion_text",
                "ai_solution": "ai_solution_text",
                "ai_transferred_to": "ai_transferred_to_text",
                "similarity_score": 85,
                "similarity_reason": "Brief explanation focusing on Title, AI_ProblemStage, AI_KeyLog, or AI_Conclusion similarities"
            }}
        ]
        
        Only compare using Title, AI_ProblemStage, AI_KeyLog, and AI_Conclusion fields.
        """
        
        try:
            response = self.model.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ])
            
            # Try to parse JSON response
            response_text = response.content.strip()
            
            # Clean up the response if it has markdown code blocks
            if response_text.startswith("```json"):
                response_text = response_text[7:-3]
            elif response_text.startswith("```"):
                response_text = response_text[3:-3]
            
            try:
                similar_tickets_data = json.loads(response_text)
                
                # Convert to SimilarTicket objects
                similar_tickets = []
                for ticket_data in similar_tickets_data:
                    similar_ticket = SimilarTicket(
                        incident_id=ticket_data.get('incident_id', ''),
                        title=ticket_data.get('title', ''),
                        investigation=ticket_data.get('investigation', ''),
                        ai_conclusion=ticket_data.get('ai_conclusion', ''),
                        ai_solution=ticket_data.get('ai_solution', ''),
                        ai_transferred_to=ticket_data.get('ai_transferred_to', ''),
                        similarity_score=ticket_data.get('similarity_score', 0),
                        similarity_reason=ticket_data.get('similarity_reason', '')
                    )
                    similar_tickets.append(similar_ticket)
                
                return similar_tickets
                
            except json.JSONDecodeError as e:
                print(f"❌ Failed to parse LLM response as JSON: {e}")
                print(f"📝 Raw response: {response_text}")
                return []
                
        except Exception as e:
            print(f"❌ Error in LLM analysis: {e}")
            return []

# Create global instance
similar_tickets_tool = SimilarTicketSearchTool()

def find_similar_tickets(incident_description: str, current_incident_id: str = None, product: str = None,
                        ai_problem_stage: str = None, ai_key_log: str = None, ai_conclusion: str = None) -> List[SimilarTicket]:
    """
    Find similar tickets based on incident description and AI-generated fields
    
    Args:
        incident_description: Description of the current incident (Title)
        current_incident_id: ID of current incident to exclude from results
        product: Product name to filter tickets by (required)
        ai_problem_stage: AI-generated problem stage for similarity comparison
        ai_key_log: AI-generated key log for similarity comparison
        ai_conclusion: AI-generated conclusion for similarity comparison
        
    Returns:
        List of similar tickets with IncidentId, Title, Investigation, AI_Conclusion, AI_Solution, AI_TransferredTo
    """
    return similar_tickets_tool.find_similar_tickets(
        incident_description, current_incident_id, product, ai_problem_stage, ai_key_log, ai_conclusion
    )

# Example usage
if __name__ == "__main__":
    # Example of using the updated similar tickets tool
    print("🔍 Testing Similar Tickets Tool with new requirements...")
    
    # Test data
    current_title = "Pipeline deployment failure in production environment"
    current_ai_problem_stage = "Deployment Failed"
    current_ai_key_log = "Error: Unable to connect to deployment service. Connection timeout after 30 seconds"
    current_ai_conclusion = "Deployment service is unavailable or misconfigured"
    current_product = "pipeline"
    
    # Find similar tickets using the new parameters
    similar_tickets = find_similar_tickets(
        incident_description=current_title,
        current_incident_id="INC123456",  # Exclude this ticket from results
        product=current_product,          # Required: only compare within same product
        ai_problem_stage=current_ai_problem_stage,
        ai_key_log=current_ai_key_log,
        ai_conclusion=current_ai_conclusion
    )
    
    print(f"\n📊 Found {len(similar_tickets)} similar tickets:")
    for i, ticket in enumerate(similar_tickets, 1):
        print(f"\n🎫 Similar Ticket #{i}:")
        print(f"   IncidentId: {ticket.incident_id}")
        print(f"   Title: {ticket.title}")
        print(f"   Investigation: {ticket.investigation[:100]}{'...' if len(ticket.investigation) > 100 else ''}")
        print(f"   AI_Conclusion: {ticket.ai_conclusion}")
        print(f"   AI_Solution: {ticket.ai_solution}")
        print(f"   AI_TransferredTo: {ticket.ai_transferred_to}")
        print(f"   Similarity Score: {ticket.similarity_score}%")
        print(f"   Similarity Reason: {ticket.similarity_reason}")