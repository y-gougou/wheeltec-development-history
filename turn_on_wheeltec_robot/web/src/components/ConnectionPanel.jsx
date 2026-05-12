import React from 'react';
import { Power, AlertTriangle } from 'lucide-react';

export default function ConnectionPanel({ url, onUrlChange, imuTopic, onImuTopicChange, onConnect, onDisconnect, onEstop, onRelease, rosState, t }) {
  return (
    <section className="connection panel">
      <input value={url} onChange={(e) => onUrlChange(e.target.value)} placeholder={t('rosUrl')} aria-label="rosbridge url" />
      <input value={imuTopic} onChange={(e) => onImuTopicChange(e.target.value)} placeholder={t('imuTopic')} aria-label="imu topic" />
      <button onClick={onConnect}><Power size={16}/>{t('connect')}</button>
      <button className="ghost" onClick={onDisconnect}>{t('disconnect')}</button>
      <button className="danger" onClick={() => onEstop(true)}><AlertTriangle size={16}/>{t('estop')}</button>
      <button className="ghost" onClick={() => onEstop(false)}>{t('release')}</button>
    </section>
  );
}
