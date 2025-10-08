import React, { useMemo } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { Box } from '@mui/material';
import CustomNode from './CustomNode';

const nodeTypes = {
  custom: CustomNode,
};

// Define the workflow graph structure
const initialNodes = [
  {
    id: 'alert_router',
    type: 'custom',
    position: { x: 400, y: 50 },
    data: { label: 'Alert Router', status: 'idle', description: 'Routes alerts to analysts' },
  },
  {
    id: 'usage_pattern_executor',
    type: 'custom',
    position: { x: 150, y: 200 },
    data: { label: 'Usage Analyst', status: 'idle', description: 'Analyzes usage patterns' },
  },
  {
    id: 'location_analysis_executor',
    type: 'custom',
    position: { x: 400, y: 200 },
    data: { label: 'Location Analyst', status: 'idle', description: 'Analyzes location anomalies' },
  },
  {
    id: 'billing_charge_executor',
    type: 'custom',
    position: { x: 650, y: 200 },
    data: { label: 'Billing Analyst', status: 'idle', description: 'Analyzes billing patterns' },
  },
  {
    id: 'fraud_risk_aggregator',
    type: 'custom',
    position: { x: 400, y: 350 },
    data: { label: 'Risk Aggregator', status: 'idle', description: 'Aggregates risk assessment' },
  },
  {
    id: 'review_gateway',
    type: 'custom',
    position: { x: 550, y: 500 },
    data: { label: 'Review Gateway', status: 'idle', description: 'Routes to analyst review' },
  },
  {
    id: 'auto_clear_executor',
    type: 'custom',
    position: { x: 250, y: 500 },
    data: { label: 'Auto Clear', status: 'idle', description: 'Auto-clears low risk' },
  },
  {
    id: 'analyst_review',
    type: 'custom',
    position: { x: 550, y: 650 },
    data: { label: 'Analyst Review', status: 'idle', description: 'Human review required' },
  },
  {
    id: 'fraud_action_executor',
    type: 'custom',
    position: { x: 550, y: 800 },
    data: { label: 'Fraud Action', status: 'idle', description: 'Execute fraud action' },
  },
  {
    id: 'final_notification_executor',
    type: 'custom',
    position: { x: 400, y: 950 },
    data: { label: 'Final Notification', status: 'idle', description: 'Send notifications' },
  },
];

const initialEdges = [
  // Fan-out from alert router to analysts
  { id: 'e1-1', source: 'alert_router', target: 'usage_pattern_executor', animated: true },
  { id: 'e1-2', source: 'alert_router', target: 'location_analysis_executor', animated: true },
  { id: 'e1-3', source: 'alert_router', target: 'billing_charge_executor', animated: true },
  
  // Fan-in to aggregator
  { id: 'e2-1', source: 'usage_pattern_executor', target: 'fraud_risk_aggregator' },
  { id: 'e2-2', source: 'location_analysis_executor', target: 'fraud_risk_aggregator' },
  { id: 'e2-3', source: 'billing_charge_executor', target: 'fraud_risk_aggregator' },
  
  // Switch case from aggregator
  { id: 'e3-1', source: 'fraud_risk_aggregator', target: 'review_gateway', label: 'High Risk', style: { stroke: '#f44336' } },
  { id: 'e3-2', source: 'fraud_risk_aggregator', target: 'auto_clear_executor', label: 'Low Risk', style: { stroke: '#4caf50' } },
  
  // Review loop
  { id: 'e4-1', source: 'review_gateway', target: 'analyst_review' },
  { id: 'e4-2', source: 'analyst_review', target: 'review_gateway', animated: true, style: { stroke: '#ff9800' } },
  { id: 'e4-3', source: 'review_gateway', target: 'fraud_action_executor' },
  
  // Final paths
  { id: 'e5-1', source: 'auto_clear_executor', target: 'final_notification_executor' },
  { id: 'e5-2', source: 'fraud_action_executor', target: 'final_notification_executor' },
];

function WorkflowVisualizer({ executorStates = {} }) {
  // Update nodes with current executor states
  const nodes = useMemo(() => {
    return initialNodes.map((node) => ({
      ...node,
      data: {
        ...node.data,
        status: executorStates[node.id] || 'idle',
      },
    }));
  }, [executorStates]);

  const [nodesState, setNodes, onNodesChange] = useNodesState(nodes);
  const [edgesState, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Update nodes when executor states change
  React.useEffect(() => {
    setNodes(nodes);
  }, [nodes, setNodes]);

  return (
    <Box sx={{ width: '100%', height: '100%' }}>
      <ReactFlow
        nodes={nodesState}
        edges={edgesState}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        fitView
        attributionPosition="bottom-left"
      >
        <Background />
        <Controls />
        <MiniMap
          nodeColor={(node) => {
            const status = node.data.status;
            if (status === 'running') return '#1976d2';
            if (status === 'completed') return '#4caf50';
            return '#9e9e9e';
          }}
        />
      </ReactFlow>
    </Box>
  );
}

export default WorkflowVisualizer;
