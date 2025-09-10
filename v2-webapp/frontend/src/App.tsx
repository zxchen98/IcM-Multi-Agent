import React, { useState, useRef, useEffect } from 'react';
import ChatInterface from './components/ChatInterface';
import { ChatSession, Message } from './types';
import { apiService } from './services/api';

const App: React.FC = () => {
  const [chatSession, setChatSession] = useState<ChatSession | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [useRealBackend, setUseRealBackend] = useState(true);
  const websocketRef = useRef<WebSocket | null>(null);

  // Cleanup WebSocket on unmount
  useEffect(() => {
    return () => {
      if (websocketRef.current) {
        websocketRef.current.close();
      }
    };
  }, []);

  const handleProcessTicket = async (ticketId: string) => {
    setIsLoading(true);
    setError(null);

    try {
      if (useRealBackend) {
        // Real backend with WebSocket streaming
        const response = await apiService.processTicket(ticketId);
        
        // Create user message
        const userMessage: Message = {
          id: `user_${Date.now()}`,
          type: 'user',
          content: `Process ticket: ${ticketId}`,
          timestamp: new Date(),
        };
        
        // Create new session with user message
        const newSession: ChatSession = {
          id: response.sessionId,
          ticketId: ticketId,
          messages: [userMessage],
          status: 'active',
          startTime: new Date(),
        };
        
        setChatSession(newSession);
        
        // Connect to WebSocket for real-time updates
        websocketRef.current = apiService.createWebSocketConnection(
          response.sessionId,
          (message: Message) => {
            setChatSession(prevSession => {
              if (!prevSession) return prevSession;
              
              const lastMessage = prevSession.messages[prevSession.messages.length - 1];
              
              // Check if this is a progress update from the same agent
              const shouldUpdateLastMessage = lastMessage &&
                lastMessage.agentName === message.agentName &&
                lastMessage.type === message.type &&
                message.type === 'agent' &&
                // Only update if the new message looks like a progress update
                (message.content.includes('...') || 
                 message.content.includes('Starting') ||
                 message.content.includes('Processing') ||
                 message.content.includes('Analyzing') ||
                 message.content.match(/\.\.\.|\.\.$/));
              
              let updatedMessages;
              if (shouldUpdateLastMessage) {
                // Update the last message instead of adding a new one
                updatedMessages = [
                  ...prevSession.messages.slice(0, -1),
                  { ...message, id: lastMessage.id } // Keep the same ID
                ];
              } else {
                // Add as new message
                updatedMessages = [...prevSession.messages, message];
              }
              
              const isCompleted = message.type === 'report';
              
              return {
                ...prevSession,
                messages: updatedMessages,
                status: isCompleted ? 'completed' : 'active',
                endTime: isCompleted ? new Date() : undefined,
              };
            });
          },
          ticketId
        );
        
      } else {
        // Fallback to mock data
        const response = await apiService.mockProcessTicket(ticketId);
        
        const newSession: ChatSession = {
          id: response.sessionId,
          ticketId: ticketId,
          messages: response.messages,
          status: response.status as 'active' | 'completed' | 'error',
          startTime: new Date(),
          endTime: response.status === 'completed' ? new Date() : undefined,
        };

        setChatSession(newSession);
      }
      
    } catch (err) {
      console.error('Error processing ticket:', err);
      setError(err instanceof Error ? err.message : 'Unknown error occurred while processing ticket');
      
      // Fallback to mock data if real backend fails
      if (useRealBackend) {
        console.log('Falling back to mock data...');
        setUseRealBackend(false);
        // Retry with mock data
        setTimeout(() => {
          handleProcessTicket(ticketId);
        }, 1000);
        return;
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      <ChatInterface
        onProcessTicket={handleProcessTicket}
        chatSession={chatSession}
        isLoading={isLoading}
        error={error}
      />
    </div>
  );
};

export default App; 