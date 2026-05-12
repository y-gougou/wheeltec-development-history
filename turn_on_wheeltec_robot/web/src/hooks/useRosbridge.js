import { useCallback, useRef, useState } from 'react';

export function useRosbridge(initialUrl) {
  const [url, setUrl] = useState(initialUrl);
  const [state, setState] = useState('offline');
  const [lastError, setLastError] = useState('');
  const socketRef = useRef(null);
  const listenersRef = useRef(new Map());
  const typeRef = useRef(new Map());

  const publish = useCallback((topic, msg) => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify({ op: 'publish', topic, msg }));
    return true;
  }, []);

  const subscribe = useCallback((topic, type, handler) => {
    const prevType = typeRef.current.get(topic);
    const prevHandler = listenersRef.current.get(topic);
    listenersRef.current.set(topic, handler);
    typeRef.current.set(topic, type);
    const socket = socketRef.current;
    if (socket && socket.readyState === WebSocket.OPEN) {
      if (prevHandler && prevType) {
        socket.send(JSON.stringify({ op: 'unsubscribe', topic, type: prevType }));
      }
      socket.send(JSON.stringify({ op: 'subscribe', topic, type, queue_length: 1 }));
    }
    return () => {
      const currentHandler = listenersRef.current.get(topic);
      if (currentHandler === handler) {
        listenersRef.current.delete(topic);
        typeRef.current.delete(topic);
        const liveSocket = socketRef.current;
        if (liveSocket && liveSocket.readyState === WebSocket.OPEN) {
          liveSocket.send(JSON.stringify({ op: 'unsubscribe', topic, type }));
        }
      }
    };
  }, []);

  const connect = useCallback(() => {
    if (socketRef.current) socketRef.current.close();
    setState('connecting');
    setLastError('');
    const socket = new WebSocket(url);
    socketRef.current = socket;
    socket.onopen = () => {
      setState('online');
      for (const [topic, type] of typeRef.current) {
        socket.send(JSON.stringify({ op: 'subscribe', topic, type, queue_length: 1 }));
      }
    };
    socket.onclose = () => setState('offline');
    socket.onerror = () => {
      setLastError('rosbridge websocket error');
      setState('error');
    };
    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      if (payload.op !== 'publish') return;
      const handler = listenersRef.current.get(payload.topic);
      if (handler) handler(payload.msg);
    };
  }, [url]);

  const disconnect = useCallback(() => {
    if (socketRef.current) socketRef.current.close();
    socketRef.current = null;
    setState('offline');
  }, []);

  return { url, setUrl, state, lastError, publish, subscribe, connect, disconnect };
}
