import React, { useState, useCallback, useEffect } from 'react';
import {
  Box,
  ThemeProvider,
  createTheme,
  CssBaseline,
  AppBar,
  Toolbar,
  Typography,
  Container,
  Paper,
  Grid,
} from '@mui/material';
import SecurityIcon from '@mui/icons-material/Security';
import WorkflowVisualizer from './components/WorkflowVisualizer';
import ControlPanel from './components/ControlPanel';
import AnalystDecisionPanel from './components/AnalystDecisionPanel';
import EventLog from './components/EventLog';
import { useWebSocket } from './hooks/useWebSocket';

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: '#dc004e',
    },
    success: {
      main: '#4caf50',
    },
    warning: {
      main: '#ff9800',
    },
    error: {
      main: '#f44336',
    },
  },
  typography: {
    fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
  },
});

function App() {
  const [alerts, setAlerts] = useState([]);
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [workflowRunning, setWorkflowRunning] = useState(false);
  const [events, setEvents] = useState([]);
  const [pendingDecision, setPendingDecision] = useState(null);
  const [executorStates, setExecutorStates] = useState({});

  // WebSocket hook for real-time updates
  const { lastMessage, sendMessage } = useWebSocket('ws://localhost:8001/ws');

  // Load sample alerts on mount
  useEffect(() => {
    fetch('/api/alerts')
      .then((res) => res.json())
      .then((data) => setAlerts(data.alerts))
      .catch((err) => console.error('Error loading alerts:', err));
  }, []);

  // Handle WebSocket messages
  useEffect(() => {
    if (!lastMessage) return;

    try {
      const event = lastMessage;

      // Add to event log - prevent duplicates by checking timestamp + type + executor_id
      setEvents((prev) => {
        const eventKey = `${event.timestamp}-${event.type || event.event_type}-${event.executor_id || ''}`;
        const isDuplicate = prev.some(
          (e) => `${e.timestamp}-${e.type || e.event_type}-${e.executor_id || ''}` === eventKey
        );
        return isDuplicate ? prev : [...prev, event];
      });

      // Handle workflow initialization
      if (event.type === 'workflow_initializing') {
        // Keep workflow running flag true, just show initialization message
      }

      // Handle workflow started
      if (event.type === 'workflow_started') {
        // Workflow is now running
      }

      // Update executor states based on event type
      if (event.event_type === 'executor_invoked') {
        setExecutorStates((prev) => ({
          ...prev,
          [event.executor_id]: 'running',
        }));
      } else if (event.event_type === 'executor_completed') {
        setExecutorStates((prev) => ({
          ...prev,
          [event.executor_id]: 'completed',
        }));
      }

      // Handle decision required
      if (event.type === 'decision_required') {
        setPendingDecision(event);
        setWorkflowRunning(false);
      }

      // Handle workflow completion
      if (event.type === 'workflow_completed' || event.type === 'workflow_error') {
        setWorkflowRunning(false);
        // Keep all executor states as-is (they should already be 'completed')
      }
    } catch (error) {
      console.error('Error handling WebSocket message:', error);
    }
  }, [lastMessage]);

  const handleStartWorkflow = useCallback(async (alert) => {
    console.log('Starting workflow for alert:', alert);
    setSelectedAlert(alert);
    setWorkflowRunning(true);
    setEvents([]);
    setExecutorStates({});
    setPendingDecision(null);

    try {
      const response = await fetch('/api/workflow/start', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(alert),
      });

      const data = await response.json();
      console.log('Workflow started:', data);
    } catch (error) {
      console.error('Error starting workflow:', error);
      setWorkflowRunning(false);
    }
  }, []);

  const handleSubmitDecision = useCallback(async (decision) => {
    console.log('Submitting decision:', decision);

    try {
      const response = await fetch('/api/workflow/decision', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(decision),
      });

      const data = await response.json();
      console.log('Decision submitted:', data);

      setPendingDecision(null);
      setWorkflowRunning(true);
    } catch (error) {
      console.error('Error submitting decision:', error);
    }
  }, []);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
        {/* App Bar */}
        <AppBar position="static" elevation={2}>
          <Toolbar>
            <SecurityIcon sx={{ mr: 2 }} />
            <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
              Fraud Detection Workflow Visualizer
            </Typography>
            <Typography variant="body2" sx={{ opacity: 0.8 }}>
              Real-time Multi-Agent Workflow Monitoring
            </Typography>
          </Toolbar>
        </AppBar>

        {/* Main Content */}
        <Container maxWidth={false} sx={{ flex: 1, py: 3, overflow: 'hidden' }}>
          <Grid container spacing={2} sx={{ height: '100%' }}>
            {/* Left Column - Controls and Decision Panel */}
            <Grid item xs={12} md={3} sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <ControlPanel
                alerts={alerts}
                onStartWorkflow={handleStartWorkflow}
                workflowRunning={workflowRunning}
                selectedAlert={selectedAlert}
              />

              {pendingDecision && (
                <AnalystDecisionPanel
                  decision={pendingDecision}
                  onSubmit={handleSubmitDecision}
                />
              )}
            </Grid>

            {/* Center Column - Workflow Visualization */}
            <Grid item xs={12} md={6}>
              <Paper elevation={3} sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider' }}>
                  <Typography variant="h6">Workflow Graph</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {selectedAlert
                      ? `Alert: ${selectedAlert.alert_id} - ${selectedAlert.description}`
                      : 'Select an alert to start'}
                  </Typography>
                </Box>
                <Box sx={{ flex: 1, position: 'relative' }}>
                  <WorkflowVisualizer executorStates={executorStates} />
                </Box>
              </Paper>
            </Grid>

            {/* Right Column - Event Log */}
            <Grid item xs={12} md={3} sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
              <EventLog events={events} />
            </Grid>
          </Grid>
        </Container>
      </Box>
    </ThemeProvider>
  );
}

export default App;
