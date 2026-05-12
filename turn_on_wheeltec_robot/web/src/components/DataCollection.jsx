import React from 'react';
import { Database, Radio, Pause, RefreshCw, Download } from 'lucide-react';

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

export default function DataCollection({ collection, onFieldChange, onStart, onStop, onReconnect, onRefresh, onDownload, onToggleAdvanced, t }) {
  const { status, current, currentPort, runId, outputDir, faultLabel, faultName, faultMode, motionMode, expectedRate, showAdvanced, files, fileError, autoStopDuration } = collection;

  return (
    <section className="panel collectionPanel">
      <SectionTitle icon={Database} title={t('dataCollection')} detail={t('collectionHint')} />
      <div className="collectionTop">
        <Metric label={t('state')} value={status.state || 'idle'} tone={status.collecting ? 'good' : ''}/>
        <Metric label={t('rows')} value={String(status.sample_id || 0)}/>
        <Metric label={t('currentPort')} value={current.port || currentPort} tone={current.connected ? 'good' : ''}/>
        <Metric label={t('currentFrames')} value={String(current.valid_total || 0)}/>
      </div>
      <div className="formGrid">
        <label><span>{t('runId')}</span><input value={runId} placeholder={t('autoIfEmpty')} onChange={(e) => onFieldChange('runId', e.target.value)} /></label>
        <label><span>{t('outputDir')}</span><input value={outputDir} onChange={(e) => onFieldChange('outputDir', e.target.value)} /></label>
        <label><span>{t('currentPort')}</span><input value={currentPort} onChange={(e) => onFieldChange('currentPort', e.target.value)} /></label>
      </div>
      <div className="actions">
        <button onClick={onStart}><Radio size={16}/>{t('startCollection')}</button>
        <button className="ghost" onClick={onStop}><Pause size={16}/>{t('stopCollection')}</button>
        <button className="ghost" onClick={onReconnect}><RefreshCw size={16}/>{t('reconnectCurrent')}</button>
        <button className="ghost" onClick={onRefresh}><RefreshCw size={16}/>{t('refreshFiles')}</button>
      </div>
      <button className="linkButton" onClick={onToggleAdvanced}>
        {showAdvanced ? t('hideAdvanced') : t('showAdvanced')}
      </button>
      {showAdvanced && (
        <div className="formGrid" style={{ marginTop: 10 }}>
          <label><span>{t('faultLabel')}</span><input type="number" value={faultLabel} onChange={(e) => onFieldChange('faultLabel', e.target.value)} /></label>
          <label><span>{t('faultName')}</span><input value={faultName} onChange={(e) => onFieldChange('faultName', e.target.value)} /></label>
          <label><span>{t('faultMode')}</span><input type="number" value={faultMode} onChange={(e) => onFieldChange('faultMode', e.target.value)} /></label>
          <label><span>{t('motionMode')}</span><input value={motionMode} onChange={(e) => onFieldChange('motionMode', e.target.value)} /></label>
          <label><span>{t('expectedRate')}</span><input type="number" step="0.1" value={expectedRate} onChange={(e) => onFieldChange('expectedRate', e.target.value)} /></label>
          <label><span>{t('autoStopDuration')} <small>({t('autoStopHint')})</small></span><input type="number" min="0" step="10" value={autoStopDuration} onChange={(e) => onFieldChange('autoStopDuration', e.target.value)} /></label>
        </div>
      )}
      <div className="fileList">
        {fileError && <div className="errorLine">{fileError}</div>}
        {files.length === 0 ? <div className="muted">{t('noFiles')}</div> : files.map((file) => (
          <div className="fileRow" key={file.name}>
            <span>{file.name}</span>
            <small>{(file.size / 1024).toFixed(1)} KB</small>
            <button className="ghost" onClick={() => onDownload(file.name)}><Download size={15}/>{t('download')}</button>
          </div>
        ))}
      </div>
    </section>
  );
}
