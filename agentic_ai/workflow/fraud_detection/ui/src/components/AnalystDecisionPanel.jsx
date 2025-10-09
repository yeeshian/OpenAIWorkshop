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
        p: 1.5,
        display: 'flex',
        flexDirection: 'column',
        gap: 1,
        border: 3,
        borderColor: 'warning.main',
        animation: 'pulse 2s ease-in-out infinite',
        '@keyframes pulse': {
          '0%, 100%': { borderColor: '#ff9800' },
          '50%': { borderColor: '#ffc107' },
        },
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
        <GavelIcon color="warning" fontSize="small" />
        <Typography variant="subtitle1" fontWeight="bold">Analyst Review Required</Typography>
      </Box>

      <Alert severity="warning" sx={{ py: 0.25, px: 1 }}>
        <Typography variant="caption" fontWeight="bold">
          Human Decision Needed
        </Typography>
      </Alert>

      <Divider sx={{ my: 0.5 }} />

      {/* Risk Assessment */}
      <Box>
        <Typography variant="caption" fontWeight="bold" display="block" sx={{ mb: 0.5 }}>
          Risk Assessment
        </Typography>
        <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', mb: 0.5 }}>
          <Typography variant="caption">Risk Score:</Typography>
          <Chip
            label={`${(decision.data?.risk_score || 0).toFixed(2)} - ${getRiskLevel(
              decision.data?.risk_score || 0
            )}`}
            color={getRiskColor(decision.data?.risk_score || 0)}
            size="small"
            sx={{ height: 20, fontSize: '0.7rem' }}
          />
        </Box>
        <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center' }}>
          <Typography variant="caption">Alert ID:</Typography>
          <Chip label={decision.data?.alert_id} size="small" variant="outlined" sx={{ height: 20, fontSize: '0.7rem' }} />
        </Box>
      </Box>

      {/* Reasoning */}
      {decision.data?.reasoning && (
        <Box>
          <Typography variant="caption" fontWeight="bold" display="block" sx={{ mb: 0.5 }}>
            AI Analysis
          </Typography>
          <Paper variant="outlined" sx={{ p: 0.75, bgcolor: 'grey.50', maxHeight: 80, overflow: 'auto' }}>
            <Typography variant="caption" sx={{ whiteSpace: 'pre-wrap', fontSize: '0.7rem' }}>
              {decision.data.reasoning}
            </Typography>
          </Paper>
        </Box>
      )}

      {/* Recommended Action */}
      <Box>
        <Typography variant="caption" fontWeight="bold" display="block" sx={{ mb: 0.5 }}>
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
          size="small"
          sx={{ height: 20, fontSize: '0.7rem' }}
        />
      </Box>

      <Divider sx={{ my: 0.5 }} />

      {/* Decision Form */}
      <FormControl fullWidth size="small" sx={{ minHeight: 40 }}>
        <InputLabel sx={{ fontSize: '0.875rem' }}>Your Decision</InputLabel>
        <Select
          value={selectedAction}
          label="Your Decision"
          onChange={(e) => setSelectedAction(e.target.value)}
          sx={{ fontSize: '0.875rem' }}
        >
          {ACTION_OPTIONS.map((option) => (
            <MenuItem key={option.value} value={option.value} sx={{ fontSize: '0.875rem' }}>
              {option.label}
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      <TextField
        label="Analyst Notes"
        multiline
        rows={2}
        fullWidth
        size="small"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Add notes..."
        sx={{ '& .MuiInputBase-input': { fontSize: '0.875rem' } }}
      />

      <Button
        variant="contained"
        color="primary"
        size="small"
        fullWidth
        startIcon={<SendIcon fontSize="small" />}
        onClick={handleSubmit}
        sx={{ mt: 0.5, py: 0.75 }}
      >
        Submit Decision
      </Button>
    </Paper>
  );
}

export default AnalystDecisionPanel;
