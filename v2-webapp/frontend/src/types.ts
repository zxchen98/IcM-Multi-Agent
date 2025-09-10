export interface Message {
  id: string;
  type: 'user' | 'agent' | 'tool' | 'tool_result' | 'handoff' | 'report';
  content: string;
  timestamp: Date;
  agentName?: string;
  toolName?: string;
  command?: string;
  result?: string;
  status?: string;
  fromAgent?: string;
  toAgent?: string;
  reason?: string;
}

export interface ChatSession {
  id: string;
  ticketId: string;
  messages: Message[];
  status: 'active' | 'completed' | 'error';
  startTime: Date;
  endTime?: Date;
  currentAgent?: string;
}

export interface AgentResponse {
  agentName: string;
  message: string;
  toolCalls?: ToolCall[];
  handoff?: {
    toAgent: string;
    reason: string;
  };
  isComplete?: boolean;
}

export interface ToolCall {
  toolName: string;
  command: string;
  result: string;
  success: boolean;
  timestamp: Date;
}

export interface ProcessTicketRequest {
  ticketId: string;
}

export interface ProcessTicketResponse {
  sessionId: string;
  messages: Message[];
  status: string;
} 