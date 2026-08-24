import { useEffect, useMemo, useState } from 'react'
import axios from 'axios'

// ── Types ─────────────────────────────────────────────────────────────────────
type AnswerValue = string | number | boolean | string[]
type SectionScore = { score: number; max: number; pct: number }
type ScoreResult = {
  total: number; max: number; pct: number; band: string
  sections: Record<string, SectionScore>
  percentile: number; population_size: number
}
type AnalyticsSummary = {
  total_submissions: number
  strategy_adoption_pct: number
  ci_cd_adoption_pct: number
  avg_monitoring_coverage: number
}
type SubmissionRecord = {
  submission_id: string; respondent_id: string; submitted_at: string
  score: number; pct: number; band: string; percentile: number
}
type QuestionDist = { type: string; n: number; distribution: Record<string, number> }
type ResponseDistributions = Record<string, QuestionDist>
type Prediction = {
  probability: number | null; prediction: boolean | null
  contributions: Array<{feature: string; value: number; weight: number}>
  available: boolean; error?: string
}
type MlRun = {
  run_id: string; experiment: string; status: string; started: number
  metrics: Record<string, number>; params: Record<string, string>
}
type MlExperiment = { experiment_id: string; name: string; lifecycle_stage: string }

type ModelVersion = {
  name: string; version: string; stage: string; status: string
  created: number; run_id: string
  metrics: Record<string, number>
  params: Record<string, string>
}
type FeatureStat = {
  mean: number; type: 'binary' | 'count' | 'categorical'; n: number
  min?: number; max?: number
  distribution?: Record<string, number>
}
type FeatureStats = {
  total_submissions: number; labeled_submissions: number
  high_readiness_n: number; low_readiness_n: number; high_readiness_rate: number
  features: Record<string, FeatureStat>
}

// ── Constants ─────────────────────────────────────────────────────────────────
const API         = 'http://localhost:8000'
const templateId  = '01KX0J5J5C0V5JHKYXY9MXBZJJ'
const GRAFANA_URL = 'http://localhost:3000/d/assessment-platform/assessment-platform-overview?orgId=1&kiosk=tv&refresh=30s&theme=dark'

const TOOLS = [
  { label: 'MLflow',    url: 'http://localhost:5000', color: '#0ea5e9', desc: 'Experiment tracking & model registry' },
  { label: 'Grafana',   url: 'http://localhost:3000', color: '#f97316', desc: 'Metrics, logs & trace dashboards' },
  { label: 'Superset',  url: 'http://localhost:8088', color: '#a855f7', desc: 'dbt mart analytics dashboards' },
  { label: 'Redpanda',  url: 'http://localhost:8081', color: '#e11d48', desc: 'Kafka-compatible topic browser' },
  { label: 'Trino',     url: 'http://localhost:8080', color: '#eab308', desc: 'Distributed SQL query engine' },
  { label: 'MinIO',     url: 'http://localhost:9001', color: '#10b981', desc: 'Object store — Iceberg & MLflow artifacts' },
]

const SECTION_COLORS: Record<string, string> = {
  Strategy:      '#6366f1',
  Production:    '#0ea5e9',
  MLOps:         '#a855f7',
  Observability: '#f97316',
  General:       '#64748b',
}

const BAND_COLOR: Record<string, string> = {
  Emerging:   '#ef4444',
  Developing: '#f59e0b',
  Advanced:   '#22c55e',
}

const questions = [
  { section: 'Strategy',      key: 'ml_strategy',         type: 'boolean',
    prompt: 'Does your organisation have a documented ML/AI strategy with executive sponsorship?' },
  { section: 'Production',    key: 'prod_scale',           type: 'single_select',
    prompt: 'How many ML models does your organisation currently have in production?',
    options: ['10+ models in production', '1–9 models in production', 'Proof of concept / pilot', 'Not yet deployed'] },
  { section: 'MLOps',         key: 'experiment_tracking',  type: 'single_select',
    prompt: 'How does your team track ML experiments and model lineage?',
    options: ['MLflow + model registry', 'Weights & Biases / Neptune', 'Custom solution', 'Notebooks / ad-hoc'] },
  { section: 'MLOps',         key: 'ci_cd_ml',             type: 'boolean',
    prompt: 'Do you have CI/CD pipelines for automated model training, validation, and deployment?' },
  { section: 'Production',    key: 'serving_patterns',     type: 'multi_select',
    prompt: 'Which model serving patterns are currently in production?',
    options: ['Real-time API (<100ms)', 'Batch inference', 'Streaming (Kafka / Redpanda)', 'Edge / on-device', 'Shadow mode / A-B testing'] },
  { section: 'Observability', key: 'model_monitoring',     type: 'multi_select',
    prompt: 'What do you actively monitor for models in production?',
    options: ['Data drift', 'Prediction drift', 'Latency / SLOs', 'Feature quality', 'Business KPIs'] },
  { section: 'General',       key: 'notes',                type: 'text',
    prompt: 'Anything else to capture? (team structure, key blockers, roadmap priorities...)' },
]

// ── Helpers ───────────────────────────────────────────────────────────────────
function barColor(pct: number) {
  return pct >= 70 ? '#22c55e' : pct >= 40 ? '#f59e0b' : '#ef4444'
}
function fmtTime(ms: number) {
  return ms ? new Date(ms).toLocaleString() : '—'
}

// ── Assessment view ───────────────────────────────────────────────────────────
function AssessmentView() {
  const [respondentId, setRespondentId] = useState('org-001')
  const [answers, setAnswers]           = useState<Record<string, AnswerValue>>({})
  const [submitting, setSubmitting]     = useState(false)
  const [submissionId, setSubmissionId] = useState('')
  const [score, setScore]               = useState<ScoreResult | null>(null)
  const [analytics, setAnalytics]       = useState<AnalyticsSummary | null>(null)
  const [prediction, setPrediction]     = useState<Prediction | null>(null)
  const [error, setError]               = useState('')

  const completion = useMemo(() => {
    const required = questions.filter(q => q.type !== 'text')
    return required.filter(q => answers[q.key] !== undefined).length / required.length
  }, [answers])

  function updateAnswer(key: string, value: AnswerValue) {
    setAnswers(prev => ({ ...prev, [key]: value }))
  }

  async function submit() {
    setSubmitting(true); setError(''); setScore(null); setAnalytics(null); setPrediction(null)
    try {
      const payload = {
        template_id: templateId, respondent_id: respondentId,
        channel: 'virtual', metadata_json: { source: 'react-ui' },
        answers: questions.map(q => ({
          question_key:   q.key,
          answer_text:    typeof answers[q.key] === 'string'  ? answers[q.key] : null,
          answer_numeric: typeof answers[q.key] === 'number'  ? answers[q.key] : null,
          answer_json:    Array.isArray(answers[q.key]) || typeof answers[q.key] === 'boolean'
                            ? { value: answers[q.key] } : null,
        })),
      }
      const { data } = await axios.post(`${API}/submissions`, payload)
      setSubmissionId(data.submission_id)
      const [scoreRes, analyticsRes, predRes] = await Promise.all([
        axios.get(`${API}/submissions/${data.submission_id}/score`),
        axios.get(`${API}/analytics/summary`),
        axios.get(`${API}/submissions/${data.submission_id}/predict`),
      ])
      setScore(scoreRes.data)
      setAnalytics(analyticsRes.data)
      setPrediction(predRes.data)
    } catch {
      setError('Submission failed — check the API is running and the template ID is valid.')
    } finally {
      setSubmitting(false)
    }
  }

  const userMonitoring = Array.isArray(answers['model_monitoring'])
    ? (answers['model_monitoring'] as string[]).length : null

  return (
    <div className="page">
      {/* Sidebar */}
      <aside className="sidebar">
        <div>
          <h1>Org Readiness Assessment</h1>
          <p>Staff ML Engineer · Evaluate your organisation's ML maturity across strategy, production, MLOps, and observability.</p>
        </div>

        <div className="card">
          <label>Organisation ID</label>
          <input value={respondentId} onChange={e => setRespondentId(e.target.value)} />
          <div className="progress-row">
            <label style={{ marginBottom: 0 }}>Progress</label>
            <span className="progress-pct">{Math.round(completion * 100)}%</span>
          </div>
          <progress max={1} value={completion} />
        </div>

        {score ? (
          <div className="card score-card">
            <label>Readiness Score</label>
            <div className="score-ring">
              <div className="score-number" style={{ color: BAND_COLOR[score.band] }}>{score.pct}</div>
              <div className="score-denom">/ 100</div>
            </div>
            <div className="score-band" style={{ color: BAND_COLOR[score.band] }}>{score.band}</div>
            <div className="score-sub">{score.total} of {score.max} pts</div>
            {score.population_size > 1 && (
              <div className="score-percentile">
                Top {100 - score.percentile}% of {score.population_size} respondents
              </div>
            )}
          </div>
        ) : (
          <div className="card dim-card">
            <label>Dimensions</label>
            {['Strategy', 'Production', 'MLOps', 'Observability'].map(s => (
              <div key={s} className="dim-row">
                <span className="dim-dot" style={{ background: SECTION_COLORS[s] }} />
                <span>{s}</span>
              </div>
            ))}
          </div>
        )}
      </aside>

      {/* Questions */}
      <main className="content">
        {questions.map((q, i) => (
          <section className="card question-card" key={q.key}>
            <div className="question-header">
              <span className="section-badge"
                style={{ background: SECTION_COLORS[q.section] + '22', color: SECTION_COLORS[q.section], borderColor: SECTION_COLORS[q.section] + '55' }}>
                {q.section}
              </span>
              <span className="question-num">Q{i + 1}</span>
            </div>
            <h2>{q.prompt}</h2>

            {q.type === 'text' && (
              <textarea rows={3} placeholder="Optional — share context here..."
                onChange={e => updateAnswer(q.key, e.target.value)} />
            )}
            {q.type === 'boolean' && (
              <div className="bool-group">
                <button className={answers[q.key] === true  ? 'active' : ''} onClick={() => updateAnswer(q.key, true)}>Yes</button>
                <button className={answers[q.key] === false ? 'active' : ''} onClick={() => updateAnswer(q.key, false)}>No</button>
              </div>
            )}
            {q.type === 'single_select' && q.options && (
              <div className="option-group">
                {q.options.map(o => (
                  <button key={o} className={answers[q.key] === o ? 'active' : ''}
                    onClick={() => updateAnswer(q.key, o)}>{o}</button>
                ))}
              </div>
            )}
            {q.type === 'multi_select' && q.options && (
              <div className="chips">
                {q.options.map(o => {
                  const selected = Array.isArray(answers[q.key]) && (answers[q.key] as string[]).includes(o)
                  return (
                    <label key={o} className={selected ? 'chip-active' : ''}>
                      <input type="checkbox" checked={selected}
                        onChange={e => {
                          const cur = Array.isArray(answers[q.key]) ? [...(answers[q.key] as string[])] : []
                          updateAnswer(q.key, e.target.checked ? [...cur, o] : cur.filter(v => v !== o))
                        }} />
                      {o}
                    </label>
                  )
                })}
              </div>
            )}
          </section>
        ))}

        <button className="submit" onClick={submit} disabled={submitting}>
          {submitting ? 'Submitting...' : 'Submit Assessment'}
        </button>

        {error && <p className="error">{error}</p>}

        {score && analytics && (
          <div className="insights">
            <div className="insights-header">
              <h2>Readiness Insights</h2>
              <code>{submissionId}</code>
            </div>
            <div className={`insights-grid${prediction?.available ? ' insights-grid--3' : ''}`}>
              <div className="card">
                <label>Score Breakdown</label>
                {Object.entries(score.sections).map(([section, data]) => (
                  <div key={section} className="section-row">
                    <span className="section-dot" style={{ background: SECTION_COLORS[section] }} />
                    <span className="section-name">{section}</span>
                    <div className="bar-track">
                      <div className="bar-fill" style={{ width: `${data.pct}%`, background: barColor(data.pct) }} />
                    </div>
                    <span className="bar-label">{data.pct}%</span>
                  </div>
                ))}
              </div>
              <div className="card">
                <label>Population ({analytics.total_submissions} submission{analytics.total_submissions !== 1 ? 's' : ''})</label>
                <div className="stat-row"><span>Have ML/AI strategy</span><strong>{analytics.strategy_adoption_pct}%</strong></div>
                <div className="stat-row"><span>Have ML CI/CD pipelines</span><strong>{analytics.ci_cd_adoption_pct}%</strong></div>
                <div className="stat-row"><span>Avg monitoring areas</span><strong>{analytics.avg_monitoring_coverage} / 5</strong></div>
                {userMonitoring !== null && (
                  <div className="stat-row comparison">
                    <span>Your monitoring vs avg</span>
                    <strong style={{ color: userMonitoring >= analytics.avg_monitoring_coverage ? '#22c55e' : '#f59e0b' }}>
                      {userMonitoring > analytics.avg_monitoring_coverage
                        ? `+${(userMonitoring - analytics.avg_monitoring_coverage).toFixed(1)} above`
                        : userMonitoring === analytics.avg_monitoring_coverage ? 'At average'
                        : `${(userMonitoring - analytics.avg_monitoring_coverage).toFixed(1)} below`}
                    </strong>
                  </div>
                )}
              </div>
              {prediction?.available && prediction.probability !== null && (
                <div className="card">
                  <label>Model Prediction</label>
                  <div className="pred-probability" style={{ color: prediction.probability >= 0.5 ? '#22c55e' : '#f59e0b' }}>
                    {Math.round(prediction.probability * 100)}%
                  </div>
                  <div className="pred-label">confidence high-readiness</div>
                  <div className="pred-bar-wrap">
                    <div className="pred-bar">
                      <div className="pred-fill" style={{
                        width: `${Math.round(prediction.probability * 100)}%`,
                        background: prediction.probability >= 0.5 ? '#22c55e' : '#f59e0b',
                      }} />
                    </div>
                  </div>
                  <div className="pred-features">
                    {prediction.contributions.slice(0, 4).map(c => (
                      <div key={c.feature} className="pred-feat-row">
                        <span className="pred-feat-name">{c.feature.replace(/_/g, ' ')}</span>
                        <span className="pred-feat-val">{c.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

// ── Dashboards view ───────────────────────────────────────────────────────────
const SUPERSET_URL = 'http://localhost:8088/dashboard/list/'

type DashPane = 'grafana' | 'superset'

function DashboardsView() {
  const [runs, setRuns]           = useState<MlRun[]>([])
  const [experiments, setExp]     = useState<MlExperiment[]>([])
  const [loading, setLoading]     = useState(true)
  const [dashPane, setDashPane]   = useState<DashPane>('grafana')

  useEffect(() => {
    Promise.all([
      axios.get<MlRun[]>(`${API}/analytics/ml-runs`),
      axios.get<MlExperiment[]>(`${API}/analytics/ml-experiments`),
    ]).then(([r, e]) => {
      setRuns(r.data); setExp(e.data)
    }).finally(() => setLoading(false))
  }, [])

  return (
    <div className="dashboards-view">
      {/* Embedded dashboard switcher */}
      <div className="card grafana-card">
        <div className="grafana-header">
          <div className="dash-switcher">
            <button className={dashPane === 'grafana'  ? 'dash-tab active' : 'dash-tab'} onClick={() => setDashPane('grafana')}>
              Grafana
            </button>
            <button className={dashPane === 'superset' ? 'dash-tab active' : 'dash-tab'} onClick={() => setDashPane('superset')}>
              Superset
            </button>
          </div>
          {dashPane === 'grafana'
            ? <a href="http://localhost:3000" target="_blank" rel="noopener noreferrer" className="open-link">Open Grafana ↗</a>
            : <a href="http://localhost:8088" target="_blank" rel="noopener noreferrer" className="open-link">Open Superset ↗</a>
          }
        </div>

        {dashPane === 'grafana' && (
          <iframe
            src={GRAFANA_URL}
            className="grafana-frame"
            title="Grafana Platform Overview"
            allowFullScreen
          />
        )}
        {dashPane === 'superset' && (
          <iframe
            src={SUPERSET_URL}
            className="grafana-frame"
            title="Superset Dashboards"
            allowFullScreen
          />
        )}
      </div>

      <div className="dash-lower">
        {/* MLflow runs */}
        <div className="card">
          <div className="grafana-header">
            <label style={{ marginBottom: 0 }}>MLflow — Recent Training Runs</label>
            <a href="http://localhost:5000" target="_blank" rel="noopener noreferrer" className="open-link">Open MLflow ↗</a>
          </div>

          {loading && <p className="dim-text">Loading...</p>}

          {!loading && experiments.length === 0 && runs.length === 0 && (
            <p className="dim-text">No ML runs logged yet — run <code>make ml-train</code> to train the readiness model.</p>
          )}

          {!loading && experiments.length > 0 && (
            <div className="exp-list">
              {experiments.map(e => (
                <div key={e.experiment_id} className="exp-row">
                  <span className="exp-badge">{e.experiment_id}</span>
                  <span className="exp-name">{e.name}</span>
                  <span className={`exp-status ${e.lifecycle_stage}`}>{e.lifecycle_stage}</span>
                </div>
              ))}
            </div>
          )}

          {!loading && runs.length > 0 && (
            <div className="runs-table-wrap">
              <table className="runs-table">
                <thead>
                  <tr><th>Run</th><th>Status</th><th>Started</th><th>Metrics</th></tr>
                </thead>
                <tbody>
                  {runs.map(r => (
                    <tr key={r.run_id}>
                      <td><code>{r.run_id}</code></td>
                      <td><span className={`run-status ${r.status.toLowerCase()}`}>{r.status}</span></td>
                      <td>{fmtTime(r.started)}</td>
                      <td className="metrics-cell">
                        {Object.entries(r.metrics).map(([k, v]) => (
                          <span key={k} className="metric-chip">{k}: {v}</span>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Tool links */}
        <div className="card">
          <label>Services</label>
          <div className="service-list">
            {TOOLS.map(t => (
              <a key={t.label} href={t.url} target="_blank" rel="noopener noreferrer"
                 className="service-row" style={{ '--tool-color': t.color } as React.CSSProperties}>
                <span className="service-dot" style={{ background: t.color }} />
                <div>
                  <div className="service-label">{t.label}</div>
                  <div className="service-desc">{t.desc}</div>
                </div>
                <span className="service-arrow">↗</span>
              </a>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── ML Studio view ────────────────────────────────────────────────────────────
const FEATURE_LABELS: Record<string, string> = {
  has_ml_strategy:           'ML Strategy documented',
  has_ci_cd:                 'CI/CD for ML pipelines',
  serving_pattern_count:     'Serving patterns (count)',
  monitoring_count:          'Monitoring areas (count)',
  experiment_tracking_score: 'Experiment tracking (0–3)',
  prod_scale_score:          'Production scale (0–3)',
}

function MlStudioView() {
  const [versions,  setVersions]  = useState<ModelVersion[]>([])
  const [featStats, setFeatStats] = useState<FeatureStats | null>(null)
  const [loading,   setLoading]   = useState(true)

  useEffect(() => {
    Promise.all([
      axios.get<ModelVersion[]>(`${API}/analytics/ml-model-versions`),
      axios.get<FeatureStats>(`${API}/analytics/feature-stats`),
    ]).then(([mv, fs]) => {
      setVersions(mv.data); setFeatStats(fs.data)
    }).finally(() => setLoading(false))
  }, [])

  const metricOrder = ['roc_auc', 'accuracy', 'f1_high', 'precision_high', 'recall_high']

  return (
    <div className="studio-view">

      {/* ── Model Registry ── */}
      <div className="studio-row">
        <div className="card studio-card">
          <div className="card-header">
            <label>Model Registry — readiness-classifier</label>
            <a href="http://localhost:5000/#/models/readiness-classifier" target="_blank" rel="noopener noreferrer" className="open-link">MLflow ↗</a>
          </div>

          {loading && <p className="dim-text">Loading...</p>}

          {!loading && versions.length === 0 && (
            <div className="empty-state">
              <p className="dim-text">No registered model versions found.</p>
              <p className="dim-text hint">Run <code>make ml-features && make ml-labels && make ml-train</code> to train and register the first version.</p>
            </div>
          )}

          {versions.map(v => (
            <div key={v.version} className="version-card">
              <div className="version-header">
                <div className="version-title">
                  <span className="version-badge">v{v.version}</span>
                  <span className="version-name">{v.name}</span>
                </div>
                <div className="version-meta">
                  <span className={`stage-chip stage-${v.stage.toLowerCase()}`}>{v.stage}</span>
                  <span className={`status-chip status-${v.status.toLowerCase()}`}>{v.status}</span>
                </div>
              </div>

              <div className="version-body">
                {/* Metrics */}
                <div className="metric-grid">
                  {metricOrder.filter(k => v.metrics[k] !== undefined).map(k => (
                    <div key={k} className="metric-tile">
                      <div className="metric-value" style={{ color: v.metrics[k] >= 0.9 ? '#22c55e' : v.metrics[k] >= 0.7 ? '#f59e0b' : '#ef4444' }}>
                        {(v.metrics[k] * 100).toFixed(1)}%
                      </div>
                      <div className="metric-key">{k.replace(/_/g, ' ')}</div>
                    </div>
                  ))}
                </div>

                {/* Params */}
                <div className="params-row">
                  {Object.entries(v.params).filter(([k]) => ['model','train_size','test_size','positive_rate'].includes(k)).map(([k, val]) => (
                    <span key={k} className="param-chip">
                      <span className="param-key">{k.replace(/_/g,' ')}</span>
                      <span className="param-val">{val}</span>
                    </span>
                  ))}
                  <span className="param-chip">
                    <span className="param-key">run</span>
                    <span className="param-val">{v.run_id}</span>
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* ── Dataset Stats ── */}
        <div className="card studio-card studio-card--narrow">
          <label>Dataset</label>
          {featStats ? (
            <>
              <div className="dataset-stat">
                <span className="ds-number">{featStats.total_submissions}</span>
                <span className="ds-label">Total submissions</span>
              </div>
              <div className="dataset-stat">
                <span className="ds-number">{featStats.labeled_submissions}</span>
                <span className="ds-label">Labeled rows</span>
              </div>
              <div className="readiness-split">
                <div className="split-bar">
                  <div className="split-fill split-high"
                    style={{ width: `${Math.round(featStats.high_readiness_rate * 100)}%` }} />
                </div>
                <div className="split-legend">
                  <span className="split-dot high" /><span>{featStats.high_readiness_n} high</span>
                  <span className="split-dot low"  /><span>{featStats.low_readiness_n} low</span>
                </div>
                <div className="split-pct">{Math.round(featStats.high_readiness_rate * 100)}% high-readiness</div>
              </div>
              <div className="label-rule">
                <span className="label-rule-title">Label rule</span>
                <code>ci_cd = 1 AND monitoring ≥ 2 AND prod_scale ≥ 2</code>
              </div>
            </>
          ) : (
            <p className="dim-text">{loading ? 'Loading...' : 'No data yet'}</p>
          )}
        </div>
      </div>

      {/* ── Feature Distributions ── */}
      <div className="card">
        <label>Feature Distributions (population mean)</label>
        {!featStats && <p className="dim-text">{loading ? 'Loading...' : 'No feature data available'}</p>}
        {featStats && (
          <div className="feat-grid">
            {Object.entries(featStats.features).map(([key, stat]) => {
              const label = FEATURE_LABELS[key] || key
              const maxVal = stat.type === 'binary' ? 1 : stat.type === 'count' ? (stat.max ?? 5) : 3
              const pct = Math.min(100, Math.round((stat.mean / maxVal) * 100))
              return (
                <div key={key} className="feat-row">
                  <div className="feat-label">{label}</div>
                  <div className="feat-bar-wrap">
                    <div className="feat-bar">
                      <div className="feat-bar-fill" style={{ width: `${pct}%`, background: pct >= 66 ? '#22c55e' : pct >= 33 ? '#f59e0b' : '#ef4444' }} />
                    </div>
                    <span className="feat-mean">
                      {stat.type === 'binary'
                        ? `${Math.round(stat.mean * 100)}% yes`
                        : stat.type === 'count'
                        ? `avg ${stat.mean} (${stat.min}–${stat.max})`
                        : `avg ${stat.mean} / ${maxVal}`}
                    </span>
                  </div>
                  {stat.distribution && (
                    <div className="dist-pills">
                      {Object.entries(stat.distribution).sort(([,a],[,b]) => b-a).map(([opt, cnt]) => (
                        <span key={opt} className="dist-pill">{opt} <strong>{cnt}</strong></span>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

    </div>
  )
}

// ── Responses view ────────────────────────────────────────────────────────────
const QUESTION_LABELS: Record<string, string> = {
  ml_strategy:         'ML/AI Strategy',
  prod_scale:          'Production Scale',
  experiment_tracking: 'Experiment Tracking',
  ci_cd_ml:            'ML CI/CD Pipelines',
  serving_patterns:    'Model Serving Patterns',
  model_monitoring:    'Production Monitoring',
}

function ResponsesView() {
  const [submissions,   setSubmissions]   = useState<SubmissionRecord[]>([])
  const [distributions, setDistributions] = useState<ResponseDistributions | null>(null)
  const [loading,       setLoading]       = useState(true)

  useEffect(() => {
    Promise.all([
      axios.get<SubmissionRecord[]>(`${API}/analytics/submissions`),
      axios.get<ResponseDistributions>(`${API}/analytics/responses/distribution`),
    ]).then(([s, d]) => {
      setSubmissions(s.data)
      setDistributions(d.data)
    }).finally(() => setLoading(false))
  }, [])

  const buckets = [
    { label: '0–19',   min: 0,  max: 19,  color: '#ef4444' },
    { label: '20–39',  min: 20, max: 39,  color: '#ef4444' },
    { label: '40–59',  min: 40, max: 59,  color: '#f59e0b' },
    { label: '60–79',  min: 60, max: 79,  color: '#22c55e' },
    { label: '80–100', min: 80, max: 100, color: '#22c55e' },
  ]
  const bucketCounts    = buckets.map(b => submissions.filter(s => s.pct >= b.min && s.pct <= b.max).length)
  const maxBucketCount  = Math.max(...bucketCounts, 1)
  const sortedSubs      = [...submissions].sort((a, b) => b.pct - a.pct)
  const avgScore        = submissions.length
    ? Math.round(submissions.reduce((sum, s) => sum + s.pct, 0) / submissions.length) : 0
  const bandCounts = {
    Advanced:   submissions.filter(s => s.band === 'Advanced').length,
    Developing: submissions.filter(s => s.band === 'Developing').length,
    Emerging:   submissions.filter(s => s.band === 'Emerging').length,
  }

  if (loading) return <div className="responses-view"><p className="dim-text">Loading...</p></div>

  if (!submissions.length) return (
    <div className="responses-view">
      <div className="card">
        <p className="dim-text">No submissions yet. Submit an assessment or run <code>make seed-bulk</code> to populate data.</p>
      </div>
    </div>
  )

  return (
    <div className="responses-view">
      <div className="resp-stats-row">
        {[
          { value: submissions.length,      label: 'Total Submissions', color: '#e2e8f0' },
          { value: `${avgScore}%`,           label: 'Average Score',     color: '#3b82f6' },
          { value: bandCounts.Advanced,      label: 'Advanced',          color: '#22c55e' },
          { value: bandCounts.Developing,    label: 'Developing',        color: '#f59e0b' },
          { value: bandCounts.Emerging,      label: 'Emerging',          color: '#ef4444' },
        ].map(s => (
          <div key={s.label} className="card resp-stat-card">
            <div className="ds-number" style={{ color: s.color }}>{s.value}</div>
            <div className="ds-label">{s.label}</div>
          </div>
        ))}
      </div>

      <div className="resp-main-row">
        <div className="card">
          <label>Score Distribution</label>
          <div className="dist-histogram">
            {buckets.map((b, i) => (
              <div key={b.label} className="hist-bar-group">
                <div className="hist-count">{bucketCounts[i]}</div>
                <div className="hist-bar-wrap">
                  <div className="hist-bar" style={{
                    height: `${Math.round((bucketCounts[i] / maxBucketCount) * 100)}%`,
                    background: b.color,
                  }} />
                </div>
                <div className="hist-label">{b.label}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="card resp-table-card">
          <label>All Submissions</label>
          <div className="resp-table-wrap">
            <table className="resp-table">
              <thead>
                <tr><th>Org</th><th>Score</th><th>Band</th><th>Submitted</th></tr>
              </thead>
              <tbody>
                {sortedSubs.map(s => (
                  <tr key={s.submission_id}>
                    <td><code className="resp-org">{s.respondent_id}</code></td>
                    <td>
                      <div className="score-cell">
                        <div className="score-mini-bar">
                          <div style={{ width: `${s.pct}%`, background: barColor(s.pct), height: '100%', borderRadius: '3px' }} />
                        </div>
                        <span style={{ color: barColor(s.pct), fontWeight: 600, fontSize: 13 }}>{s.pct}%</span>
                      </div>
                    </td>
                    <td>
                      <span className="band-chip" style={{
                        color: BAND_COLOR[s.band],
                        borderColor: BAND_COLOR[s.band] + '55',
                        background: BAND_COLOR[s.band] + '11',
                      }}>{s.band}</span>
                    </td>
                    <td className="submitted-cell">{new Date(s.submitted_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {distributions && (
        <div className="card">
          <label>Response Breakdown by Question</label>
          <div className="q-dist-grid">
            {Object.entries(distributions).map(([key, dist]) => {
              const total     = Math.max(dist.n, 1)
              const sortedOpts = Object.entries(dist.distribution).sort(([, a], [, b]) => b - a)
              return (
                <div key={key} className="q-dist-block">
                  <div className="q-dist-title">{QUESTION_LABELS[key] || key}</div>
                  {sortedOpts.map(([opt, count]) => {
                    const pct = Math.round((count / total) * 100)
                    return (
                      <div key={opt} className="q-dist-row">
                        <div className="q-dist-opt">{opt}</div>
                        <div className="q-dist-bar-wrap">
                          <div className="q-dist-bar">
                            <div className="q-dist-fill" style={{ width: `${pct}%` }} />
                          </div>
                          <span className="q-dist-pct">{pct}% <span className="q-dist-n">({count})</span></span>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Root ──────────────────────────────────────────────────────────────────────
export default function App() {
  const [tab, setTab] = useState<'assessment' | 'responses' | 'dashboards' | 'ml-studio'>('assessment')

  return (
    <div className="app-shell">
      <nav className="navbar">
        <div className="navbar-left">
          <span className="navbar-brand">ML Readiness</span>
          <div className="nav-tabs">
            <button className={tab === 'assessment' ? 'nav-tab active' : 'nav-tab'} onClick={() => setTab('assessment')}>Assessment</button>
            <button className={tab === 'responses'  ? 'nav-tab active' : 'nav-tab'} onClick={() => setTab('responses')}>Responses</button>
            <button className={tab === 'dashboards' ? 'nav-tab active' : 'nav-tab'} onClick={() => setTab('dashboards')}>Dashboards</button>
            <button className={tab === 'ml-studio'  ? 'nav-tab active' : 'nav-tab'} onClick={() => setTab('ml-studio')}>ML Studio</button>
          </div>
        </div>
        <div className="navbar-tools">
          {TOOLS.map(t => (
            <a key={t.label} href={t.url} target="_blank" rel="noopener noreferrer"
               className="tool-link" style={{ '--tool-color': t.color } as React.CSSProperties}>
              {t.label}
            </a>
          ))}
        </div>
      </nav>

      {tab === 'assessment' && <AssessmentView />}
      {tab === 'responses'  && <ResponsesView />}
      {tab === 'dashboards' && <DashboardsView />}
      {tab === 'ml-studio'  && <MlStudioView />}
    </div>
  )
}
