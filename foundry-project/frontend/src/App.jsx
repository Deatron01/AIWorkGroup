import { useEffect, useState, useRef } from 'react';
export default App;
export function useFoundrySocket(url) {
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [logs, setLogs] = useState({}); // Keyed by task_id
  const ws = useRef(null);

  useEffect(() => {
    ws.current = new WebSocket(url);

    ws.current.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      switch (data.type) {
        case 'DAG_INIT':
          // Transform Boss JSON graph into React Flow nodes and edges
          const newNodes = data.payload.tasks.map((t, index) => ({
            id: t.task_id,
            data: { label: `${t.task_id} (${t.role})`, status: 'pending' },
            position: { x: index * 200, y: index * 100 } // Auto-layout logic goes here
          }));
          
          const newEdges = data.payload.tasks.flatMap(t => 
            t.dependencies.map(dep => ({
              id: `e-${dep}-${t.task_id}`,
              source: dep,
              target: t.task_id
            }))
          );
          setNodes(newNodes);
          setEdges(newEdges);
          break;

        case 'TASK_STATUS_CHANGE':
          // Update node color based on status (ready, completed, failed)
          setNodes(nds => nds.map(node => {
            if (node.id === data.payload.task_id) {
              return { ...node, data: { ...node.data, status: data.payload.status } };
            }
            return node;
          }));
          break;

        case 'AGENT_LOG':
          // Append streaming log to the specific task's terminal
          setLogs(prev => ({
            ...prev,
            [data.payload.task_id]: (prev[data.payload.task_id] || '') + data.payload.log + '\n'
          }));
          break;
      }
    };

    return () => ws.current.close();
  }, [url]);

  return { nodes, edges, logs };
}