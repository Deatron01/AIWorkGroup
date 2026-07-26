import ReactFlow, { Background, Controls } from 'reactflow';
import 'reactflow/dist/style.css';
import { useFoundrySocket } from './useFoundrySocket';

// Custom node styling based on status
const nodeColor = (node) => {
  switch (node.data.status) {
    case 'completed': return '#4caf50'; // Green
    case 'ready': return '#2196f3';     // Blue (In Progress)
    case 'failed': return '#f44336';    // Red
    default: return '#9e9e9e';          // Grey (Pending)
  }
};

export default function FoundryDashboard() {
  const { nodes, edges, logs } = useFoundrySocket('ws://127.0.0.1:8000/ws/ui');

  return (
    <div style={{ display: 'flex', height: '100vh', width: '100vw' }}>
      {/* Left Pane: The Task DAG */}
      <div style={{ flex: 1, borderRight: '1px solid #333' }}>
        <ReactFlow nodes={nodes.map(n => ({...n, style: { background: nodeColor(n) }}))} edges={edges}>
          <Background />
          <Controls />
        </ReactFlow>
      </div>

      {/* Right Pane: Live Agent Terminals */}
      <div style={{ width: '400px', backgroundColor: '#1e1e1e', color: '#00ff00', padding: '10px', overflowY: 'auto' }}>
        <h3>Live Agent Swimlanes</h3>
        {Object.entries(logs).map(([taskId, logText]) => (
          <div key={taskId} style={{ marginBottom: '20px' }}>
            <h4 style={{ color: '#fff' }}>Task: {taskId}</h4>
            <pre style={{ whiteSpace: 'pre-wrap', fontSize: '12px' }}>{logText}</pre>
          </div>
        ))}
      </div>
    </div>
  );
}