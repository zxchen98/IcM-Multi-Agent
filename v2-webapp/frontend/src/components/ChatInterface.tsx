import React, { useState, useEffect, useRef } from 'react';
import { Button, Card, CardBody, Spinner } from '@heroui/react';
import { PaperAirplaneIcon } from '@heroicons/react/24/solid';
import MessageBubble from './MessageBubble';
import { ChatSession } from '../types';

interface ChatInterfaceProps {
  onProcessTicket: (ticketId: string) => Promise<void>;
  chatSession: ChatSession | null;
  isLoading: boolean;
  error: string | null;
}

const ChatInterface: React.FC<ChatInterfaceProps> = ({
  onProcessTicket,
  chatSession,
  isLoading,
  error
}) => {
  const [ticketId, setTicketId] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [chatSession?.messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ticketId.trim() || isProcessing) return;

    setIsProcessing(true);
    try {
      await onProcessTicket(ticketId.trim());
      setTicketId('');
    } catch (error) {
      console.error('Failed to process ticket:', error);
    } finally {
      setIsProcessing(false);
    }
  };

  const renderStatus = () => {
    if (!chatSession) return null;

    const statusColors = {
      active: 'text-blue-600 bg-blue-50',
      completed: 'text-green-600 bg-green-50',
      error: 'text-red-600 bg-red-50'
    };

    return (
      <div className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${statusColors[chatSession.status]}`}>
        <div className={`w-2 h-2 rounded-full mr-2 ${
          chatSession.status === 'active' ? 'bg-blue-600 animate-pulse' :
          chatSession.status === 'completed' ? 'bg-green-600' : 'bg-red-600'
        }`} />
        {chatSession.status === 'active' ? 'Processing' :
         chatSession.status === 'completed' ? 'Completed' : 'Error'}
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full max-w-6xl mx-auto p-4">
      {/* Main Container with rounded border */}
      <div className="flex flex-col h-full bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
        {/* Header */}
        <div className="border-b border-gray-200 p-6 bg-gray-50">
          <div className="flex items-center justify-between">
            <h1 className="text-2xl font-bold text-gray-900">
              IcM Multi-Agent System
            </h1>
            {chatSession && (
              <div className="flex items-center gap-4">
                <span className="text-sm text-gray-600">
                  Ticket ID: <span className="font-mono font-medium">{chatSession.ticketId}</span>
                </span>
                {renderStatus()}
              </div>
            )}
          </div>
        </div>

        {/* Chat Messages */}
        <div className="flex-1 overflow-hidden">
          {chatSession ? (
            <div className="h-full overflow-y-auto p-6 scrollbar-hide">
              <div className="space-y-2">
                {chatSession.messages.map((message) => (
                  <MessageBubble 
                    key={message.id} 
                    message={message} 
                  />
                ))}
                {isLoading && (
                  <div className="flex justify-center p-4">
                                      <div className="flex items-center gap-2 text-gray-600">
                    <Spinner size="sm" />
                    <span>Agents are processing...</span>
                  </div>
                  </div>
                )}
              </div>
              <div ref={messagesEndRef} />
            </div>
          ) : (
            <div className="flex items-center justify-center h-full p-6">
              <Card className="w-full max-w-md shadow-sm">
                <CardBody className="text-center p-8">
                  <div className="text-4xl mb-4">🤖</div>
                  <h2 className="text-xl font-semibold mb-2">Welcome to PPP IcM Multi-Agent System</h2>
                  <p className="text-gray-600 mb-4">
                    Enter a Ticket ID to start processing
                  </p>
                </CardBody>
              </Card>
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="border-t border-gray-200 p-6 bg-gray-50">
          <form onSubmit={handleSubmit} className="flex gap-3 items-center">
            <div className="flex-1 relative">
              <textarea
                value={ticketId}
                onChange={(e) => setTicketId(e.target.value)}
                placeholder="Enter Ticket ID here (e.g., 669533608)"
                disabled={isProcessing || isLoading}
                rows={2}
                className="w-full px-4 py-3 text-base border border-gray-300 rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-opacity-30 focus:border-blue-500 hover:border-gray-400 transition-all duration-200"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    if (ticketId.trim() && !isProcessing && !isLoading) {
                      handleSubmit(e as any);
                    }
                  }
                }}
              />
            </div>
            <Button
              type="submit"
              variant="bordered"
              disabled={!ticketId.trim() || isProcessing || isLoading}
              isLoading={isProcessing}
              className="px-4 py-2 border-gray-300 hover:border-gray-400 hover:bg-gray-50 text-gray-700 h-10 min-w-[2.5rem] flex items-center justify-center"
            >
              {isProcessing ? 'Processing...' : <PaperAirplaneIcon className="w-5 h-5" />}
            </Button>
          </form>
          
          {error && (
            <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-md">
              <p className="text-red-800 text-sm">{error}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ChatInterface; 