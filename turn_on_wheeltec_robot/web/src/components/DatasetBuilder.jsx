import React, { useCallback, useRef, useState } from 'react';
import { Hammer, Play, RefreshCw, CheckCircle, XCircle } from 'lucide-react';
import { apiUrl } from '../utils';

function SectionTitle({ icon: Icon, title, detail }) {
  return (
    <div className="sectionTitle">
      <div><Icon size={18}/><strong>{title}</strong></div>
      {detail && <span>{detail}</span>}
    </div>
  );
}

export default function DatasetBuilder({ dataset, onFieldChange, t }) {
  const {
    featureSet, windowSize, stepSize, scaler,
    trimStart, trimEnd, allowSameRunSplit,
    inputDir, outputDir,
    building, buildLog, buildResult, buildError, buildId,
  } = dataset;

  const pollRef = useRef(null);
  const [datasets, setDatasets] = useState([]);

  const startBuild = useCallback(async () => {
    onFieldChange('building', true);
    onFieldChange('buildLog', []);
    onFieldChange('buildResult', null);
    onFieldChange('buildError', '');

    try {
      const resp = await fetch(apiUrl('/api/dataset/build'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          input_dir: inputDir,
          output_dir: outputDir,
          feature_set: featureSet,
          window_size: Number(windowSize) || 50,
          step_size: Number(stepSize) || 10,
          scaler: scaler,
          trim_start_sec: Number(trimStart) || 5,
          trim_end_sec: Number(trimEnd) || 5,
          allow_same_run_split: allowSameRunSplit,
        }),
      });
      const body = await resp.json();
      if (body.error) {
        onFieldChange('buildError', body.error);
        onFieldChange('building', false);
        return;
      }
      onFieldChange('buildId', body.build_id);
      startPolling(body.build_id);
    } catch (e) {
      onFieldChange('buildError', String(e));
      onFieldChange('building', false);
    }
  }, [inputDir, outputDir, featureSet, windowSize, stepSize, scaler, trimStart, trimEnd, allowSameRunSplit, onFieldChange]);

  const startPolling = useCallback((bid) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const resp = await fetch(apiUrl('/api/dataset/status', { build_id: bid }));
        const body = await resp.json();
        onFieldChange('buildLog', body.log_lines || []);
        if (body.state === 'done') {
          onFieldChange('building', false);
          onFieldChange('buildResult', body.result);
          clearInterval(pollRef.current);
          pollRef.current = null;
        } else if (body.state === 'error') {
          onFieldChange('building', false);
          onFieldChange('buildError', 'Build failed - check log');
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } catch (e) {
        // ignore poll errors
      }
    }, 1500);
  }, [onFieldChange]);

  const refreshDatasets = useCallback(async () => {
    try {
      const resp = await fetch(apiUrl('/api/dataset/list', { dir: outputDir }));
      const body = await resp.json();
      setDatasets(body.datasets || []);
    } catch {}
  }, [outputDir]);

  return (
    <section className="panel datasetPanel">
      <SectionTitle icon={Hammer} title={t('datasetBuilder')} detail={t('datasetBuilderHint')} />

      <div className="formGrid">
        <label>
          <span>{t('inputDir')}</span>
          <input value={inputDir} onChange={(e) => onFieldChange('inputDir', e.target.value)} />
        </label>
        <label>
          <span>{t('outputDir')}</span>
          <input value={outputDir} onChange={(e) => onFieldChange('outputDir', e.target.value)} />
        </label>
        <label>
          <span>{t('featureSet')}</span>
          <select value={featureSet} onChange={(e) => onFieldChange('featureSet', e.target.value)}>
            <option value="15ch">15ch (with wheel_speed)</option>
            <option value="12ch">12ch (without wheel_speed)</option>
          </select>
        </label>
        <label>
          <span>{t('windowSize')}</span>
          <input type="number" min="10" value={windowSize} onChange={(e) => onFieldChange('windowSize', e.target.value)} />
        </label>
        <label>
          <span>{t('stepSize')}</span>
          <input type="number" min="1" value={stepSize} onChange={(e) => onFieldChange('stepSize', e.target.value)} />
        </label>
        <label>
          <span>{t('scaler')}</span>
          <select value={scaler} onChange={(e) => onFieldChange('scaler', e.target.value)}>
            <option value="standard">StandardScaler</option>
          </select>
        </label>
        <label>
          <span>{t('trimStart')}</span>
          <input type="number" min="0" step="0.5" value={trimStart} onChange={(e) => onFieldChange('trimStart', e.target.value)} />
        </label>
        <label>
          <span>{t('trimEnd')}</span>
          <input type="number" min="0" step="0.5" value={trimEnd} onChange={(e) => onFieldChange('trimEnd', e.target.value)} />
        </label>
        <label className="checkboxLabel">
          <input type="checkbox" checked={allowSameRunSplit} onChange={(e) => onFieldChange('allowSameRunSplit', e.target.checked)} />
          <span>{t('allowSameRunSplit')}</span>
        </label>
      </div>

      <div className="actions">
        <button onClick={startBuild} disabled={building}>
          <Play size={16}/>{building ? t('building') : t('buildDatasetBtn')}
        </button>
        <button className="ghost" onClick={refreshDatasets}>
          <RefreshCw size={16}/>{t('refreshDatasets')}
        </button>
      </div>

      {buildError && <div className="errorLine" style={{ marginTop: 10 }}>{buildError}</div>}

      {buildResult && (
        <div className="buildResult" style={{ marginTop: 10 }}>
          <div className="resultHeader"><CheckCircle size={16}/> {t('buildComplete')}</div>
          <div className="resultGrid">
            <span>X_train: [{buildResult.train_samples}, {buildResult.num_features}, {buildResult.window_size}]</span>
            <span>X_test: [{buildResult.test_samples}, {buildResult.num_features}, {buildResult.window_size}]</span>
            <span>{t('featureSet')}: {buildResult.feature_set} ({buildResult.num_features}ch)</span>
            <span>{t('splitMethod')}: {buildResult.split_method}</span>
          </div>
        </div>
      )}

      {buildLog.length > 0 && (
        <div className="buildLog" style={{ marginTop: 10 }}>
          <div className="logHeader">{t('buildLog')} ({buildLog.length} lines)</div>
          <pre>{buildLog.slice(-60).join('\n')}</pre>
        </div>
      )}

      {datasets.length > 0 && (
        <div className="fileList" style={{ marginTop: 12 }}>
          {datasets.map((ds) => (
            <div className="fileRow" key={ds.name}>
              <span>{ds.name}</span>
              <small>{ds.config ? `${ds.config.feature_set} ${ds.config.train_samples}+${ds.config.test_samples}` : '--'}</small>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
