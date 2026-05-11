import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity,
  AlertTriangle,
  ArrowDown,
  ArrowDownLeft,
  ArrowDownRight,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  ArrowUpLeft,
  ArrowUpRight,
  Compass,
  Database,
  Download,
  Gauge,
  Gamepad2,
  Pause,
  Power,
  Radio,
  RefreshCw,
  RotateCcw,
  Send,
  Square,
  Wifi,
  WifiOff,
} from 'lucide-react';
import './styles.css';

const LIMITS = {
  maxLinear: 1.0,
  maxLateral: 0.65,
  maxAngular: 2.5,
  deadzone: 0.07,
  commandMs: 33,
  heartbeatMs: 250,
};

const DIRECTIONS = [
  { label: 'Forward-left', icon: ArrowUpLeft, x: 1, y: 1 },
  { label: 'Forward', icon: ArrowUp, x: 1, y: 0 },
  { label: 'Forward-right', icon: ArrowUpRight, x: 1, y: -1 },
  { label: 'Left', icon: ArrowLeft, x: 0, y: 1 },
  { label: 'Stop vector', icon: Square, x: 0, y: 0 },
  { label: 'Right', icon: ArrowRight, x: 0, y: -1 },
  { label: 'Back-left', icon: ArrowDownLeft, x: -1, y: 1 },
  { label: 'Back', icon: ArrowDown, x: -1, y: 0 },
  { label: 'Back-right', icon: ArrowDownRight, x: -1, y: -1 },
];

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function normalizeVector(vector) {
  const length = Math.hypot(vector.x, vector.y);
  if (length <= 0.001) return { x: 0, y: 0 };
  return { x: vector.x / length, y: vector.y / length };
}

function axis(value, deadzone = LIMITS.deadzone) {
  const mag = Math.abs(value);
  if (mag <= deadzone) return 0;
  return Math.sign(value) * Math.min(1, (mag - deadzone) / (1 - deadzone));
}

function emptyTwist() {
  return { linear: { x: 0, y: 0, z: 0 }, angular: { x: 0, y: 0, z: 0 } };
}

function twist(vx = 0, vy = 0, wz = 0) {
  return { linear: { x: vx, y: vy, z: 0 }, angular: { x: 0, y: 0, z: wz } };
}

function parseCruiseStatus(text) {
  if (!text || text === 'cruise: off') {
    return { active: false, target: { vx: 0, vy: 0, wz: 0 }, actual: { vx: 0, vy: 0, wz: 0 }, raw: text || 'cruise: off' };
  }
  const match = text.match(/vx=([-0-9.]+)\(([-0-9.]+)\)\s+vy=([-0-9.]+)\(([-0-9.]+)\)\s+wz=([-0-9.]+)\(([-0-9.]+)\)/);
  if (!match) {
    return { active: text.startsWith('cruise:'), target: { vx: 0, vy: 0, wz: 0 }, actual: { vx: 0, vy: 0, wz: 0 }, raw: text };
  }
  return {
    active: true,
    target: { vx: Number(match[1]), vy: Number(match[3]), wz: Number(match[5]) },
    actual: { vx: Number(match[2]), vy: Number(match[4]), wz: Number(match[6]) },
    raw: text,
  };
}

function parseJsonStatus(text, fallback = {}) {
  try {
    return { ...fallback, ...(JSON.parse(text || '{}')) };
  } catch {
    return fallback;
  }
}

function apiUrl(path, params = {}) {
  const url = new URL(path, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, value);
    }
  });
  return url.toString();
}

function useRosbridge(initialUrl) {
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
    listenersRef.current.set(topic, handler);
    typeRef.current.set(topic, type);
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

function Metric({ label, value, tone = '' }) {
  return <div className={`metric ${tone}`}><span>{label}</span><strong>{value}</strong></div>;
}

function SectionTitle({ icon: Icon, title, detail }) {
  return <div className="sectionTitle"><div><Icon size={19}/><strong>{title}</strong></div>{detail && <span>{detail}</span>}</div>;
}

function DirectionPad({ value, onChange }) {
  return <div className="dirPad">
    {DIRECTIONS.map((item) => {
      const Icon = item.icon;
      const active = value.x === item.x && value.y === item.y;
      return <button
        key={item.label}
        className={active ? 'active' : 'ghost'}
        title={item.label}
        onClick={() => onChange({ x: item.x, y: item.y })}
      >
        <Icon size={18}/>
      </button>;
    })}
  </div>;
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
  const [cruise, setCruise] = useState({ speed: 0.2, direction: { x: 1, y: 0 }, status: parseCruiseStatus('cruise: off') });
  const [collection, setCollection] = useState({
    current_port: '/dev/ttyUSB1',
    output_dir: '/home/wheeltec/R550PLUS_data_collect/log_v2',
    fault_label: 0,
    fault_name: 'normal',
    fault_mode: 0,
    run_id: '',
    motion_mode: 'straight_back_forth_0.25ms',
    expected_rate: 20,
    status: { state: 'idle', collecting: false, sample_id: 0 },
    current: { connected: false, port: '/dev/ttyUSB1', valid_total: 0 },
    files: [],
    filesDir: '',
    fileError: '',
    showAdvanced: false,
  });
  const [telemetry, setTelemetry] = useState({
    voltage: '--',
    vx: '0.00',
    vy: '0.00',
    wz: '0.00',
    imuZ: '--',
    odomX: '--',
    odomY: '--',
    c0: '--',
    c1: '--',
    c2: '--',
  });
  const [log, setLog] = useState([]);
  const keyRef = useRef({});

  const addLog = useCallback((text) => {
    setLog((items) => [`${new Date().toLocaleTimeString()}  ${text}`, ...items].slice(0, 12));
  }, []);

  const command = useMemo(() => {
    const drive = axis(-stick.y);
    const turn = axis(stick.x);
    const lat = axis(lateral);
    return {
      drive,
      turn,
      lat,
      twist: twist(drive * LIMITS.maxLinear * mult, lat * LIMITS.maxLateral * mult, -turn * LIMITS.maxAngular * mult),
    };
  }, [stick, lateral, mult]);

  const cruiseVector = useMemo(() => normalizeVector(cruise.direction), [cruise.direction]);
  const cruiseCmd = useMemo(() => {
    const speed = clamp(Number(cruise.speed) || 0, 0, LIMITS.maxLinear);
    return twist(cruiseVector.x * speed, cruiseVector.y * speed, 0);
  }, [cruise.speed, cruiseVector]);

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
      setTelemetry((t) => ({
        ...t,
        vx: Number(tw.linear?.x || 0).toFixed(2),
        vy: Number(tw.linear?.y || 0).toFixed(2),
        wz: Number(tw.angular?.z || 0).toFixed(2),
        odomX: Number(po.position?.x || 0).toFixed(2),
        odomY: Number(po.position?.y || 0).toFixed(2),
      }));
    });
    ros.subscribe('/web/control_status', 'std_msgs/String', (msg) => setStatus(msg.data || 'idle'));
    ros.subscribe('/web/cruise_status', 'std_msgs/String', (msg) => setCruise((c) => ({ ...c, status: parseCruiseStatus(msg.data || '') })));
    ros.subscribe('/web/collection_status', 'std_msgs/String', (msg) => {
      const parsed = parseJsonStatus(msg.data, { state: 'idle', collecting: false, sample_id: 0 });
      setCollection((c) => ({ ...c, status: parsed }));
    });
    ros.subscribe('/web/current_reader_status', 'std_msgs/String', (msg) => {
      const parsed = parseJsonStatus(msg.data, { connected: false });
      setCollection((c) => ({ ...c, current: parsed, current_port: parsed.port || c.current_port }));
    });
  }, [ros.subscribe]);

  useEffect(() => {
    const heartbeat = setInterval(() => ros.publish('/web/heartbeat', {}), LIMITS.heartbeatMs);
    const sender = setInterval(() => {
      if (!cruise.status.active) ros.publish('/cmd_vel_web', command.twist);
    }, LIMITS.commandMs);
    return () => {
      clearInterval(heartbeat);
      clearInterval(sender);
    };
  }, [ros.publish, command, cruise.status.active]);

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
      if (['w', 'a', 's', 'd', 'q', 'e', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright', 'shift'].includes(key)) {
        e.preventDefault();
        keyRef.current[key] = true;
        syncKeys();
      }
      if (key === 'space') stop();
    };
    const up = (e) => {
      const key = e.key === ' ' ? 'space' : e.key.toLowerCase();
      keyRef.current[key] = false;
      syncKeys();
    };
    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    return () => {
      window.removeEventListener('keydown', down);
      window.removeEventListener('keyup', up);
    };
  }, []);

  function stop() {
    setStick({ x: 0, y: 0 });
    setLateral(0);
    ros.publish('/web/test_enable', { data: false });
    ros.publish('/web/cruise_enable', { data: false });
    ros.publish('/cmd_vel_web', emptyTwist());
    addLog('Stop command sent');
  }

  function estop(active) {
    if (active) stop();
    ros.publish('/web/estop', { data: active });
    addLog(active ? 'E-stop locked' : 'E-stop released');
  }

  function startCruise() {
    ros.publish('/web/cruise_cmd', cruiseCmd);
    ros.publish('/web/cruise_enable', { data: true });
    addLog(`Cruise start vx=${cruiseCmd.linear.x.toFixed(2)} vy=${cruiseCmd.linear.y.toFixed(2)} wz=0.00`);
  }

  function stopCruise() {
    ros.publish('/web/cruise_enable', { data: false });
    ros.publish('/cmd_vel_web', emptyTwist());
    addLog('Cruise stopped');
  }

  function sendAngle() {
    const angle = Number(targetAngle);
    if (!Number.isFinite(angle)) return;
    ros.publish('/target_angle', { data: angle });
    setAngleState(`${angle.toFixed(1)} deg`);
    addLog(`Target angle ${angle.toFixed(1)} deg`);
  }

  function zeroAngle() {
    ros.publish('/target_angle_reset', {});
    setTargetAngle(0);
    setAngleState('current heading = 0 deg');
    addLog('Current heading set as 0 deg');
  }

  const collectionConfig = useMemo(() => ({
    output_dir: collection.output_dir,
    fault_label: Number(collection.fault_label) || 0,
    fault_name: collection.fault_name || 'normal',
    fault_mode: Number(collection.fault_mode) || 0,
    run_id: collection.run_id || '',
    motion_mode: collection.motion_mode || 'straight_back_forth_0.25ms',
    expected_rate: Number(collection.expected_rate) || 20,
  }), [
    collection.output_dir,
    collection.fault_label,
    collection.fault_name,
    collection.fault_mode,
    collection.run_id,
    collection.motion_mode,
    collection.expected_rate,
  ]);

  function publishCollectionConfig(extra = {}) {
    return ros.publish('/web/collection_config', { data: JSON.stringify({ ...collectionConfig, ...extra }) });
  }

  function reconnectCurrentReader() {
    ros.publish('/web/current_reader_config', { data: JSON.stringify({ port: collection.current_port, reconnect: true }) });
    addLog(`Current reader reconnect ${collection.current_port}`);
  }

  function startCollection() {
    reconnectCurrentReader();
    publishCollectionConfig({ start: true });
    ros.publish('/web/collection_enable', { data: true });
    addLog(`Collection start ${collection.run_id || '(auto run_id)'}`);
    setTimeout(refreshFiles, 800);
  }

  function stopCollection() {
    ros.publish('/web/collection_enable', { data: false });
    addLog('Collection stopped');
    setTimeout(refreshFiles, 500);
  }

  async function refreshFiles() {
    try {
      const response = await fetch(apiUrl('/api/data/list', { dir: collection.output_dir }));
      const body = await response.json();
      setCollection((c) => ({ ...c, files: body.files || [], filesDir: body.dir || c.output_dir, fileError: body.error || '' }));
    } catch (e) {
      setCollection((c) => ({ ...c, fileError: String(e) }));
    }
  }

  function downloadFile(name) {
    window.open(apiUrl(`/api/data/download/${encodeURIComponent(name)}`, { dir: collection.output_dir }), '_blank');
  }

  function pointerMove(e) {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = clamp((e.clientX - rect.left - rect.width / 2) / (rect.width * 0.38), -1, 1);
    const y = clamp((e.clientY - rect.top - rect.height / 2) / (rect.height * 0.38), -1, 1);
    setStick({ x, y });
  }

  const cruiseStatus = cruise.status.active ? 'cruise on' : 'cruise off';

  return <main className="app">
    <header className="topbar">
      <div>
        <h1>WHEELTEC Drive Console</h1>
        <p>Manual speed, cruise speed, and target heading are separate command paths.</p>
      </div>
      <div className={`net ${ros.state}`}>{ros.state === 'online' ? <Wifi size={18}/> : <WifiOff size={18}/>} {ros.state}</div>
    </header>

    <section className="connection panel">
      <input value={ros.url} onChange={(e) => ros.setUrl(e.target.value)} aria-label="rosbridge websocket url" />
      <button onClick={ros.connect}><Power size={17}/>Connect</button>
      <button className="ghost" onClick={ros.disconnect}>Disconnect</button>
      <button className="danger" onClick={() => estop(true)}><AlertTriangle size={17}/>E-stop</button>
      <button className="ghost" onClick={() => estop(false)}>Release</button>
    </section>

    {ros.lastError && <div className="errorLine">{ros.lastError}</div>}

    <section className="grid metrics">
      <Metric label="Control status" value={status}/>
      <Metric label="Cruise status" value={cruiseStatus} tone={cruise.status.active ? 'good' : ''}/>
      <Metric label="Collection" value={collection.status.state || 'idle'} tone={collection.status.collecting ? 'good' : ''}/>
      <Metric label="Battery" value={telemetry.voltage}/>
      <Metric label="IMU Wz" value={telemetry.imuZ}/>
    </section>

    <section className="layout">
      <div className="panel drivePanel">
        <SectionTitle icon={Gamepad2} title="Manual Drive" detail="W/S forward, Q/E strafe, A/D turn" />
        <div
          className="stick"
          onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); pointerMove(e); }}
          onPointerMove={(e) => e.buttons && pointerMove(e)}
          onPointerUp={() => setStick({ x: 0, y: 0 })}
        >
          <div className="knob" style={{ transform: `translate(${stick.x * 86}px, ${stick.y * 86}px)` }} />
        </div>
        <div className="cmdGrid">
          <Metric label="Linear X" value={command.twist.linear.x.toFixed(2)}/>
          <Metric label="Linear Y" value={command.twist.linear.y.toFixed(2)}/>
          <Metric label="Angular Z" value={command.twist.angular.z.toFixed(2)}/>
          <Metric label="Speed scale" value={`${mult.toFixed(1)}x`}/>
        </div>
        <div className="actions">
          <button onClick={stop}><Square size={17}/>Stop</button>
          <button className="ghost" onMouseDown={() => setLateral(-1)} onMouseUp={() => setLateral(0)} onMouseLeave={() => setLateral(0)}><ArrowLeft size={17}/>Strafe left</button>
          <button className="ghost" onMouseDown={() => setLateral(1)} onMouseUp={() => setLateral(0)} onMouseLeave={() => setLateral(0)}><ArrowRight size={17}/>Strafe right</button>
        </div>
      </div>

      <div className="sideStack">
        <div className="panel cruisePanel">
          <SectionTitle icon={Gauge} title="Cruise Control" detail="direction + speed, wz stays 0" />
          <DirectionPad value={cruise.direction} onChange={(direction) => setCruise((c) => ({ ...c, direction }))} />
          <div className="sliderRow">
            <label htmlFor="cruiseSpeed">Cruise speed</label>
            <input id="cruiseSpeed" type="range" min="0" max={LIMITS.maxLinear} step="0.01" value={cruise.speed} onChange={(e) => setCruise((c) => ({ ...c, speed: Number(e.target.value) }))} />
            <strong>{Number(cruise.speed).toFixed(2)} m/s</strong>
          </div>
          <div className="cmdGrid compact">
            <Metric label="Target Vx" value={cruiseCmd.linear.x.toFixed(2)}/>
            <Metric label="Target Vy" value={cruiseCmd.linear.y.toFixed(2)}/>
            <Metric label="Target Wz" value="0.00"/>
          </div>
          <div className="cmdGrid compact">
            <Metric label="Actual Vx" value={cruise.status.actual.vx.toFixed(2)}/>
            <Metric label="Actual Vy" value={cruise.status.actual.vy.toFixed(2)}/>
            <Metric label="Actual Wz" value={cruise.status.actual.wz.toFixed(2)}/>
          </div>
          <div className="actions">
            <button onClick={startCruise}><Radio size={17}/>Start cruise</button>
            <button className="ghost" onClick={stopCruise}><Pause size={17}/>Stop cruise</button>
          </div>
        </div>

        <div className="panel anglePanel">
          <SectionTitle icon={Compass} title="Heading Angle" detail="/target_angle only" />
          <div className="angleInput">
            <input type="number" step="1" value={targetAngle} onChange={(e) => setTargetAngle(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && sendAngle()} />
            <span>deg</span>
          </div>
          <div className="actions">
            <button onClick={sendAngle}><Send size={17}/>Send angle</button>
            <button className="ghost" onClick={zeroAngle}><RotateCcw size={17}/>Set zero</button>
          </div>
          <Metric label="Angle command" value={angleState}/>
          <div className="note">Left/right keys are manual angular.z commands. Cruise does not change target heading.</div>
        </div>
      </div>
    </section>

    <section className="panel collectionPanel">
      <SectionTitle icon={Database} title="Data Collection" detail="CSV capture and download" />
      <div className="collectionTop">
        <Metric label="State" value={collection.status.state || 'idle'} tone={collection.status.collecting ? 'good' : ''}/>
        <Metric label="Rows" value={String(collection.status.sample_id || 0)}/>
        <Metric label="Current port" value={collection.current.port || collection.current_port} tone={collection.current.connected ? 'good' : ''}/>
        <Metric label="Current frames" value={String(collection.current.valid_total || 0)}/>
      </div>
      <div className="formGrid">
        <label>
          <span>Run ID</span>
          <input value={collection.run_id} placeholder="auto if empty" onChange={(e) => setCollection((c) => ({ ...c, run_id: e.target.value }))} />
        </label>
        <label>
          <span>Output dir</span>
          <input value={collection.output_dir} onChange={(e) => setCollection((c) => ({ ...c, output_dir: e.target.value }))} />
        </label>
        <label>
          <span>Current port</span>
          <input value={collection.current_port} onChange={(e) => setCollection((c) => ({ ...c, current_port: e.target.value }))} />
        </label>
      </div>
      <div className="actions">
        <button onClick={startCollection}><Radio size={17}/>Start collection</button>
        <button className="ghost" onClick={stopCollection}><Pause size={17}/>Stop collection</button>
        <button className="ghost" onClick={reconnectCurrentReader}><RefreshCw size={17}/>Reconnect current</button>
        <button className="ghost" onClick={refreshFiles}><RefreshCw size={17}/>Refresh files</button>
      </div>
      <button className="linkButton" onClick={() => setCollection((c) => ({ ...c, showAdvanced: !c.showAdvanced }))}>
        {collection.showAdvanced ? 'Hide advanced parameters' : 'Show advanced parameters'}
      </button>
      {collection.showAdvanced && <div className="formGrid advanced">
        <label>
          <span>Fault label</span>
          <input type="number" value={collection.fault_label} onChange={(e) => setCollection((c) => ({ ...c, fault_label: e.target.value }))} />
        </label>
        <label>
          <span>Fault name</span>
          <input value={collection.fault_name} onChange={(e) => setCollection((c) => ({ ...c, fault_name: e.target.value }))} />
        </label>
        <label>
          <span>Fault mode</span>
          <input type="number" value={collection.fault_mode} onChange={(e) => setCollection((c) => ({ ...c, fault_mode: e.target.value }))} />
        </label>
        <label>
          <span>Motion mode</span>
          <input value={collection.motion_mode} onChange={(e) => setCollection((c) => ({ ...c, motion_mode: e.target.value }))} />
        </label>
        <label>
          <span>Expected rate</span>
          <input type="number" step="0.1" value={collection.expected_rate} onChange={(e) => setCollection((c) => ({ ...c, expected_rate: e.target.value }))} />
        </label>
      </div>}
      <div className="fileList">
        {collection.fileError && <div className="errorLine">{collection.fileError}</div>}
        {collection.files.length === 0 ? <div className="muted">No CSV files loaded.</div> : collection.files.map((file) => (
          <div className="fileRow" key={file.name}>
            <span>{file.name}</span>
            <small>{(file.size / 1024).toFixed(1)} KB</small>
            <button className="ghost" onClick={() => downloadFile(file.name)}><Download size={16}/>Download</button>
          </div>
        ))}
      </div>
    </section>

    <section className="grid telemetry">
      <Metric label="Odom Vx" value={telemetry.vx}/>
      <Metric label="Odom Vy" value={telemetry.vy}/>
      <Metric label="Odom Wz" value={telemetry.wz}/>
      <Metric label="Odom X" value={telemetry.odomX}/>
      <Metric label="Odom Y" value={telemetry.odomY}/>
      <Metric label="Current A/B/C" value={`${telemetry.c0} / ${telemetry.c1} / ${telemetry.c2}`}/>
    </section>

    <section className="panel log">
      <SectionTitle icon={Activity} title="Event Log" />
      {log.length === 0 ? <div className="muted">No events yet.</div> : log.map((line) => <div key={line}>{line}</div>)}
    </section>
  </main>;
}

createRoot(document.getElementById('root')).render(<App />);
