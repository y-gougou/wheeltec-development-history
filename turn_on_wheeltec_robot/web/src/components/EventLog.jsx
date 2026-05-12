import React from 'react';
import { Activity } from 'lucide-react';

function SectionTitle({ icon: Icon, title }) {
  return (
    <div className="sectionTitle">
      <div><Icon size={18}/><strong>{title}</strong></div>
    </div>
  );
}

export default function EventLog({ log, t }) {
  return (
    <section className="panel log">
      <SectionTitle icon={Activity} title={t('eventLog')} />
      {log.length === 0 ? <div className="muted">{t('noEvents')}</div> : log.map((line) => <div key={line}>{line}</div>)}
    </section>
  );
}
