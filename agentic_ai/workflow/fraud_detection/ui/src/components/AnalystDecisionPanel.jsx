import React, { useState } from 'react';
import {
  Paper,
  Box,
  Typography,
  Button,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Chip,
  Alert,
  Divider,
} from '@mui/material';
import GavelIcon from '@mui/icons-material/Gavel';
import SendIcon from '@mui/icons-material/Send';

const ACTION_OPTIONS = [
  { value: 'clear', label: 'Clear - No Action Needed', color: 'success' },
  { value: 'lock_account', label: 'Lock Account', color: 'error' },
  { value: 'refund_charges', label: 'Refund Charges', color: 'warning' },
  { value: 'both', label: 'Lock Account & Refund', color: 'error' },
];

function AnalystDecisionPanel({ decision, onSubmit }) {
  const [selectedAction, setSelectedAction] = useState(
    decision.data?.recommended_action || 'clear'
  );
  const [notes, setNotes] = useState('');

  const handleSubmit = () => {
    onSubmit({
      request_id: decision.request_id,
      alert_id: decision.data.alert_id,
      customer_id: decision.data.customer_id,
      approved_action: selectedAction,
      analyst_notes: notes || 'Analyst decision from UI',
      analyst_id: 'analyst_ui',
    });
  };

  const getRiskColor = (score) => {
    if (score >= 0.8) return 'error';
    if (score >= 0.6) return 'warning';
    if (score >= 0.3) return 'info';
    return 'success';
  };

  const getRiskLevel = (score) => {
    if (score >= 0.8) return 'Critical';
    if (score >= 0.6) return 'High';
    if (score >= 0.3) return 'Medium';
    return 'Low';
  };

  return (
    <Paper
      elevation={3}
      sx={{
        p: 3,
        display: 'flex',
        flexDirection: 'column',
        gap: 2,
        border: 3,
        borderColor: 'warning.main',
        animation: 'pulse 2s ease-in-out infinite',
        '@keyframes pulse': {
          '0%, 100%': { borderColor: '#ff9800' },
          '50%': { borderColor: '#ffc107' },
        },
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <GavelIcon color="warning" />
        <Typography variant="h6">Analyst Review Required</Typography>
      </Box>

      <Alert severity="warning" sx={{ mb: 1 }}>
        <Typography variant="body2" fontWeight="bold">
          Human Decision Needed
        </Typography>
        <Typography variant="caption">
          The workflow is paused pending your review
        </Typography>
      </Alert>

      <Divider />

      {/* Risk Assessment */}
      <Box>
        <Typography variant="subtitle2" gutterBottom>
          Risk Assessment
        </Typography>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', mb: 1 }}>
          <Typography variant="body2">Risk Score:</Typography>
          <Chip
            label={`${(decision.data?.risk_score || 0).toFixed(2)} - ${getRiskLevel(
              decision.data?.risk_score || 0
            )}`}
            color={getRiskColor(decision.data?.risk_score || 0)}
            size="small"
          />
        </Box>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          <Typography variant="body2">Alert ID:</Typography>
          <Chip label={decision.data?.alert_id} size="small" variant="outlined" />
        </Box>
      </Box>

      {/* Reasoning */}
      {decision.data?.reasoning && (
        <Box>
          <Typography variant="subtitle2" gutterBottom>
            AI Analysis
          </Typography>
          <Paper variant="outlined" sx={{ p: 1.5, bgcolor: 'grey.50', maxHeight: 150, overflow: 'auto' }}>
            <Typography variant="caption" sx={{ whiteSpace: 'pre-wrap' }}>
              {decision.data.reasoning}
            </Typography>
          </Paper>
        </Box>
      )}

      {/* Recommended Action */}
      <Box>
        <Typography variant="subtitle2" gutterBottom>
          Recommended Action
        </Typography>
        <Chip
          label={
            ACTION_OPTIONS.find((opt) => opt.value === decision.data?.recommended_action)
              ?.label || 'Unknown'
          }
          color={
            ACTION_OPTIONS.find((opt) => opt.value === decision.data?.recommended_action)
              ?.color || 'default'
          }
          size="medium"
        />
      </Box>

      <Divider />

      {/* Decision Form */}
      <FormControl fullWidth>
        <InputLabel>Your Decision</InputLabel>
        <Select
          value={selectedAction}
          label="Your Decision"
          onChange={(e) => setSelectedAction(e.target.value)}
        >
          {ACTION_OPTIONS.map((option) => (
            <MenuItem key={option.value} value={option.value}>
              {option.label}
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      <TextField
        label="Analyst Notes"
        multiline
        rows={3}
        fullWidth
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Add your analysis and reasoning..."
      />

      <Button
        variant="contained"
        color="primary"
        size="large"
        fullWidth
        startIcon={<SendIcon />}
        onClick={handleSubmit}
      >
        Submit Decision
      </Button>
    </Paper>
  );
}

export default AnalystDecisionPanel;
