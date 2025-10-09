import React, { useRef, useEffect } from 'react';
import {
  Paper,
  Box,
  Typography,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Chip,
  Divider,
} from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import InfoIcon from '@mui/icons-material/Info';
import GavelIcon from '@mui/icons-material/Gavel';
import ErrorIcon from '@mui/icons-material/Error';

const getEventIcon = (event) => {
  switch (event.event_type) {
    case 'executor_invoked':
      return <PlayArrowIcon color="primary" />;
    case 'executor_completed':
      return <CheckCircleIcon color="success" />;
    case 'status_change':
      return <InfoIcon color="info" />;
    case 'workflow_output':
      return <CheckCircleIcon color="success" />;
    default:
      if (event.type === 'decision_required') {
        return <GavelIcon color="warning" />;
      }
      if (event.type === 'workflow_error') {
        return <ErrorIcon color="error" />;
      }
      return <InfoIcon />;
  }
};

const getEventColor = (event) => {
  switch (event.event_type) {
    case 'executor_invoked':
      return 'primary';
    case 'executor_completed':
      return 'success';
    case 'status_change':
      return 'info';
    case 'workflow_output':
      return 'success';
    default:
      if (event.type === 'decision_required') {
        return 'warning';
      }
      if (event.type === 'workflow_error') {
        return 'error';
      }
      return 'default';
  }
};

const getEventTitle = (event) => {
  if (event.event_type === 'executor_invoked') {
    return `${event.executor_id} started`;
  }
  if (event.event_type === 'executor_completed') {
    return `${event.executor_id} completed`;
  }
  if (event.event_type === 'status_change') {
    return `Status: ${event.status}`;
  }
  if (event.event_type === 'workflow_output') {
    return 'Workflow Output';
  }
  if (event.type === 'decision_required') {
    return 'Decision Required';
  }
  if (event.type === 'workflow_started') {
    return 'Workflow Started';
  }
  if (event.type === 'workflow_completed') {
    return 'Workflow Completed';
  }
  if (event.type === 'workflow_error') {
    return 'Error Occurred';
  }
  return event.type || 'Event';
};

function EventLog({ events }) {
  const listRef = useRef(null);

  // Auto-scroll to bottom when new events arrive
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [events]);

  const formatTime = (timestamp) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', { 
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  return (
    <Paper elevation={3} sx={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <Box sx={{ p: 1.5, borderBottom: 1, borderColor: 'divider', flexShrink: 0 }}>
        <Typography variant="subtitle1" fontWeight="bold">Event Log</Typography>
        <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem' }}>
          {events.length} events
        </Typography>
      </Box>

      <List
        ref={listRef}
        sx={{
          flex: 1,
          overflow: 'auto',
          px: 0.5,
          py: 0,
          minHeight: 0,
          '&::-webkit-scrollbar': {
            width: '8px',
          },
          '&::-webkit-scrollbar-track': {
            backgroundColor: 'grey.100',
          },
          '&::-webkit-scrollbar-thumb': {
            backgroundColor: 'grey.400',
            borderRadius: '4px',
            '&:hover': {
              backgroundColor: 'grey.600',
            },
          },
        }}
      >
        {events.length === 0 ? (
          <Box sx={{ p: 2, textAlign: 'center' }}>
            <Typography variant="caption" color="text.secondary">
              No events yet. Start a workflow to see events.
            </Typography>
          </Box>
        ) : (
          events.map((event, index) => (
            <React.Fragment key={index}>
              <ListItem
                sx={{
                  py: 0.75,
                  px: 0.75,
                  '&:hover': {
                    bgcolor: 'action.hover',
                  },
                }}
              >
                <ListItemIcon sx={{ minWidth: 32 }}>
                  {React.cloneElement(getEventIcon(event), { fontSize: 'small' })}
                </ListItemIcon>
                <ListItemText
                  primary={
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, flexWrap: 'wrap' }}>
                      <Typography variant="caption" fontWeight="medium" sx={{ fontSize: '0.75rem' }}>
                        {getEventTitle(event)}
                      </Typography>
                      <Chip
                        label={event.event_type || event.type}
                        size="small"
                        color={getEventColor(event)}
                        sx={{ height: 16, fontSize: '0.65rem' }}
                      />
                    </Box>
                  }
                  secondary={
                    <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.65rem' }}>
                      {formatTime(event.timestamp)}
                    </Typography>
                  }
                />
              </ListItem>
              {index < events.length - 1 && <Divider variant="inset" component="li" sx={{ ml: 4 }} />}
            </React.Fragment>
          ))
        )}
      </List>
    </Paper>
  );
}

export default EventLog;
