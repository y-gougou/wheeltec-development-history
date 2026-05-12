import React from 'react';

function Metric({ label, value }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}

export default function TelemetryBar({ telemetry, t }) {
  return (
    <section className="grid telemetry">
      <Metric label={t('odomVx')} value={telemetry.vx}/>
      <Metric label={t('odomVy')} value={telemetry.vy}/>
      <Metric label={t('odomWz')} value={telemetry.wz}/>
      <Metric label={t('odomX')} value={telemetry.odomX}/>
      <Metric label={t('odomY')} value={telemetry.odomY}/>
      <Metric label={t('currentABC')} value={`${telemetry.c0} / ${telemetry.c1} / ${telemetry.c2}`}/>
    </section>
  );
}
