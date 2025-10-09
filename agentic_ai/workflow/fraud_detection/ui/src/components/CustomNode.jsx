import React from 'react';
import { Handle, Position } from 'reactflow';
import { Box, Typography, Paper, Chip } from '@mui/material';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import HourglassEmptyIcon from '@mui/icons-material/HourglassEmpty';
import CircleIcon from '@mui/icons-material/Circle';

const getStatusColor = (status) => {
  switch (status) {
    case 'running':
      return { bg: '#1976d2', text: '#ffffff' };
    case 'completed':
      return { bg: '#4caf50', text: '#ffffff' };
    case 'error':
      return { bg: '#f44336', text: '#ffffff' };
    default:
      return { bg: '#ffffff', text: '#000000' };
  }
};

const getStatusIcon = (status) => {
  switch (status) {
    case 'running':
      return <HourglassEmptyIcon sx={{ fontSize: 16 }} />;
    case 'completed':
      return <CheckCircleIcon sx={{ fontSize: 16 }} />;
    default:
      return <CircleIcon sx={{ fontSize: 16, color: '#9e9e9e' }} />;
  }
};

const getStatusLabel = (status) => {
  switch (status) {
    case 'running':
      return 'Running';
    case 'completed':
      return 'Completed';
    case 'error':
      return 'Error';
    default:
      return 'Idle';
  }
};

function CustomNode({ data }) {
  const statusColor = getStatusColor(data.status);
  const isActive = data.status === 'running';

  return (
    <Paper
      elevation={isActive ? 8 : 3}
      sx={{
        padding: 2,
        minWidth: 180,
        borderRadius: 2,
        border: isActive ? `3px solid ${statusColor.bg}` : '1px solid #e0e0e0',
        backgroundColor: statusColor.bg === '#ffffff' ? '#ffffff' : `${statusColor.bg}15`,
        transition: 'all 0.3s ease',
        '&:hover': {
          elevation: 6,
          transform: 'scale(1.02)',
        },
      }}
    >
      <Handle type="target" position={Position.Top} />

      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Typography variant="subtitle1" fontWeight="bold" sx={{ fontSize: 14 }}>
            {data.label}
          </Typography>
          <Chip
            icon={getStatusIcon(data.status)}
            label={getStatusLabel(data.status)}
            size="small"
            sx={{
              backgroundColor: statusColor.bg,
              color: statusColor.text,
              fontSize: 11,
              height: 24,
            }}
          />
        </Box>

        {data.description && (
          <Typography variant="caption" color="text.secondary" sx={{ fontSize: 11 }}>
            {data.description}
          </Typography>
        )}
      </Box>

      <Handle type="source" position={Position.Bottom} />
    </Paper>
  );
}

export default CustomNode;
