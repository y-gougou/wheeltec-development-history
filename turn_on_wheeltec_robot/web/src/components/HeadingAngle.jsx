import React from 'react';
import { Compass, Send, RotateCcw } from 'lucide-react';

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

export default function HeadingAngle({ targetAngle, angleState, onAngleChange, onSend, onZero, onKeyDown, t }) {
  return (
    <div className="panel anglePanel">
      <SectionTitle icon={Compass} title={t('headingAngle')} detail={t('headingHint')} />
      <div className="angleInput">
        <input type="number" step="1" value={targetAngle} onChange={(e) => onAngleChange(e.target.value)} onKeyDown={onKeyDown} />
        <span>{t('deg')}</span>
      </div>
      <div className="actions">
        <button onClick={onSend}><Send size={16}/>{t('sendAngle')}</button>
        <button className="ghost" onClick={onZero}><RotateCcw size={16}/>{t('setZero')}</button>
      </div>
      <Metric label={t('angleCmd')} value={angleState}/>
      <div className="note">{t('angleNote')}</div>
    </div>
  );
}
