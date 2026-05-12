import React from 'react';
import { AlertTriangle, Zap, RotateCcw } from 'lucide-react';

function SectionTitle({ icon: Icon, title, detail }) {
  return (
    <div className="sectionTitle">
      <div><Icon size={18}/><strong>{title}</strong></div>
      {detail && <span>{detail}</span>}
    </div>
  );
}

function Metric({ label, value, tone = '' }) {
  const title = typeof value === 'string' ? value : undefined;
  const valueClass = typeof value === 'string' && value.length > 14 ? 'longValue' : '';
  return <div className={`metric ${tone}`}><span>{label}</span><strong className={valueClass} title={title}>{value}</strong></div>;
}

export default function FaultInjection({ faultInjection, onFieldChange, onApply, onReset, t }) {
  const { enableFault, faultType, wheels, alpha, status } = faultInjection;
  const injecting = status.injecting || (enableFault && faultType === 'drive_abnormal');
  const selectedWheels = ['A', 'B', 'C'].filter((wheel) => wheels?.[wheel]).join('+') || 'none';
  const alphaLabel = ['A', 'B', 'C']
    .filter((wheel) => wheels?.[wheel])
    .map((wheel) => `${wheel}:${Number(alpha?.[wheel] ?? 1).toFixed(2)}`)
    .join(' ') || '1.00';

  function setWheel(wheel, checked) {
    onFieldChange('wheels', { ...wheels, [wheel]: checked });
  }

  function setAlpha(wheel, value) {
    onFieldChange('alpha', { ...alpha, [wheel]: value });
  }

  return (
    <section className="panel collectionPanel">
      <SectionTitle icon={AlertTriangle} title={t('faultInjection')} detail={t('faultInjectionHint')} />
      <div className="collectionTop">
        <Metric label={t('enableFault')} value={enableFault ? t('injectionOn') : t('injectionOff')} tone={injecting ? 'warn' : ''}/>
        <Metric label={t('faultType')} value={faultType}/>
        <Metric label={t('faultWheel')} value={status.fault_wheel || selectedWheels}/>
        <Metric label={t('faultAlpha')} value={alphaLabel}/>
      </div>
      <div className="formGrid">
        <label>
          <span>{t('enableFault')}</span>
          <select value={enableFault ? 'true' : 'false'} onChange={(e) => onFieldChange('enableFault', e.target.value === 'true')}>
            <option value="false">{t('injectionOff')}</option>
            <option value="true">{t('injectionOn')}</option>
          </select>
        </label>
        <label>
          <span>{t('faultType')}</span>
          <select value={faultType} onChange={(e) => onFieldChange('faultType', e.target.value)}>
            <option value="normal">{t('normalMode')}</option>
            <option value="drive_abnormal">{t('driveAbnormal')}</option>
          </select>
        </label>
        {['A', 'B', 'C'].map((wheel) => (
          <label key={wheel}>
            <span>{t('faultWheel')} {wheel}</span>
            <div className="checkboxLabel">
              <input
                type="checkbox"
                checked={Boolean(wheels?.[wheel])}
                onChange={(e) => setWheel(wheel, e.target.checked)}
              />
              <span>{wheels?.[wheel] ? t('injectionOn') : t('injectionOff')}</span>
            </div>
            <input
              type="number"
              min="0"
              max="1"
              step="0.05"
              value={alpha?.[wheel] ?? 1}
              onChange={(e) => setAlpha(wheel, e.target.value)}
            />
          </label>
        ))}
      </div>
      <div className="actions">
        <button onClick={onApply}><Zap size={16}/>{t('applyFaultConfig')}</button>
        <button className="ghost" onClick={onReset}><RotateCcw size={16}/>{t('resetFault')}</button>
      </div>
    </section>
  );
}
