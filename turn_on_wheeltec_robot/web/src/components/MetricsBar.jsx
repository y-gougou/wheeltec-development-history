import React from 'react';

function Metric({ label, value, tone = '' }) {
  return (
    <div className={`metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export default function MetricsBar({ controlStatus, cruiseActive, collectionState, collectionCollecting, voltage, imuZ, heading, headingSource, t }) {
  return (
    <section className="grid metrics">
      <Metric label={t('status')} value={controlStatus}/>
      <Metric label={t('cruiseStatus')} value={cruiseActive ? t('cruiseOn') : t('cruiseOff')} tone={cruiseActive ? 'good' : ''}/>
      <Metric label={t('collectionStatus')} value={collectionState || 'idle'} tone={collectionCollecting ? 'good' : ''}/>
      <Metric label={t('battery')} value={voltage}/>
      <Metric label={t('imuWz')} value={imuZ}/>
      <Metric label={t('headingValue')} value={heading === '--' ? '--' : `${heading} deg`}/>
      <Metric label={t('headingSource')} value={headingSource || '--'}/>
    </section>
  );
}
