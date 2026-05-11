import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, AlertTriangle, Compass, Gamepad2, Gauge, Power, RotateCcw, Send, Square, Wifi, WifiOff } from 'lucide-react';
import './styles.css';

const LIMITS = {
  maxLinear: 1.0,
  maxLateral: 0.65,
  maxAngular: 2.5,
  deadzone: 0.07,
  commandMs: 33,
  heartbeatMs: 250,
};

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function axis(value, deadzone = LIMITS.deadzone) {
  const mag = Math.abs(value);
  if (mag <= deadzone) return 0;
  return Math.sign(value) * Math.min(1, (mag - deadzone) / (1 - deadzone));
}

function emptyTwist() {
  return { linear: { x: 0, y: 0, z: 0 }, angular: { x: 0, y: 0, z: 0 } };
}

function useRosbridge(initialUrl) {
  const [url, setUrl] = useState(initialUrl);
  const [state, setState] = useState('offline');
  const [lastError, setLastError] = useState('');
  const socketRef = useRef(null);
  const listenersRef = useRef(new Map());

  const publish = useCallback((topic, msg) => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify({ op: 'publish', topic, msg }));
    return true;
  }, []);

  const subscribe = useCallback((topic, type, handler) => {
    listenersRef.current.set(topic, handler);
    const socket = socketRef.current;
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ op: 'subscribe', topic, type, queue_length: 1 }));
    }
  }, []);

  const connect = useCallback(() => {
    if (socketRef.current) socketRef.current.close();
    setState('connecting');
    setLastError('');
    const socket = new WebSocket(url);
    socketRef.current = socket;
    socket.onopen = () => {
      setState('online');
      for (const [topic] of listenersRef.current) {
        const type = topic === '/odom' ? 'nav_msgs/Odometry'
          : topic === '/imu' ? 'sensor_msgs/Imu'
          : topic === '/current_data' ? 'std_msgs/Float32MultiArray'
          : 'std_msgs/String';
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

function Metric({ label, value }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}

function App() {
  const defaultUrl = `ws://${window.location.hostname || '127.0.0.1'}:9090`;
  const ros = useRosbridge(defaultUrl);
  const [stick, setStick] = useState({ x: 0, y: 0 });
  const [lateral, setLateral] = useState(0);
  const [mult, setMult] = useState(1);
  const [targetAngle, setTargetAngle] = useState(0);
  const [angleState, setAngleState] = useState('idle');
  const [status, setStatus] = useState('idle');
  const [telemetry, setTelemetry] = useState({ voltage: '--', vx: '0.00', vy: '0.00', wz: '0.00', imuZ: '--', odomX: '--', odomY: '--', c0: '--', c1: '--', c2: '--' });
  const [log, setLog] = useState([]);
  const keyRef = useRef({});
  const padRef = useRef(null);

  const addLog = useCallback((text) => {
    setLog((items) => [`${new Date().toLocaleTimeString()}  ${text}`, ...items].slice(0, 9));
  }, []);

  const command = useMemo(() => {
    const drive = axis(-stick.y);
    const turn = axis(stick.x);
    const lat = axis(lateral);
    return {
      drive,
      turn,
      lat,
      twist: {
        linear: { x: drive * LIMITS.maxLinear * mult, y: lat * LIMITS.maxLateral * mult, z: 0 },
        angular: { x: 0, y: 0, z: -turn * LIMITS.maxAngular * mult }
      }
    };
  }, [stick, lateral, mult]);

  useEffect(() => {
    ros.subscribe('/PowerVoltage', 'std_msgs/Float32', (msg) => setTelemetry((t) => ({ ...t, voltage: `${Number(msg.data || 0).toFixed(2)} V` })));
    ros.subscribe('/current_data', 'std_msgs/Float32MultiArray', (msg) => {
      const d = msg.data || [];
      setTelemetry((t) => ({ ...t, c0: `${Number(d[0] || 0).toFixed(3)} A`, c1: `${Number(d[1] || 0).toFixed(3)} A`, c2: `${Number(d[2] || 0).toFixed(3)} A` }));
    });
    ros.subscribe('/imu', 'sensor_msgs/Imu', (msg) => setTelemetry((t) => ({ ...t, imuZ: Number(msg.angular_velocity?.z || 0).toFixed(3) })));
    ros.subscribe('/odom', 'nav_msgs/Odometry', (msg) => {
      const tw = msg.twist?.twist || {};
      const po = msg.pose?.pose || {};
      setTelemetry((t) => ({ ...t, vx: Number(tw.linear?.x || 0).toFixed(2), vy: Number(tw.linear?.y || 0).toFixed(2), wz: Number(tw.angular?.z || 0).toFixed(2), odomX: Number(po.position?.x || 0).toFixed(2), odomY: Number(po.position?.y || 0).toFixed(2) }));
    });
    ros.subscribe('/web/control_status', 'std_msgs/String', (msg) => setStatus(msg.data || 'idle'));
  }, [ros.subscribe]);

  useEffect(() => {
    const heartbeat = setInterval(() => ros.publish('/web/heartbeat', {}), LIMITS.heartbeatMs);
    const sender = setInterval(() => ros.publish('/cmd_vel_web', command.twist), LIMITS.commandMs);
    return () => { clearInterval(heartbeat); clearInterval(sender); };
  }, [ros.publish, command]);

  useEffect(() => {
    function syncKeys() {
      const k = keyRef.current;
      const fwd = k.w || k.arrowup;
      const bwd = k.s || k.arrowdown;
      const left = k.a || k.arrowleft;
      const right = k.d || k.arrowright;
      const q = k.q;
      const e = k.e;
      setStick({ x: (right ? 1 : 0) - (left ? 1 : 0), y: (bwd ? 1 : 0) - (fwd ? 1 : 0) });
      setLateral((e ? 1 : 0) - (q ? 1 : 0));
      setMult(k.shift ? 1.5 : 1);
    }
    const down = (e) => {
      const key = e.key === ' ' ? 'space' : e.key.toLowerCase();
      if (['w','a','s','d','q','e','arrowup','arrowdown','arrowleft','arrowright','shift'].includes(key)) {
        e.preventDefault(); keyRef.current[key] = true; syncKeys();
      }
      if (key === 'space') stop();
    };
    const up = (e) => { keyRef.current[e.key.toLowerCase()] = false; syncKeys(); };
    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    return () => { window.removeEventListener('keydown', down); window.removeEventListener('keyup', up); };
  }, []);

  function stop() {
    setStick({ x: 0, y: 0 });
    setLateral(0);
    ros.publish('/web/test_enable', { data: false });
    ros.publish('/web/cruise_enable', { data: false });
    ros.publish('/cmd_vel_web', emptyTwist());
    addLog('stop');
  }

  function estop(active) {
    if (active) stop();
    ros.publish('/web/estop', { data: active });
    addLog(active ? 'E-STOP locked' : 'E-STOP released');
  }

  function sendAngle() {
    const angle = Number(targetAngle);
    if (!Number.isFinite(angle)) return;
    ros.publish('/target_angle', { data: angle });
    setAngleState(`${angle.toFixed(1)} deg`);
    addLog(`target angle ${angle.toFixed(1)} deg`);
  }

  function zeroAngle() {
    ros.publish('/target_angle_reset', {});
    setTargetAngle(0);
    setAngleState('zeroed');
    addLog('set current heading as 0 deg');
  }

  function pointerMove(e) {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = clamp((e.clientX - rect.left - rect.width / 2) / (rect.width * 0.38), -1, 1);
    const y = clamp((e.clientY - rect.top - rect.height / 2) / (rect.height * 0.38), -1, 1);
    setStick({ x, y });
  }

  return <main className="app">
    <header className="topbar">
      <div><h1>WHEELTEC ROS Console</h1><p>Speed and heading-angle control are separated. Left/right keys remain manual steering.</p></div>
      <div className={`net ${ros.state}`}>{ros.state === 'online' ? <Wifi size={18}/> : <WifiOff size={18}/>} {ros.state}</div>
    </header>

    <section className="connection panel">
      <input value={ros.url} onChange={(e) => ros.setUrl(e.target.value)} />
      <button onClick={ros.connect}><Power size={17}/>Rate</button>
      <button className="ghost" onClick={ros.disconnect}>Rate</button>
      <button className="danger" onClick={() => estop(true)}><AlertTriangle size={17}/>Rate</button>
      <button className="ghost" onClick={() => estop(false)}>Events</button>
    </section>

    <section className="grid metrics">
      <Metric label="Events" value={status}/><Metric label="Events" value={telemetry.voltage}/><Metric label="Rate X" value={telemetry.vx}/><Metric label="Rate Wz" value={telemetry.wz}/>
    </section>

    <section className="layout">
      <div className="panel drivePanel">
        <div className="panelTitle"><Gamepad2 size={19}/> Events</div>
        <div className="stick" onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); pointerMove(e); }} onPointerMove={(e) => e.buttons && pointerMove(e)} onPointerUp={() => setStick({ x: 0, y: 0 })}>
          <div className="knob" style={{ transform: `translate(${stick.x * 86}px, ${stick.y * 86}px)` }} />
        </div>
        <div className="cmdGrid">
          <Metric label="Linear X" value={command.twist.linear.x.toFixed(2)}/><Metric label="Linear Y" value={command.twist.linear.y.toFixed(2)}/><Metric label="Angular Z" value={command.twist.angular.z.toFixed(2)}/><Metric label="Rate" value={`${mult.toFixed(1)}x`}/>
        </div>
        <div className="actions"><button onClick={stop}><Square size={17}/>Rate</button><button onClick={() => setLateral(-1)}>Rate?</button><button onClick={() => setLateral(1)}>Rate?</button></div>
      </div>

      <div className="panel anglePanel">
        <div className="panelTitle"><Compass size={19}/> Events?</div>
        <div className="angleInput"><input type="number" step="1" value={targetAngle} onChange={(e) => setTargetAngle(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && sendAngle()} /><span>deg</span></div>
        <div className="actions"><button onClick={sendAngle}><Send size={17}/>Events?</button><button className="ghost" onClick={zeroAngle}><RotateCcw size={17}/>Events? 0 ?</button></div>
        <Metric label="Events" value={angleState}/>
        <div className="note">EventsRate /target_angleRate? A/D EventsEvents? angular.z?</div>
      </div>
    </section>

    <section className="grid telemetry">
      <Metric label="IMU Wz" value={telemetry.imuZ}/><Metric label="Rate X" value={telemetry.odomX}/><Metric label="Rate Y" value={telemetry.odomY}/><Metric label="Rate 0" value={telemetry.c0}/><Metric label="Rate 1" value={telemetry.c1}/><Metric label="Rate 2" value={telemetry.c2}/>
    </section>

    <section className="panel log"><div className="panelTitle"><Activity size={18}/>Rate</div>{log.map((line) => <div key={line}>{line}</div>)}</section>
  </main>;
}

createRoot(document.getElementById('root')).render(<App />);
