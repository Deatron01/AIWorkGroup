import { useEffect, useState, useRef } from 'react';

export function useFoundrySocket(url) {
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [logs, setLogs] = useState({});
  const ws = useRef(null);

  useEffect(() => {
    ws.current = new WebSocket(url);

    ws.current.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      switch (data.type) {
        case 'DAG_INIT':
          const newNodes = data.payload.tasks.map((t, index) => ({
            id: t.task_id,
            data: { label: `${t.task_id} (${t.role})`, status: 'pending' },
            position: { x: index * 200, y: index * 100 }
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
          setNodes(nds => nds.map(node => {
            if (node.id === data.payload.task_id) {
              return { ...node, data: { ...node.data, status: data.payload.status } };
            }
            return node;
          }));
          break;

        case 'AGENT_LOG':
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