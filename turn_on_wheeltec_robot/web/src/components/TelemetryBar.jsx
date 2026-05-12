import React from 'react';

function Metric({ label, value }) {
  const title = typeof value === 'string' ? value : undefined;
  const valueClass = typeof value === 'string' && value.length > 14 ? 'longValue' : '';
  return <div className="metric"><span>{label}</span><strong className={valueClass} title={title}>{value}</strong></div>;
}

export default function TelemetryBar({ telemetry, t }) {
  return (
    <section className="grid telemetry">
      <Metric label={t('odomVx')} value={telemetry.vx}/>
      <Metric label={t('odomVy')} value={telemetry.vy}/>
      <Metric label={t('odomWz')} value={telemetry.wz}/>
      <Metric label={t('odomX')} value={telemetry.odomX}/>
      <Metric label={t('odomY')} value={telemetry.odomY}/>
      <Metric
        label={t('currentABC')}
        value={<span className="metricLines"><span>{telemetry.c0}</span><span>{telemetry.c1}</span><span>{telemetry.c2}</span></span>}
      />
    </section>
  );
}
