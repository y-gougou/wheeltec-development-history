import React from 'react';
import { Gauge, Radio, Pause } from 'lucide-react';
import DirPad from './DirPad';
import { clamp, LIMITS } from '../utils';

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

export default function CruiseControl({ speed, direction, cruiseStatus, cruiseCmd, onDirectionChange, onSpeedChange, onStart, onStop, t }) {
  return (
    <div className="panel cruisePanel">
      <SectionTitle icon={Gauge} title={t('cruiseControl')} detail={t('cruiseHint')} />
      <DirPad value={direction} onChange={onDirectionChange} />
      <div className="sliderRow">
        <label htmlFor="cruiseSpeed">{t('cruiseSpeed')}</label>
        <input id="cruiseSpeed" type="range" min="0" max={LIMITS.maxLinear} step="0.01" value={speed} onChange={(e) => onSpeedChange(Number(e.target.value))} />
        <strong>{Number(speed).toFixed(2)} m/s</strong>
      </div>
      <div className="cmdGrid compact">
        <Metric label={t('targetVx')} value={cruiseCmd.linear.x.toFixed(2)}/>
        <Metric label={t('targetVy')} value={cruiseCmd.linear.y.toFixed(2)}/>
        <Metric label={t('targetWz')} value="0.00"/>
      </div>
      <div className="cmdGrid compact">
        <Metric label={t('actualVx')} value={cruiseStatus.actual.vx.toFixed(2)}/>
        <Metric label={t('actualVy')} value={cruiseStatus.actual.vy.toFixed(2)}/>
        <Metric label={t('actualWz')} value={cruiseStatus.actual.wz.toFixed(2)}/>
      </div>
      <div className="actions">
        <button onClick={onStart}><Radio size={16}/>{t('startCruise')}</button>
        <button className="ghost" onClick={onStop}><Pause size={16}/>{t('stopCruise')}</button>
      </div>
    </div>
  );
}
