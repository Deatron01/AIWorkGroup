import { ReactFlow, Background, Controls, Panel } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
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

  const handleStartTask = () => {
    console.log("Task started! Sending signal to backend...");
    
    // Sends an HTTP POST request to your FastAPI backend to kick off the work pipeline
    fetch('http://127.0.0.1:8000/start-task', { 
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task: "run_ai_job" })
    })
    .then(response => response.json())
    .then(data => console.log("Backend response:", data))
    .catch(error => console.error("Error starting task:", error));
  };

  return (
    <div style={{ display: 'flex', height: '100vh', width: '100vw' }}>
      {/* Left Pane: The Task DAG with Start Button Panel */}
      <div style={{ flex: 1, borderRight: '1px solid #333', position: 'relative' }}>
        <ReactFlow 
          nodes={nodes.map(n => ({ ...n, style: { background: nodeColor(n), color: '#fff', padding: 10, borderRadius: 5 } }))} 
          edges={edges}
        >
          <Background />
          <Controls />
          
          {/* Floating Control Panel */}
          <Panel position="top-left">
            <button 
              onClick={handleStartTask}
              style={{ 
                padding: '10px 20px', 
                cursor: 'pointer', 
                background: '#007bff', 
                color: 'white', 
                border: 'none', 
                borderRadius: '5px',
                fontWeight: 'bold',
                boxShadow: '0 2px 4px rgba(0,0,0,0.2)'
              }}
            >
              ▶ Start Task
            </button>
          </Panel>
        </ReactFlow>
      </div>

      {/* Right Pane: Live Agent Terminals */}
      <div style={{ width: '400px', backgroundColor: '#1e1e1e', color: '#00ff00', padding: '15px', overflowY: 'auto' }}>
        <h3>Live Agent Swimlanes</h3>
        {Object.keys(logs).length === 0 ? (
          <p style={{ color: '#666', fontSize: '13px' }}>Awaiting task logs...</p>
        ) : (
          Object.entries(logs).map(([taskId, logText]) => (
            <div key={taskId} style={{ marginBottom: '20px' }}>
              <h4 style={{ color: '#fff', margin: '0 0 5px 0' }}>Task: {taskId}</h4>
              <pre style={{ whiteSpace: 'pre-wrap', fontSize: '12px', margin: 0, background: '#111', padding: '8px', borderRadius: '4px' }}>
                {logText}
              </pre>
            </div>
          ))
        )}
      </div>
    </div>
  );
}