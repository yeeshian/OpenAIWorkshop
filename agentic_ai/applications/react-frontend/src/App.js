import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  Container,
  Paper,
  TextField,
  IconButton,
  Button,
  Typography,
  Drawer,
  AppBar,
  Toolbar,
  Divider,
  Chip,
  Card,
  CardContent,
  LinearProgress,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  ThemeProvider,
  createTheme,
  CssBaseline,
} from '@mui/material';
import {
  Send as SendIcon,
  Psychology as BrainIcon,
  SmartToy as AgentIcon,
  CheckCircle as CheckIcon,
  Visibility as VisibilityIcon,
  VisibilityOff as VisibilityOffIcon,
  Add as AddIcon,
  EmojiObjects as IdeaIcon,
  Assignment as PlanIcon,
  TrendingUp as ProgressIcon,
  CheckCircleOutline as ResultIcon,
  ExpandMore as ExpandMoreIcon,
} from '@mui/icons-material';
import ReactMarkdown from 'react-markdown';
import { v4 as uuidv4 } from 'uuid';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://localhost:7000';
const WS_URL = BACKEND_URL.replace('http://', 'ws://').replace('https://', 'wss://') + '/ws/chat';

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: '#dc004e',
    },
    background: {
      default: '#f5f5f5',
      paper: '#ffffff',
    },
  },
});

function App() {
  const [sessionId, setSessionId] = useState(() => uuidv4());
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [showInternalProcess, setShowInternalProcess] = useState(true);
  const [orchestratorEvents, setOrchestratorEvents] = useState([]);
  const [agentEvents, setAgentEvents] = useState({});
  const [currentAgents, setCurrentAgents] = useState(new Set());
  const [lastFinalAnswer, setLastFinalAnswer] = useState(null); // Track last final answer for deduplication

  const wsRef = useRef(null);
  const messagesEndRef = useRef(null);
  const processEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const scrollProcessToBottom = () => {
    processEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(scrollToBottom, [messages]);
  useEffect(scrollProcessToBottom, [orchestratorEvents, agentEvents]);

  useEffect(() => {
    // Connect to WebSocket
    const connectWebSocket = () => {
      const ws = new WebSocket(WS_URL);

      ws.onopen = () => {
        console.log('WebSocket connected');
        // Register session
        ws.send(JSON.stringify({
          session_id: sessionId,
          access_token: null,
        }));
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
      };

      ws.onclose = () => {
        console.log('WebSocket disconnected');
        // Reconnect after 3 seconds
        setTimeout(connectWebSocket, 3000);
      };

      wsRef.current = ws;
    };

    connectWebSocket();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [sessionId]);

  const handleWebSocketMessage = (event) => {
    const { type } = event;

    switch (type) {
      case 'orchestrator':
        // Add orchestrator event with deduplication (check last event content)
        setOrchestratorEvents((prev) => {
          const lastEvent = prev[prev.length - 1];
          // Skip if same kind and same content as last event
          if (lastEvent && lastEvent.kind === event.kind && lastEvent.content === event.content) {
            return prev;
          }
          return [...prev, event];
        });
        break;

      case 'agent_start':
        setCurrentAgents((prev) => new Set([...prev, event.agent_id]));
        setAgentEvents((prev) => {
          // Don't recreate if already exists
          if (prev[event.agent_id]) {
            return prev;
          }
          return {
            ...prev,
            [event.agent_id]: {
              name: event.agent_id.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
              tokens: [],
              complete: false,
            },
          };
        });
        break;

      case 'agent_token':
        setAgentEvents((prev) => ({
          ...prev,
          [event.agent_id]: {
            ...prev[event.agent_id],
            tokens: [...(prev[event.agent_id]?.tokens || []), event.content],
          },
        }));
        break;

      case 'agent_message':
        setCurrentAgents((prev) => {
          const newSet = new Set(prev);
          newSet.delete(event.agent_id);
          return newSet;
        });
        setAgentEvents((prev) => {
          // Don't update if already marked complete with same message
          const existing = prev[event.agent_id];
          if (existing?.complete && existing.finalMessage === event.content) {
            return prev;
          }
          return {
            ...prev,
            [event.agent_id]: {
              ...existing,
              finalMessage: event.content,
              complete: true,
            },
          };
        });
        break;

      case 'final_result':
        // Final answer from the workflow - check for duplicates
        if (event.content && event.content !== lastFinalAnswer) {
          setLastFinalAnswer(event.content);
          setMessages((prev) => [
            ...prev,
            {
              role: 'assistant',
              content: event.content,
              timestamp: new Date(),
            },
          ]);
        }
        setIsProcessing(false);
        break;

      case 'message':
        // Legacy message event (for Autogen compatibility)
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: event.content,
            timestamp: new Date(),
          },
        ]);
        setIsProcessing(false);
        break;

      case 'done':
        setIsProcessing(false);
        break;

      case 'error':
        console.error('Backend error:', event.message);
        setMessages((prev) => [
          ...prev,
          {
            role: 'error',
            content: `Error: ${event.message}`,
            timestamp: new Date(),
          },
        ]);
        setIsProcessing(false);
        break;

      default:
        break;
    }
  };

  const handleSend = () => {
    if (!input.trim() || !wsRef.current || isProcessing) return;

    // Add user message
    setMessages((prev) => [
      ...prev,
      {
        role: 'user',
        content: input,
        timestamp: new Date(),
      },
    ]);

    // Clear internal process for new request
    setOrchestratorEvents([]);
    setAgentEvents({});
    setCurrentAgents(new Set());
    setLastFinalAnswer(null); // Reset deduplication

    // Send to backend
    wsRef.current.send(JSON.stringify({
      session_id: sessionId,
      prompt: input,
      access_token: null,
    }));

    setInput('');
    setIsProcessing(true);
  };

  const handleNewSession = async () => {
    // Generate new session ID
    const newSessionId = uuidv4();
    
    // Clear all state
    setMessages([]);
    setInput('');
    setIsProcessing(false);
    setOrchestratorEvents([]);
    setAgentEvents({});
    setCurrentAgents(new Set());
    setLastFinalAnswer(null);

    // Close existing WebSocket
    if (wsRef.current) {
      wsRef.current.close();
    }

    // Call backend to reset old session (optional cleanup)
    try {
      await fetch(`${BACKEND_URL}/reset_session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId }),
      });
    } catch (error) {
      console.error('Error resetting session:', error);
    }

    // Update session ID (will trigger WebSocket reconnect via useEffect)
    setSessionId(newSessionId);
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Helper: Get icon and label for orchestrator event kind
  const getOrchestratorDisplay = (kind) => {
    switch (kind) {
      case 'plan':
        return { icon: <PlanIcon fontSize="small" />, label: '📋 Planning', color: 'primary', bgColor: '#e3f2fd' };
      case 'progress':
        return { icon: <ProgressIcon fontSize="small" />, label: '⚙️ Working', color: 'info', bgColor: '#e1f5fe' };
      case 'result':
        return { icon: <ResultIcon fontSize="small" />, label: '✅ Decision', color: 'success', bgColor: '#e8f5e9' };
      default:
        return { icon: <IdeaIcon fontSize="small" />, label: '💭 Thinking', color: 'default', bgColor: '#f5f5f5' };
    }
  };

  // Helper: Extract agent name from orchestrator content (if delegating)
  const extractDelegatedAgent = (content) => {
    const agentPatterns = [
      /crm_billing|billing|CRM|account/i,
      /product_promotions|promotion|product/i,
      /security_authentication|security|auth/i,
    ];
    const agentNames = ['💳 Billing Agent', '🎁 Promotions Agent', '🔒 Security Agent'];
    
    for (let i = 0; i < agentPatterns.length; i++) {
      if (agentPatterns[i].test(content)) {
        return agentNames[i];
      }
    }
    return null;
  };

  // Helper: Get creative emoji for agent
  const getAgentEmoji = (agentId) => {
    if (agentId.includes('crm') || agentId.includes('billing')) return '💳';
    if (agentId.includes('product') || agentId.includes('promotion')) return '🎁';
    if (agentId.includes('security') || agentId.includes('auth')) return '🔒';
    return '🤖';
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ display: 'flex', height: '100vh' }}>
        {/* Internal Process Drawer */}
        <Drawer
          variant="persistent"
          anchor="left"
          open={showInternalProcess}
          sx={{
            width: showInternalProcess ? 400 : 0,
            flexShrink: 0,
            '& .MuiDrawer-paper': {
              width: 400,
              boxSizing: 'border-box',
            },
          }}
        >
          <Toolbar />
          <Box sx={{ p: 2, overflow: 'auto', height: '100%' }}>
            <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <BrainIcon color="primary" />
              Internal Process
            </Typography>
            <Divider sx={{ mb: 2 }} />

            {/* Orchestrator Events */}
            {orchestratorEvents.length > 0 && (
              <Accordion defaultExpanded>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <BrainIcon fontSize="small" color="primary" />
                    Orchestrator ({orchestratorEvents.length})
                  </Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                    {orchestratorEvents.map((event, idx) => {
                      const display = getOrchestratorDisplay(event.kind);
                      const delegatedAgent = extractDelegatedAgent(event.content);
                      
                      return (
                        <Card key={idx} variant="outlined" sx={{ bgcolor: display.bgColor }}>
                          <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                              <Chip
                                icon={display.icon}
                                label={display.label}
                                size="small"
                                color={display.color}
                              />
                              {delegatedAgent && (
                                <Chip
                                  label={`→ ${delegatedAgent}`}
                                  size="small"
                                  variant="outlined"
                                  color="secondary"
                                />
                              )}
                            </Box>
                            <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                              {event.content}
                            </Typography>
                          </CardContent>
                        </Card>
                      );
                    })}
                  </Box>
                </AccordionDetails>
              </Accordion>
            )}

            {/* Agent Events */}
            {Object.entries(agentEvents).map(([agentId, agentData]) => {
              const agentEmoji = getAgentEmoji(agentId);
              return (
                <Accordion key={agentId} defaultExpanded={!agentData.complete}>
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Typography sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <span style={{ fontSize: '1.2em' }}>{agentEmoji}</span>
                      {agentData.name}
                      {currentAgents.has(agentId) && (
                        <Chip label="Working..." size="small" color="secondary" />
                      )}
                      {agentData.complete && (
                        <CheckIcon fontSize="small" color="success" />
                      )}
                    </Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Card variant="outlined" sx={{ bgcolor: '#fff3e0' }}>
                      <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
                        <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                          {agentData.finalMessage || agentData.tokens.join('')}
                        </Typography>
                      </CardContent>
                    </Card>
                  </AccordionDetails>
                </Accordion>
              );
            })}

            <div ref={processEndRef} />
          </Box>
        </Drawer>

        {/* Main Chat Area */}
        <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column' }}>
          {/* App Bar */}
          <AppBar position="static">
            <Toolbar>
              <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
                🤖 Magentic AI Assistant
              </Typography>
              <Button
                color="inherit"
                onClick={handleNewSession}
                startIcon={<AddIcon />}
                sx={{ mr: 2 }}
              >
                New Session
              </Button>
              <IconButton
                color="inherit"
                onClick={() => setShowInternalProcess(!showInternalProcess)}
              >
                {showInternalProcess ? <VisibilityOffIcon /> : <VisibilityIcon />}
              </IconButton>
            </Toolbar>
          </AppBar>

          {isProcessing && <LinearProgress />}

          {/* Messages */}
          <Box
            sx={{
              flexGrow: 1,
              overflow: 'auto',
              p: 3,
              bgcolor: 'background.default',
            }}
          >
            <Container maxWidth="md">
              {messages.length === 0 && (
                <Paper sx={{ p: 4, textAlign: 'center', bgcolor: 'background.paper' }}>
                  <Typography variant="h5" gutterBottom>
                    Welcome! 👋
                  </Typography>
                  <Typography color="text.secondary">
                    I'm a multi-agent AI assistant. Ask me about customer accounts, billing, promotions, or security.
                  </Typography>
                </Paper>
              )}

              {messages.map((msg, idx) => (
                <Paper
                  key={idx}
                  sx={{
                    p: 2,
                    mb: 2,
                    bgcolor: msg.role === 'user' ? '#e3f2fd' : msg.role === 'error' ? '#ffebee' : 'background.paper',
                  }}
                >
                  <Typography variant="caption" color="text.secondary" gutterBottom display="block">
                    {msg.role === 'user' ? 'You' : msg.role === 'error' ? 'Error' : 'Assistant'} •{' '}
                    {msg.timestamp.toLocaleTimeString()}
                  </Typography>
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                </Paper>
              ))}

              <div ref={messagesEndRef} />
            </Container>
          </Box>

          {/* Input Area */}
          <Paper
            sx={{
              p: 2,
              borderTop: 1,
              borderColor: 'divider',
            }}
          >
            <Container maxWidth="md">
              <Box sx={{ display: 'flex', gap: 1 }}>
                <TextField
                  fullWidth
                  multiline
                  maxRows={4}
                  placeholder="Type your message..."
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyPress={handleKeyPress}
                  disabled={isProcessing}
                />
                <IconButton
                  color="primary"
                  onClick={handleSend}
                  disabled={!input.trim() || isProcessing}
                  sx={{ alignSelf: 'flex-end' }}
                >
                  <SendIcon />
                </IconButton>
              </Box>
            </Container>
          </Paper>
        </Box>
      </Box>
    </ThemeProvider>
  );
}

export default App;
