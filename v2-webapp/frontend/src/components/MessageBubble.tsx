import React, { useState } from 'react';
import { Message } from '../types';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface MessageBubbleProps {
  message: Message;
}

function getBubbleStyles(type: Message['type']) {
  switch (type) {
    case 'user':
      return 'bg-blue-600 text-white shadow-sm ml-auto mr-0';
    case 'agent':
      return 'bg-white border border-gray-200 text-gray-800 shadow-sm mr-auto ml-0';
    case 'tool':
      return 'bg-green-50 border border-green-200 text-green-800 shadow-sm mr-auto ml-0';
    case 'tool_result':
      return 'bg-yellow-50 border border-yellow-200 text-yellow-800 shadow-sm mr-auto ml-0';
    case 'handoff':
      return 'bg-purple-50 border border-purple-200 text-purple-800 shadow-sm mr-auto ml-0';
    case 'report':
      return 'bg-blue-50 border border-blue-200 text-blue-800 shadow-sm mr-auto ml-0';
    default:
      return 'bg-gray-50 border border-gray-200 text-gray-800 shadow-sm mr-auto ml-0';
  }
}

function getIconForType(type: Message['type']) {
  switch (type) {
    case 'user':
      return '👤';
    case 'agent':
      return '🤖';
    case 'tool':
      return '🔧';
    case 'tool_result':
      return '📋';
    case 'handoff':
      return '🔄';
    case 'report':
      return '📊';
    default:
      return '💬';
  }
}

const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  
  const formatTimestamp = (timestamp: Date) => {
    return new Intl.DateTimeFormat('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    }).format(timestamp);
  };

  // Check if content is long and needs truncation
  const isLongContent = message.content && message.content.length > 2000;

  // Special rendering for handoff messages
  if (message.type === 'handoff') {
    return (
      <div className="flex justify-center my-6">
        <div className="flex items-center w-full max-w-4xl">
          <div className="flex-1 h-px bg-gradient-to-r from-transparent to-purple-300"></div>
          <div className="mx-4 px-4 py-2 bg-purple-100 border border-purple-300 rounded-full text-purple-800 text-sm font-medium flex items-center gap-2">
            <span>🔄</span>
            <span>
              {message.fromAgent && message.toAgent 
                ? `${message.fromAgent} → ${message.toAgent}`
                : 'Agent Handoff'
              }
            </span>
            {message.reason && (
              <span className="text-xs opacity-75">({message.reason})</span>
            )}
          </div>
          <div className="flex-1 h-px bg-gradient-to-l from-transparent to-purple-300"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex mb-4 w-full">
      <div className={`
        rounded-lg p-4 w-full max-w-4xl mx-auto
        ${getBubbleStyles(message.type)}
      `}>
        {/* Header with agent name and timestamp */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="text-sm">{getIconForType(message.type)}</span>
            <span className={`font-medium text-sm ${
              message.type === 'user' ? 'text-white' : 'text-gray-900'
            }`}>
              {message.agentName || (message.type === 'user' ? 'You' : message.type)}
            </span>
          </div>
          <span className={`text-xs ${
            message.type === 'user' ? 'text-blue-100' : 'opacity-70'
          }`}>
            {formatTimestamp(message.timestamp)}
            {/* Show loading indicator for progress messages */}
            {(message.content.includes('...') || 
              message.content.includes('Starting') ||
              message.content.includes('Processing') ||
              message.content.includes('Analyzing') ||
              message.content.match(/\.\.\.|\.\.$/)) && (
              <span className="ml-2 animate-pulse">⏳</span>
            )}
          </span>
        </div>

        {/* Tool command display */}
        {message.type === 'tool' && message.command && (
          <div className="mt-3 p-3 bg-gray-50 border border-gray-200 rounded text-xs font-mono">
            {/* Command output if available */}
            {message.content && (
              <div className="mt-2">
                <div className="font-medium text-gray-600 mb-1">Command:</div>
                <div className="bg-white p-2 rounded border border-gray-300">
                  <pre className="whitespace-pre-wrap text-xs text-gray-700">{message.content}</pre>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Regular content display */}
        {!(message.type === 'tool' && message.command) && (
          /* Regular content display */
          <div className={`whitespace-pre-wrap text-sm leading-relaxed ${
            message.type === 'user' 
              ? 'text-white' 
              : 'prose prose-sm max-w-none prose-gray'
          } ${
            // Add scrollable container for long content
            isLongContent
              ? `${isExpanded ? 'max-h-screen' : 'max-h-96'} overflow-y-auto border border-gray-200 rounded p-3 bg-gray-50`
              : ''
          }`}>
            {message.content && (
              message.type === 'user' ? (
                <div>{message.content}</div>
              ) : (
                <ReactMarkdown 
                  remarkPlugins={[remarkGfm]}
                  components={{
                    // Custom styling for long content
                    p: ({ children }) => (
                      <p className="mb-2 break-words">{children}</p>
                    ),
                    // Limit code block height
                    pre: ({ children }) => (
                      <pre className="max-h-32 overflow-y-auto bg-gray-100 p-2 rounded text-xs">
                        {children}
                      </pre>
                    )
                  }}
                >
                  {message.content}
                </ReactMarkdown>
              )
            )}
          </div>
        )}

        {/* Expand/Collapse button for long content */}
        {isLongContent && (
          <div className="mt-2">
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="text-xs text-blue-600 hover:text-blue-800 underline focus:outline-none"
            >
              {isExpanded ? '🔼 Show Less (Compact View)' : '🔽 Show More (Expanded View)'}
            </button>
          </div>
        )}

        {/* Tool result simple formatting */}
        {message.type === 'tool_result' && message.result && (
          <div className="mt-3 p-3 bg-white bg-opacity-50 rounded border text-xs font-mono">
            <div className="font-medium text-gray-600 mb-1">Result:</div>
            <pre className={`whitespace-pre-wrap overflow-x-auto ${
              // Add height limit for long results
              typeof message.result === 'string' && message.result.length > 1000
                ? 'max-h-48 overflow-y-auto'
                : ''
            }`}>
              {message.result}
            </pre>
          </div>
        )}

        {/* Status indicator (only for non-tool messages) */}
        {message.status && message.type !== 'tool_result' && (
          <div className="mt-2 text-xs">
            <span className={`inline-block px-2 py-1 rounded-full text-xs font-medium ${
              message.status === 'completed' ? 'bg-green-100 text-green-800' :
              message.status === 'running' ? 'bg-blue-100 text-blue-800' :
              message.status === 'failed' ? 'bg-red-100 text-red-800' :
              'bg-gray-100 text-gray-800'
            }`}>
              {message.status}
            </span>
          </div>
        )}
      </div>
    </div>
  );
};

export default MessageBubble;
