import { useMemo, useState } from 'react'
import axios from 'axios'

type AnswerValue = string | number | boolean | string[]

const templateId = 'seed-after-running-make-seed'

const questions = [
  { section: 'Strategy', key: 'ai_strategy', prompt: 'Do you have an AI strategy?', type: 'boolean' },
  { section: 'Platform', key: 'streaming_stack', prompt: 'Which streaming stack do you use?', type: 'single_select', options: ['Kafka', 'Redpanda', 'Other'] },
  { section: 'Maturity', key: 'ml_maturity', prompt: 'Rate your ML maturity from 1 to 5', type: 'rating' },
  { section: 'Observability', key: 'obs_tools', prompt: 'Which observability tools do you use?', type: 'multi_select', options: ['Grafana', 'Superset', 'Prometheus', 'OpenTelemetry'] },
  { section: 'Comments', key: 'notes', prompt: 'Anything else to capture?', type: 'text' },
]

export default function App() {
  const [respondentId, setRespondentId] = useState('org-001')
  const [answers, setAnswers] = useState<Record<string, AnswerValue>>({})
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<string>('')

  const completion = useMemo(() => Object.keys(answers).length / questions.length, [answers])

  async function submit() {
    setSubmitting(true)
    setResult('')
    try {
      const payload = {
        template_id: templateId,
        respondent_id: respondentId,
        channel: 'virtual',
        metadata_json: { source: 'react-ui' },
        answers: questions.map((q) => ({
          question_key: q.key,
          answer_text: typeof answers[q.key] === 'string' ? answers[q.key] : null,
          answer_numeric: typeof answers[q.key] === 'number' ? answers[q.key] : null,
          answer_json: Array.isArray(answers[q.key]) || typeof answers[q.key] === 'boolean' ? { value: answers[q.key] } : null,
        })),
      }
      const { data } = await axios.post('http://localhost:8000/submissions', payload)
      setResult(`Submitted successfully: ${data.submission_id}`)
    } catch (error) {
      setResult('Submission failed. Ensure the API is running and replace templateId with the seeded template id.')
    } finally {
      setSubmitting(false)
    }
  }

  function updateAnswer(key: string, value: AnswerValue) {
    setAnswers((current) => ({ ...current, [key]: value }))
  }

  return (
    <div className="page">
      <aside className="sidebar">
        <h1>Assessment Framework</h1>
        <p>Virtual submission layer for configurable assessments.</p>
        <div className="card">
          <label>Respondent ID</label>
          <input value={respondentId} onChange={(e) => setRespondentId(e.target.value)} />
          <label>Completion</label>
          <progress max={1} value={completion}></progress>
          <span>{Math.round(completion * 100)}%</span>
        </div>
      </aside>
      <main className="content">
        {questions.map((q) => (
          <section className="card" key={q.key}>
            <small>{q.section}</small>
            <h2>{q.prompt}</h2>
            {q.type === 'text' && (
              <textarea onChange={(e) => updateAnswer(q.key, e.target.value)} rows={4} />
            )}
            {q.type === 'rating' && (
              <input type="number" min={1} max={5} onChange={(e) => updateAnswer(q.key, Number(e.target.value))} />
            )}
            {q.type === 'boolean' && (
              <div className="inline">
                <button onClick={() => updateAnswer(q.key, true)}>Yes</button>
                <button onClick={() => updateAnswer(q.key, false)}>No</button>
              </div>
            )}
            {q.type === 'single_select' && q.options && (
              <select onChange={(e) => updateAnswer(q.key, e.target.value)}>
                <option>Select</option>
                {q.options.map((option) => <option key={option}>{option}</option>)}
              </select>
            )}
            {q.type === 'multi_select' && q.options && (
              <div className="chips">
                {q.options.map((option) => (
                  <label key={option}>
                    <input
                      type="checkbox"
                      onChange={(e) => {
                        const current = Array.isArray(answers[q.key]) ? [...answers[q.key] as string[]] : []
                        const next = e.target.checked ? [...current, option] : current.filter((v) => v !== option)
                        updateAnswer(q.key, next)
                      }}
                    />
                    {option}
                  </label>
                ))}
              </div>
            )}
          </section>
        ))}
        <button className="submit" onClick={submit} disabled={submitting}>{submitting ? 'Submitting...' : 'Submit assessment'}</button>
        {result && <p>{result}</p>}
      </main>
    </div>
  )
}
