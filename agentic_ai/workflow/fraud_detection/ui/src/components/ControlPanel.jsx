import React, { useState } from 'react';
import {
  Paper,
  Box,
  Typography,
  Button,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Chip,
  CircularProgress,
} from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import WarningIcon from '@mui/icons-material/Warning';
import ErrorIcon from '@mui/icons-material/Error';
import InfoIcon from '@mui/icons-material/Info';

const getSeverityIcon = (severity) => {
  switch (severity) {
    case 'high':
      return <ErrorIcon color="error" />;
    case 'medium':
      return <WarningIcon color="warning" />;
    case 'low':
      return <InfoIcon color="info" />;
    default:
      return <InfoIcon />;
  }
};

const getSeverityColor = (severity) => {
  switch (severity) {
    case 'high':
      return 'error';
    case 'medium':
      return 'warning';
    case 'low':
      return 'info';
    default:
      return 'default';
  }
};

function ControlPanel({ alerts, onStartWorkflow, workflowRunning, selectedAlert }) {
  const [selectedAlertId, setSelectedAlertId] = useState('');

  const handleStartClick = () => {
    const alert = alerts.find((a) => a.alert_id === selectedAlertId);
    if (alert) {
      onStartWorkflow(alert);
    }
  };

  return (
    <Paper elevation={3} sx={{ p: 3, display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Typography variant="h6" gutterBottom>
        Workflow Control
      </Typography>

      <FormControl fullWidth>
        <InputLabel>Select Alert</InputLabel>
        <Select
          value={selectedAlertId}
          label="Select Alert"
          onChange={(e) => setSelectedAlertId(e.target.value)}
          disabled={workflowRunning}
        >
          {alerts.map((alert) => (
            <MenuItem key={alert.alert_id} value={alert.alert_id}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
                {getSeverityIcon(alert.severity)}
                <Box sx={{ flex: 1 }}>
                  <Typography variant="body2" fontWeight="bold">
                    {alert.alert_id}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {alert.alert_type}
                  </Typography>
                </Box>
                <Chip
                  label={alert.severity}
                  size="small"
                  color={getSeverityColor(alert.severity)}
                />
              </Box>
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      {selectedAlertId && !workflowRunning && (
        <Box sx={{ p: 2, bgcolor: 'grey.100', borderRadius: 1 }}>
          <Typography variant="body2" color="text.secondary" gutterBottom>
            <strong>Description:</strong>
          </Typography>
          <Typography variant="body2">
            {alerts.find((a) => a.alert_id === selectedAlertId)?.description}
          </Typography>
          <Box sx={{ mt: 1, display: 'flex', gap: 1 }}>
            <Chip
              label={`Customer ${alerts.find((a) => a.alert_id === selectedAlertId)?.customer_id}`}
              size="small"
              variant="outlined"
            />
            <Chip
              label={alerts.find((a) => a.alert_id === selectedAlertId)?.alert_type}
              size="small"
              variant="outlined"
            />
          </Box>
        </Box>
      )}

      <Button
        variant="contained"
        size="large"
        fullWidth
        startIcon={workflowRunning ? <CircularProgress size={20} color="inherit" /> : <PlayArrowIcon />}
        onClick={handleStartClick}
        disabled={!selectedAlertId || workflowRunning}
        sx={{ mt: 1 }}
      >
        {workflowRunning ? 'Workflow Running...' : 'Start Workflow'}
      </Button>

      {selectedAlert && workflowRunning && (
        <Box sx={{ p: 2, bgcolor: 'primary.main', color: 'white', borderRadius: 1 }}>
          <Typography variant="body2" fontWeight="bold">
            Active Workflow
          </Typography>
          <Typography variant="caption">
            Processing {selectedAlert.alert_id}
          </Typography>
        </Box>
      )}
    </Paper>
  );
}

export default ControlPanel;
