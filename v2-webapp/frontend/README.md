# IcM Multi-Agent System Frontend

This is a React.js-based frontend interface for displaying the ticket processing workflow of the IcM Multi-Agent System.

## Features

### 🤖 Multi-Agent Conversation Display
- **Conversational Interface**: Display agent interactions in chat format
- **Agent Identification**: Clearly show the name of the currently speaking agent
- **Real-time Status**: Display real-time status of ticket processing (Processing/Completed/Error)

### 🔧 Tool Call Visualization
- **Command Line Display**: Show executed commands in terminal style
- **Result Display**: Format and display tool execution results
- **Tool Identification**: Clearly identify the tool name being used

### 🔄 Agent Handoff Display
- **Handoff Process**: Visualize the handoff process between agents
- **Handoff Reason**: Display the reason and logic for handoffs
- **Process Tracking**: Complete record of processing workflow

### 📋 Final Report Generation
- **Markdown Rendering**: Support Markdown format report display
- **Structured Display**: Clear report structure and formatting
- **Complete Record**: Include problem analysis, solutions, and participating agents

## Tech Stack

- **React 19** - Frontend framework
- **TypeScript** - Type safety
- **Tailwind CSS** - Styling framework
- **HeroUI** - UI component library
- **React Markdown** - Markdown rendering
- **Vite** - Build tool

## Quick Start

### 1. Install Dependencies

```bash
cd frontend
npm install
```

### 2. Start Development Server

**Method 1: Using startup script (Recommended)**

Windows:
```bash
start-simple.bat
```

Linux/macOS:
```bash
./start-demo.sh
```

**Method 2: Manual start**
```bash
npm run dev
```

Project will start at `http://localhost:3000`.

### 3. Build Production Version

```bash
npm run build
```

## Project Structure

```
frontend/
├── src/
│   ├── components/          # React components
│   │   ├── ChatInterface.tsx    # Main chat interface
│   │   └── MessageBubble.tsx    # Message bubble component
│   ├── services/            # API services
│   │   └── api.ts              # API call wrapper
│   ├── types.ts             # TypeScript type definitions
│   ├── App.tsx              # Main application component
│   ├── main.tsx             # Application entry point
│   └── index.css            # Global styles
├── package.json             # Project configuration
├── vite.config.ts           # Vite configuration
├── tailwind.config.js       # Tailwind configuration
└── tsconfig.json            # TypeScript configuration
```

## Interface Preview

### Main Interface
- Welcome page prompting user to enter Ticket ID
- Clear input box and submit button

### Chat Interface
- **User Messages**: Blue bubbles, right-aligned
- **Agent Messages**: Gray bubbles, left-aligned, showing agent names
- **Tool Calls**: Green border, displaying commands and results
- **Agent Handoffs**: Yellow background, centered handoff information
- **Final Report**: Purple border, Markdown format rendering

### Status Indicators
- **Processing**: Blue pulsing indicator
- **Completed**: Green completion indicator
- **Error**: Red error indicator

## API Integration

Currently uses mock data for demonstration. To connect to actual backend API:

1. Modify `API_BASE_URL` in `src/services/api.ts`
2. Replace `mockProcessTicket` with `processTicket` in `App.tsx`
3. Ensure backend API returns data conforming to `ProcessTicketResponse` interface

## Custom Configuration

### Modify API Endpoint
Edit proxy configuration in `vite.config.ts`:

```typescript
server: {
  proxy: {
    '/api': {
      target: 'http://your-backend-url:port',
      changeOrigin: true,
    }
  }
}
```

### Custom Styles
- Global styles: Edit `src/index.css`
- Component styles: Use Tailwind CSS class names
- Theme configuration: Modify `tailwind.config.js`

## Development Notes

### Adding New Message Types
1. Extend `Message['type']` type in `src/types.ts`
2. Add corresponding rendering logic in `MessageBubble.tsx`
3. Update style and color configurations

### Adding New Agents
1. Add new agent responses in mock data
2. Ensure `agentName` field is set correctly
3. Can customize agent display styles

### Integrating Real API
1. Implement WebSocket connection for real-time updates
2. Add error handling and retry logic
3. Implement session persistence

## Deployment

### Using Nginx

```bash
# Build project
npm run build

# Deploy dist directory contents to Nginx
cp -r dist/* /var/www/html/
```

### Environment Variables
In production environment, API endpoints and other settings can be configured through environment variables.

## License

MIT License 