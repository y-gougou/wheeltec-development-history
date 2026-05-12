import React, { useCallback, useEffect, useMemo, useReducer, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { AlertTriangle } from 'lucide-react';
import { useRosbridge } from './hooks/useRosbridge';
import { useKeyboard } from './hooks/useKeyboard';
import { useGamepad } from './hooks/useGamepad';
import { useLang } from './i18n';
import { LIMITS, clamp, axis, twist, emptyTwist, normalizeVector, parseCruiseStatus, parseJsonStatus, apiUrl } from './utils';
import './styles.css';

import TopBar from './components/TopBar';
import ConnectionPanel from './components/ConnectionPanel';
import MetricsBar from './components/MetricsBar';
import ManualDrive from './components/ManualDrive';
import CruiseControl from './components/CruiseControl';
import HeadingAngle from './components/HeadingAngle';
import DataCollection from './components/DataCollection';
import DatasetBuilder from './components/DatasetBuilder';
import TelemetryBar from './components/TelemetryBar';
import EventLog from './components/EventLog';

function getInitialTheme() {
  try {
    const saved = localStorage.getItem('theme');
    if (saved === 'dark' || saved === 'light') return saved;
  } catch {}
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

const initialState = {
  imuTopic: '/n100/imu',
  stick: { x: 0, y: 0 },
  lateral: 0,
  mult: 1,
  cruiseSpeed: 0.2,
  cruiseDirection: { x: 1, y: 0 },
  cruiseStatus: parseCruiseStatus('cruise: off'),
  targetAngle: 0,
  angleState: 'idle',
  controlStatus: 'idle',
  telemetry: { voltage: '--', vx: '0.00', vy: '0.00', wz: '0.00', imuZ: '--', heading: '--', headingSource: '--', odomX: '--', odomY: '--', c0: '--', c1: '--', c2: '--' },
  collection: {
    currentPort: '/dev/ttyUSB1',
    outputDir: '/home/wheeltec/R550PLUS_data_collect/log_v2',
    faultLabel: 0,
    faultName: 'normal',
    faultMode: 0,
    runId: '',
    motionMode: 'straight_back_forth_0.25ms',
    expectedRate: 20,
    status: { state: 'idle', collecting: false, sample_id: 0 },
    current: { connected: false, port: '/dev/ttyUSB1', valid_total: 0 },
    files: [],
    fileError: '',
    showAdvanced: false,
    autoStopDuration: 0,
  },
  dataset: {
    featureSet: '15ch',
    windowSize: 50,
    stepSize: 10,
    scaler: 'standard',
    trimStart: 5,
    trimEnd: 5,
    allowSameRunSplit: false,
    inputDir: '/home/wheeltec/R550PLUS_data_collect/log_v2',
    outputDir: '/home/wheeltec/R550PLUS_dataset/four_class_v1',
    building: false,
    buildLog: [],
    buildResult: null,
    buildError: '',
    buildId: '',
  },
  log: [],
  theme: getInitialTheme(),
};

function reducer(state, action) {
  switch (action.type) {
    case 'SET_IMU_TOPIC': return { ...state, imuTopic: action.value };
    case 'SET_STICK': return { ...state, stick: action.value };
    case 'SET_LATERAL': return { ...state, lateral: action.value };
    case 'SET_MULT': return { ...state, mult: action.value };
    case 'SET_CRUISE_SPEED': return { ...state, cruiseSpeed: action.value };
    case 'SET_CRUISE_DIRECTION': return { ...state, cruiseDirection: action.value };
    case 'SET_CRUISE_STATUS': return { ...state, cruiseStatus: action.value };
    case 'SET_TARGET_ANGLE': return { ...state, targetAngle: action.value };
    case 'SET_ANGLE_STATE': return { ...state, angleState: action.value };
    case 'SET_CONTROL_STATUS': return { ...state, controlStatus: action.value };
    case 'SET_TELEMETRY': return { ...state, telemetry: { ...state.telemetry, ...action.value } };
    case 'SET_COLLECTION': return { ...state, collection: { ...state.collection, ...action.value } };
    case 'SET_DATASET': return { ...state, dataset: { ...state.dataset, ...action.value } };
    case 'ADD_LOG': return { ...state, log: [`${new Date().toLocaleTimeString()}  ${action.text}`, ...state.log].slice(0, 12) };
    case 'SET_THEME': return { ...state, theme: action.value };
    default: return state;
  }
}

function App() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const { t, lang, toggle: toggleLang } = useLang();

  const defaultUrl = `ws://${window.location.hostname || '127.0.0.1'}:9090`;
  const ros = useRosbridge(defaultUrl);

  const addLog = useCallback((text) => dispatch({ type: 'ADD_LOG', text }), []);
  const pendingTelemetryRef = useRef({});
  const telemetryTimerRef = useRef(null);
  const pendingCollectionRef = useRef({});
  const collectionTimerRef = useRef(null);

  const queueTelemetry = useCallback((value) => {
    pendingTelemetryRef.current = { ...pendingTelemetryRef.current, ...value };
    if (telemetryTimerRef.current) return;
    telemetryTimerRef.current = window.setTimeout(() => {
      telemetryTimerRef.current = null;
      const pending = pendingTelemetryRef.current;
      pendingTelemetryRef.current = {};
      dispatch({ type: 'SET_TELEMETRY', value: pending });
    }, 100);
  }, []);

  const queueCollection = useCallback((value) => {
    pendingCollectionRef.current = { ...pendingCollectionRef.current, ...value };
    if (collectionTimerRef.current) return;
    collectionTimerRef.current = window.setTimeout(() => {
      collectionTimerRef.current = null;
      const pending = pendingCollectionRef.current;
      pendingCollectionRef.current = {};
      dispatch({ type: 'SET_COLLECTION', value: pending });
    }, 150);
  }, []);

  useEffect(() => () => {
    if (telemetryTimerRef.current) window.clearTimeout(telemetryTimerRef.current);
    if (collectionTimerRef.current) window.clearTimeout(collectionTimerRef.current);
  }, []);

  // Theme
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', state.theme);
    try { localStorage.setItem('theme', state.theme); } catch {}
  }, [state.theme]);

  const toggleTheme = useCallback(() => {
    dispatch({ type: 'SET_THEME', value: state.theme === 'dark' ? 'light' : 'dark' });
  }, [state.theme]);

  // Cruise command
  const cruiseVector = useMemo(() => normalizeVector(state.cruiseDirection), [state.cruiseDirection]);
  const cruiseCmd = useMemo(() => {
    const speed = clamp(Number(state.cruiseSpeed) || 0, 0, LIMITS.maxLinear);
    return twist(cruiseVector.x * speed, cruiseVector.y * speed, 0);
  }, [state.cruiseSpeed, cruiseVector]);

  // Manual drive command
  const command = useMemo(() => {
    const drive = axis(-state.stick.y);
    const turn = axis(state.stick.x);
    const lat = axis(state.lateral);
    return twist(drive * LIMITS.maxLinear * state.mult, lat * LIMITS.maxLateral * state.mult, -turn * LIMITS.maxAngular * state.mult);
  }, [state.stick, state.lateral, state.mult]);

  // Subscribe to ROS topics
  useEffect(() => {
    const unsubs = [];
    unsubs.push(ros.subscribe('/PowerVoltage', 'std_msgs/Float32', (msg) => queueTelemetry({ voltage: `${Number(msg.data || 0).toFixed(2)} V` })));
    unsubs.push(ros.subscribe('/current_data', 'std_msgs/Float32MultiArray', (msg) => {
      const d = msg.data || [];
      queueTelemetry({ c0: `${Number(d[0] || 0).toFixed(3)} A`, c1: `${Number(d[1] || 0).toFixed(3)} A`, c2: `${Number(d[2] || 0).toFixed(3)} A` });
    }));
    unsubs.push(ros.subscribe(state.imuTopic, 'sensor_msgs/Imu', (msg) => queueTelemetry({ imuZ: Number(msg.angular_velocity?.z || 0).toFixed(3) })));
    unsubs.push(ros.subscribe('/chassis/heading_deg', 'std_msgs/Float32', (msg) => {
      const value = Number(msg.data);
      queueTelemetry({ heading: Number.isFinite(value) ? value.toFixed(1) : '--' });
    }));
    unsubs.push(ros.subscribe('/web/heading_status', 'std_msgs/String', (msg) => {
      const parsed = parseJsonStatus(msg.data, {});
      const heading = Number(parsed.heading_deg);
      queueTelemetry(
        Number.isFinite(heading)
          ? { headingSource: parsed.source || parsed.mode || msg.data || '--', heading: heading.toFixed(1) }
          : { headingSource: parsed.source || parsed.mode || msg.data || '--' },
      );
    }));
    unsubs.push(ros.subscribe('/odom', 'nav_msgs/Odometry', (msg) => {
      const tw = msg.twist?.twist || {};
      const po = msg.pose?.pose || {};
      queueTelemetry({
        vx: Number(tw.linear?.x || 0).toFixed(2),
        vy: Number(tw.linear?.y || 0).toFixed(2),
        wz: Number(tw.angular?.z || 0).toFixed(2),
        odomX: Number(po.position?.x || 0).toFixed(2),
        odomY: Number(po.position?.y || 0).toFixed(2),
      });
    }));
    unsubs.push(ros.subscribe('/web/control_status', 'std_msgs/String', (msg) => dispatch({ type: 'SET_CONTROL_STATUS', value: msg.data || 'idle' })));
    unsubs.push(ros.subscribe('/web/cruise_status', 'std_msgs/String', (msg) => dispatch({ type: 'SET_CRUISE_STATUS', value: parseCruiseStatus(msg.data || '') })));
    unsubs.push(ros.subscribe('/web/collection_status', 'std_msgs/String', (msg) => {
      queueCollection({ status: parseJsonStatus(msg.data, { state: 'idle', collecting: false, sample_id: 0 }) });
    }));
    unsubs.push(ros.subscribe('/web/current_reader_status', 'std_msgs/String', (msg) => {
      const parsed = parseJsonStatus(msg.data, { connected: false });
      queueCollection({ current: parsed, currentPort: parsed.port || state.collection.currentPort });
    }));
    return () => unsubs.forEach((unsubscribe) => unsubscribe && unsubscribe());
  }, [ros.subscribe, state.imuTopic, state.collection.currentPort, queueTelemetry, queueCollection]);

  // Heartbeat + command sender
  useEffect(() => {
    const heartbeat = setInterval(() => ros.publish('/web/heartbeat', {}), LIMITS.heartbeatMs);
    const sender = setInterval(() => {
      if (!state.cruiseStatus.active) ros.publish('/cmd_vel_web', command);
    }, LIMITS.commandMs);
    return () => { clearInterval(heartbeat); clearInterval(sender); };
  }, [ros.publish, command, state.cruiseStatus.active]);

  // Stop function
  const stop = useCallback(() => {
    dispatch({ type: 'SET_STICK', value: { x: 0, y: 0 } });
    dispatch({ type: 'SET_LATERAL', value: 0 });
    ros.publish('/web/test_enable', { data: false });
    ros.publish('/web/cruise_enable', { data: false });
    ros.publish('/cmd_vel_web', emptyTwist());
    addLog('Stop command sent');
  }, [ros.publish, addLog]);

  // Keyboard
  useKeyboard(dispatch, stop);

  // Gamepad
  const gamepadAxes = useCallback((axes) => {
    dispatch({ type: 'SET_STICK', value: { x: axes.turn, y: axes.y } });
    dispatch({ type: 'SET_LATERAL', value: axes.x });
  }, []);
  const gamepadEstop = useCallback(() => estop(true), []);
  const gamepad = useGamepad(gamepadAxes, stop, gamepadEstop);

  // E-stop
  function estop(active) {
    if (active) stop();
    ros.publish('/web/estop', { data: active });
    addLog(active ? 'E-stop locked' : 'E-stop released');
  }

  // Cruise
  function startCruise() {
    ros.publish('/web/cruise_cmd', cruiseCmd);
    ros.publish('/web/cruise_enable', { data: true });
    addLog(`Cruise start vx=${cruiseCmd.linear.x.toFixed(2)} vy=${cruiseCmd.linear.y.toFixed(2)}`);
  }

  function stopCruise() {
    ros.publish('/web/cruise_enable', { data: false });
    ros.publish('/cmd_vel_web', emptyTwist());
    addLog('Cruise stopped');
  }

  // Heading
  function sendAngle() {
    const angle = Number(state.targetAngle);
    if (!Number.isFinite(angle)) return;
    ros.publish('/target_angle', { data: angle });
    dispatch({ type: 'SET_ANGLE_STATE', value: `${angle.toFixed(1)} deg` });
    addLog(`Target angle ${angle.toFixed(1)} deg`);
  }

  function zeroAngle() {
    ros.publish('/target_angle_reset', {});
    ros.publish('/web/heading_zero', {});
    dispatch({ type: 'SET_TARGET_ANGLE', value: 0 });
    dispatch({ type: 'SET_ANGLE_STATE', value: 'current heading = 0 deg' });
    addLog('Current heading set as 0 deg');
  }

  // Collection
  const collectionConfig = useMemo(() => ({
    output_dir: state.collection.outputDir,
    fault_label: Number(state.collection.faultLabel) || 0,
    fault_name: state.collection.faultName || 'normal',
    fault_mode: Number(state.collection.faultMode) || 0,
    run_id: state.collection.runId || '',
    motion_mode: state.collection.motionMode || 'straight_back_forth_0.25ms',
    expected_rate: Number(state.collection.expectedRate) || 20,
  }), [state.collection.outputDir, state.collection.faultLabel, state.collection.faultName, state.collection.faultMode, state.collection.runId, state.collection.motionMode, state.collection.expectedRate]);

  function publishCollectionConfig(extra = {}) {
    return ros.publish('/web/collection_config', { data: JSON.stringify({ ...collectionConfig, ...extra }) });
  }

  function reconnectCurrentReader() {
    ros.publish('/web/current_reader_config', { data: JSON.stringify({ port: state.collection.currentPort, reconnect: true }) });
    addLog(`Current reader reconnect ${state.collection.currentPort}`);
  }

  const autoStopTimerRef = useRef(null);

  function startCollection() {
    reconnectCurrentReader();
    publishCollectionConfig({ start: true });
    ros.publish('/web/collection_enable', { data: true });
    addLog(`Collection start ${state.collection.runId || '(auto run_id)'}`);
    setTimeout(refreshFiles, 800);

    // Auto-stop after duration
    const duration = Number(state.collection.autoStopDuration) || 0;
    if (duration > 0) {
      if (autoStopTimerRef.current) clearTimeout(autoStopTimerRef.current);
      autoStopTimerRef.current = setTimeout(() => {
        stopCollection();
        addLog(`Auto-stopped after ${duration}s`);
      }, duration * 1000);
    }
  }

  function stopCollection() {
    if (autoStopTimerRef.current) {
      clearTimeout(autoStopTimerRef.current);
      autoStopTimerRef.current = null;
    }
    ros.publish('/web/collection_enable', { data: false });
    addLog('Collection stopped');
    setTimeout(refreshFiles, 500);
  }

  async function refreshFiles() {
    try {
      const response = await fetch(apiUrl('/api/data/list', { dir: state.collection.outputDir }));
      const body = await response.json();
      dispatch({ type: 'SET_COLLECTION', value: { files: body.files || [], fileError: body.error || '' } });
    } catch (e) {
      dispatch({ type: 'SET_COLLECTION', value: { fileError: String(e) } });
    }
  }

  function downloadFile(name) {
    window.open(apiUrl(`/api/data/download/${encodeURIComponent(name)}`, { dir: state.collection.outputDir }), '_blank');
  }

  function onCollectionFieldChange(field, value) {
    dispatch({ type: 'SET_COLLECTION', value: { [field]: value } });
  }

  function onDatasetFieldChange(field, value) {
    dispatch({ type: 'SET_DATASET', value: { [field]: value } });
  }

  return (
    <main className="app">
      <TopBar rosState={ros.state} theme={state.theme} onToggleTheme={toggleTheme} lang={lang} onToggleLang={toggleLang} gamepadConnected={gamepad.connected} t={t} />

      <ConnectionPanel
        url={ros.url} onUrlChange={ros.setUrl}
        imuTopic={state.imuTopic} onImuTopicChange={(v) => dispatch({ type: 'SET_IMU_TOPIC', value: v })}
        onConnect={ros.connect} onDisconnect={ros.disconnect}
        onEstop={estop} onRelease={() => estop(false)}
        rosState={ros.state} t={t}
      />

      {ros.lastError && <div className="errorLine">{ros.lastError}</div>}

      <MetricsBar
        controlStatus={state.controlStatus}
        cruiseActive={state.cruiseStatus.active}
        collectionState={state.collection.status.state}
        collectionCollecting={state.collection.status.collecting}
        voltage={state.telemetry.voltage}
        imuZ={state.telemetry.imuZ}
        heading={state.telemetry.heading}
        headingSource={state.telemetry.headingSource}
        t={t}
      />

      <section className="layout">
        <ManualDrive
          stick={state.stick} lateral={state.lateral} mult={state.mult}
          onStop={stop}
          onStickChange={(v) => dispatch({ type: 'SET_STICK', value: v })}
          onStrafeLeft={(v) => dispatch({ type: 'SET_LATERAL', value: v })}
          onStrafeRight={(v) => dispatch({ type: 'SET_LATERAL', value: v })}
          t={t}
        />

        <div className="sideStack">
          <CruiseControl
            speed={state.cruiseSpeed}
            direction={state.cruiseDirection}
            cruiseStatus={state.cruiseStatus}
            cruiseCmd={cruiseCmd}
            onDirectionChange={(d) => dispatch({ type: 'SET_CRUISE_DIRECTION', value: d })}
            onSpeedChange={(s) => dispatch({ type: 'SET_CRUISE_SPEED', value: s })}
            onStart={startCruise} onStop={stopCruise} t={t}
          />

          <HeadingAngle
            targetAngle={state.targetAngle}
            angleState={state.angleState}
            onAngleChange={(v) => dispatch({ type: 'SET_TARGET_ANGLE', value: v })}
            onSend={sendAngle} onZero={zeroAngle}
            onKeyDown={(e) => e.key === 'Enter' && sendAngle()}
            t={t}
          />
        </div>
      </section>

      <DataCollection
        collection={state.collection}
        onFieldChange={onCollectionFieldChange}
        onStart={startCollection} onStop={stopCollection}
        onReconnect={reconnectCurrentReader} onRefresh={refreshFiles}
        onDownload={downloadFile}
        onToggleAdvanced={() => dispatch({ type: 'SET_COLLECTION', value: { showAdvanced: !state.collection.showAdvanced } })}
        t={t}
      />

      <DatasetBuilder
        dataset={state.dataset}
        onFieldChange={onDatasetFieldChange}
        t={t}
      />

      <TelemetryBar telemetry={state.telemetry} t={t} />

      <EventLog log={state.log} t={t} />
    </main>
  );
}

createRoot(document.getElementById('root')).render(<App />);
