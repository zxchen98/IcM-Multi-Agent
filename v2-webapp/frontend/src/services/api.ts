import { ProcessTicketResponse, Message } from '../types';

const API_BASE_URL = 'http://localhost:8000/api';
const WS_BASE_URL = 'ws://localhost:8000/ws';

// Fallback URLs for development
const FALLBACK_API_BASE_URL = '/api';

class ApiService {
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const config: RequestInit = {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    };

    // Try primary API first, then fallback
    const urls = [`${API_BASE_URL}${endpoint}`, `${FALLBACK_API_BASE_URL}${endpoint}`];
    
    for (const url of urls) {
      try {
        console.log(`Trying API URL: ${url}`);
        const response = await fetch(url, config);
        
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return await response.json();
      } catch (error) {
        console.error(`API request failed for ${url}:`, error);
        if (url === urls[urls.length - 1]) {
          // Last URL failed, throw error
          throw error;
        }
        // Continue to next URL
      }
    }
    
    throw new Error('All API endpoints failed');
  }

  async processTicket(ticketId: string): Promise<{ sessionId: string; status: string }> {
    return this.request<{ sessionId: string; status: string }>('/process-ticket', {
      method: 'POST',
      body: JSON.stringify({ ticket_id: ticketId }),
    });
  }

  async getSessionStatus(sessionId: string): Promise<{
    status: string;
    messages: Message[];
  }> {
    return this.request(`/session/${sessionId}/status`);
  }

  createWebSocketConnection(_sessionId: string, onMessage: (message: Message) => void, ticketId?: string): WebSocket {
    const ws = new WebSocket(WS_BASE_URL);
    
    ws.onopen = () => {
      console.log('WebSocket connected');
      // Send ticket processing request if ticketId is provided
      if (ticketId) {
        ws.send(JSON.stringify({
          action: 'process_ticket',
          ticket_id: ticketId
        }));
      }
    };
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'heartbeat') {
          // Handle heartbeat
          return;
        }
        
        // Convert timestamp string to Date object and ensure we have an ID
        const message: Message = {
          id: data.id || `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
          type: data.type,
          content: data.content || data.reason || '',  // Use reason as content for handoff messages
          timestamp: new Date(data.timestamp),
          agentName: data.agent_name,
          toolName: data.tool_name,
          command: data.command,
          result: data.result,
          status: data.status,
          fromAgent: data.from_agent,
          toAgent: data.to_agent,
        };
        
        // Debug logging to help with troubleshooting
        console.log('Received WebSocket message:', {
          type: message.type,
          agentName: message.agentName,
          toolName: message.toolName,
          hasContent: !!message.content,
          hasCommand: !!message.command,
          hasResult: !!message.result
        });
        
        onMessage(message);
      } catch (error) {
        console.error('Error parsing WebSocket message:', error);
      }
    };
    
    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
    
    ws.onclose = () => {
      console.log('WebSocket disconnected');
    };
    
    return ws;
  }

  async healthCheck(): Promise<{ status: string }> {
    return this.request('/health');
  }

  // Mock data for development and testing
  async mockProcessTicket(ticketId: string): Promise<ProcessTicketResponse> {
    // Simulate API delay
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    const sessionId = `session_${Date.now()}`;
    const mockMessages: Message[] = [
      {
        id: '1',
        type: 'user',
        content: `Process ticket: ${ticketId}`,
        timestamp: new Date(),
      },
      {
        id: '2',
        type: 'agent',
        content: 'Hello! I am the Master Agent, analyzing your ticket...',
        timestamp: new Date(),
        agentName: 'Master Agent',
      },
      {
        id: '3',
        type: 'tool',
        content: '',
        timestamp: new Date(),
        toolName: 'Kusto Query Tool',
        command: `KustoQuery | where TicketId == "${ticketId}" | project *`,
        result: `Found ticket information:
Title: Pipeline execution failed
Product: Azure DevOps
Team: Pipeline Agent
Severity: High
Status: Active`,
      },
      {
        id: '4',
        type: 'handoff',
        content: 'Based on ticket analysis, this is a Pipeline-related issue. Handing off to Pipeline agent for processing.',
        timestamp: new Date(),
        fromAgent: 'Master Agent',
        toAgent: 'Pipeline Agent',
      },
      {
        id: '5',
        type: 'agent',
        content: 'I am the Pipeline Agent, analyzing this pipeline execution failure issue...',
        timestamp: new Date(),
        agentName: 'Pipeline Agent',
      },
      {
        id: '6',
        type: 'tool',
        content: '',
        timestamp: new Date(),
        toolName: 'Azure CLI Tool',
        command: 'az pipelines runs show --id 12345',
        result: `Pipeline execution details:
Run ID: 12345
Status: Failed
Failed Stage: Build
Error Message: MSBuild failed with exit code 1
Duration: 5m 32s`,
      },
      {
        id: '7',
        type: 'handoff',
        content: 'This is a build failure issue that requires a specialized Build Failure Specialist to resolve.',
        timestamp: new Date(),
        fromAgent: 'Pipeline Agent',
        toAgent: 'Build Failure Specialist',
      },
      {
        id: '8',
        type: 'agent',
        content: 'I am the Build Failure Specialist, conducting in-depth analysis of the root cause of this build failure...',
        timestamp: new Date(),
        agentName: 'Build Failure Specialist',
      },
      {
        id: '9',
        type: 'tool',
        content: '',
        timestamp: new Date(),
        toolName: 'Log Analysis Tool',
        command: 'analyze-build-logs --run-id 12345',
        result: `Build log analysis results:
Error Type: Compilation Error
File: src/main.cs:45
Error: CS0103: The name 'variableName' does not exist in the current context
Suggestion: Check variable name spelling or ensure variable is declared`,
      },
      {
        id: '10',
        type: 'report',
        content: `# Ticket Processing Report

## Ticket Information
- **Ticket ID**: ${ticketId}
- **Title**: Pipeline execution failed
- **Product**: Azure DevOps
- **Severity**: High

## Problem Analysis
Through multi-agent collaborative analysis, the problem has been identified as:
- **Root Cause**: Code compilation error
- **Specific Location**: src/main.cs line 45
- **Error Type**: CS0103 - Variable name does not exist

## Solution
1. Check the variable name spelling on line 45 of src/main.cs file
2. Ensure variable 'variableName' is properly declared
3. Resubmit code and trigger build

## Participating Agents
1. **Master Agent** - Initial ticket analysis and routing
2. **Pipeline Agent** - Professional Pipeline issue analysis
3. **Build Failure Specialist** - In-depth build failure diagnosis

## Recommended Follow-up Actions
- Contact development team to fix code issues
- Verify build results after fix
- Update ticket status to resolved`,
        timestamp: new Date(),
      },
    ];

    return {
      sessionId,
      messages: mockMessages,
      status: 'completed',
    };
  }
}

export const apiService = new ApiService(); 