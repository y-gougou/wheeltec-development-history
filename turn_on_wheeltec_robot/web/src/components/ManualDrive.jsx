import React, { useCallback } from 'react';
import { Gamepad2, Square, ArrowLeft, ArrowRight } from 'lucide-react';
import { clamp, axis, LIMITS } from '../utils';

function SectionTitle({ icon: Icon, title, detail }) {
  return (
    <div className="sectionTitle">
      <div><Icon size={18}/><strong>{title}</strong></div>
      {detail && <span>{detail}</span>}
    </div>
  );
}

function Metric({ label, value }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}

export default function ManualDrive({ stick, lateral, mult, onStop, onStickChange, onStrafeLeft, onStrafeRight, t }) {
  const drive = axis(-stick.y);
  const turn = axis(stick.x);
  const lat = axis(lateral);

  const twist = {
    linear: { x: drive * LIMITS.maxLinear * mult, y: lat * LIMITS.maxLateral * mult, z: 0 },
    angular: { x: 0, y: 0, z: -turn * LIMITS.maxAngular * mult },
  };

  function pointerMove(e) {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = clamp((e.clientX - rect.left - rect.width / 2) / (rect.width * 0.38), -1, 1);
    const y = clamp((e.clientY - rect.top - rect.height / 2) / (rect.height * 0.38), -1, 1);
    onStickChange({ x, y });
  }

  return (
    <div className="panel drivePanel">
      <SectionTitle icon={Gamepad2} title={t('manualDrive')} detail={t('manualDriveHint')} />
      <div
        className="stick"
        onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); pointerMove(e); }}
        onPointerMove={(e) => e.buttons && pointerMove(e)}
        onPointerUp={() => onStickChange({ x: 0, y: 0 })}
      >
        <div className="knob" style={{ transform: `translate(${stick.x * 76}px, ${stick.y * 76}px)` }} />
      </div>
      <div className="cmdGrid">
        <Metric label={t('linearX')} value={twist.linear.x.toFixed(2)}/>
        <Metric label={t('linearY')} value={twist.linear.y.toFixed(2)}/>
        <Metric label={t('angularZ')} value={twist.angular.z.toFixed(2)}/>
        <Metric label={t('speedScale')} value={`${mult.toFixed(1)}x`}/>
      </div>
      <div className="actions">
        <button onClick={onStop}><Square size={16}/>{t('stop')}</button>
        <button className="ghost" onMouseDown={() => onStrafeLeft(-1)} onMouseUp={() => onStrafeLeft(0)} onMouseLeave={() => onStrafeLeft(0)}>
          <ArrowLeft size={16}/>{t('strafeLeft')}
        </button>
        <button className="ghost" onMouseDown={() => onStrafeRight(1)} onMouseUp={() => onStrafeRight(0)} onMouseLeave={() => onStrafeRight(0)}>
          <ArrowRight size={16}/>{t('strafeRight')}
        </button>
      </div>
    </div>
  );
}
