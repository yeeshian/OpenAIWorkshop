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
    <Paper elevation={3} sx={{ p: 1.5, display: 'flex', flexDirection: 'column', gap: 1 }}>
      <Typography variant="subtitle1" fontWeight="bold" sx={{ mb: 0.5 }}>
        Workflow Control
      </Typography>

      <FormControl fullWidth size="small">
        <InputLabel sx={{ fontSize: '0.875rem' }}>Select Alert</InputLabel>
        <Select
          value={selectedAlertId}
          label="Select Alert"
          onChange={(e) => setSelectedAlertId(e.target.value)}
          disabled={workflowRunning}
          sx={{ fontSize: '0.875rem' }}
        >
          {alerts.map((alert) => (
            <MenuItem key={alert.alert_id} value={alert.alert_id} sx={{ py: 0.75 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, width: '100%' }}>
                {getSeverityIcon(alert.severity)}
                <Box sx={{ flex: 1 }}>
                  <Typography variant="caption" fontWeight="bold" display="block">
                    {alert.alert_id}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem' }}>
                    {alert.alert_type}
                  </Typography>
                </Box>
                <Chip
                  label={alert.severity}
                  size="small"
                  color={getSeverityColor(alert.severity)}
                  sx={{ height: 18, fontSize: '0.7rem' }}
                />
              </Box>
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      {selectedAlertId && !workflowRunning && (
        <Box sx={{ p: 1, bgcolor: 'grey.100', borderRadius: 1 }}>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
            <strong>Description:</strong>
          </Typography>
          <Typography variant="caption" display="block" sx={{ mb: 0.5 }}>
            {alerts.find((a) => a.alert_id === selectedAlertId)?.description}
          </Typography>
          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
            <Chip
              label={`Customer ${alerts.find((a) => a.alert_id === selectedAlertId)?.customer_id}`}
              size="small"
              variant="outlined"
              sx={{ height: 18, fontSize: '0.7rem' }}
            />
            <Chip
              label={alerts.find((a) => a.alert_id === selectedAlertId)?.alert_type}
              size="small"
              variant="outlined"
              sx={{ height: 18, fontSize: '0.7rem' }}
            />
          </Box>
        </Box>
      )}

      <Button
        variant="contained"
        size="small"
        fullWidth
        startIcon={workflowRunning ? <CircularProgress size={16} color="inherit" /> : <PlayArrowIcon fontSize="small" />}
        onClick={handleStartClick}
        disabled={!selectedAlertId || workflowRunning}
        sx={{ mt: 0.5, py: 0.75, fontSize: '0.875rem' }}
      >
        {workflowRunning ? 'Running...' : 'Start Workflow'}
      </Button>

      {selectedAlert && workflowRunning && (
        <Box sx={{ p: 1, bgcolor: 'primary.main', color: 'white', borderRadius: 1 }}>
          <Typography variant="caption" fontWeight="bold" display="block">
            Active Workflow
          </Typography>
          <Typography variant="caption" sx={{ fontSize: '0.7rem' }}>
            Processing {selectedAlert.alert_id}
          </Typography>
        </Box>
      )}
    </Paper>
  );
}

export default ControlPanel;
