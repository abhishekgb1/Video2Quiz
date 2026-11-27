import React, { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'

const API = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
const LEVELS = ['easy', 'medium', 'hard']
const DEFAULT = { easy_count: 4, medium_count: 4, hard_count: 4 }
export const clock = value => `${Math.floor(Math.max(0, value || 0) / 60).toString().padStart(2, '0')}:${Math.floor(Math.max(0, value || 0) % 60).toString().padStart(2, '0')}`

async function request(path, options) {
  const response = await fetch(`${API}${path}`, options)
  const result = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = Array.isArray(result.detail) ? result.detail.map(item => item.msg).join(' ') : result.detail
    throw Error(detail || `Request failed (${response.status}).`)
  }
  return result
}
const post = body => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

let youtubeApi
function loadYouTube() {
  if (window.YT?.Player) return Promise.resolve(window.YT)
  if (!youtubeApi) youtubeApi = new Promise((resolve, reject) => {
    const prior = window.onYouTubeIframeAPIReady
    const timeout = setTimeout(() => { youtubeApi = null; reject(Error('YouTube player could not load. Try the saved video.')) }, 20000)
    window.onYouTubeIframeAPIReady = () => { clearTimeout(timeout); prior?.(); resolve(window.YT) }
    const script = document.createElement('script')
    script.src = 'https://www.youtube.com/iframe_api'
    script.onerror = () => { clearTimeout(timeout); youtubeApi = null; reject(Error('YouTube is unavailable. Try the saved video.')) }
    document.head.append(script)
  })
  return youtubeApi
}

export const VideoPlayer = forwardRef(function VideoPlayer({ video }, ref) {
  const box = useRef(null), native = useRef(null), holder = useRef(null), youtube = useRef(null)
  const pendingSeek = useRef(null), ready = useRef(false)
  const [saved, setSaved] = useState(video.source_type !== 'youtube')
  const [error, setError] = useState('')
  const [speed, setSpeed] = useState('1')
  const [time, setTime] = useState(0), [duration, setDuration] = useState(video.duration_seconds || 0)
  const isYouTube = !saved && video.source_type === 'youtube'

  const jump = seconds => {
    const value = Math.max(0, Number(seconds) || 0)
    box.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    if (isYouTube) {
      if (ready.current && youtube.current) { youtube.current.seekTo(value, true); youtube.current.playVideo() }
      else pendingSeek.current = value
    } else if (native.current) {
      if (native.current.readyState) { native.current.currentTime = value; native.current.play().catch(() => setError('Press Play to continue at the selected timestamp.')) }
      else { pendingSeek.current = value; native.current.load() }
    }
  }
  useImperativeHandle(ref, () => ({ seek: jump }))

  useEffect(() => {
    if (!isYouTube) return
    let cancelled = false
    let ticker
    setError('')
    ready.current = false
    let id
    try {
      const url = new URL(video.source_url)
      id = url.hostname.includes('youtu.be') ? url.pathname.split('/')[1] : url.searchParams.get('v') || url.pathname.split('/').filter(Boolean).at(-1)
    } catch { setError('This video has no valid YouTube source. Try the saved video.'); return }
    loadYouTube().then(YT => {
      if (cancelled || !holder.current) return
      const mount = document.createElement('div')
      holder.current.replaceChildren(mount)
      youtube.current = new YT.Player(mount, {
        videoId: id, width: '100%', height: '100%',
        playerVars: { playsinline: 1, controls: 1, origin: window.location.origin, rel: 0 },
        events: {
          onReady: () => {
            ready.current = true
            if (pendingSeek.current != null) { const value = pendingSeek.current; pendingSeek.current = null; jump(value) }
            ticker = setInterval(() => { setTime(youtube.current?.getCurrentTime?.() || 0); setDuration(youtube.current?.getDuration?.() || 0) }, 1000)
          },
          onError: event => setError(`YouTube playback is unavailable (${event.data}). Use the saved original video if available.`),
        },
      })
    }).catch(error => { if (!cancelled) setError(error.message) })
    return () => { cancelled = true; ready.current = false; clearInterval(ticker); youtube.current?.destroy?.(); youtube.current = null }
  }, [isYouTube, video.id])

  return <section className="source-player" ref={box} aria-label="Source video player">
    <div className="studio-heading"><div><span className="section-kicker">LEARN FROM THE SOURCE</span><h3>Original educational video</h3></div>{video.source_type === 'youtube' && <button className="button button-outline" onClick={() => { setSaved(value => !value); setError('') }}>{saved ? 'YouTube player' : 'Play saved video'}</button>}</div>
    <div className="video-frame">{isYouTube ? <div className="youtube-holder" ref={holder}/> : <video ref={native} src={`${API}/videos/${video.id}/media`} controls playsInline preload="metadata" aria-label="Original source video" onTimeUpdate={event => setTime(event.currentTarget.currentTime)} onLoadedMetadata={event => { setDuration(event.currentTarget.duration); if (pendingSeek.current != null) { const value = pendingSeek.current; pendingSeek.current = null; jump(value) } }} onError={() => setError('The saved source video is unavailable or cannot be played by this browser.')}/>}</div>
    <div className="player-toolbar"><span>{clock(time)} / {clock(duration)}</span><button className="button button-outline" onClick={() => jump(time - 10)}>−10 sec</button><button className="button button-outline" onClick={() => jump(time + 10)}>+10 sec</button><label>Speed <select aria-label="Playback speed" value={speed} onChange={event => { const value = event.target.value; setSpeed(value); if (isYouTube) youtube.current?.setPlaybackRate?.(Number(value)); else if (native.current) native.current.playbackRate = Number(value) }}>{[.5, .75, 1, 1.25, 1.5, 2].map(value => <option key={value} value={value}>{value}×</option>)}</select></label></div>
    {error && <p className="studio-error" role="alert">{error}</p>}
  </section>
})

export function ResultAnalysis({ result, seek }) {
  return <section className="studio-results" aria-label="Difficulty-wise results">
    <div className="studio-heading"><div><span className="section-kicker">YOUR LEARNING REPORT</span><h3>{result.score} / {result.total} · {result.percentage}%</h3></div><span>Time taken {clock(result.time_taken_seconds)}</span></div>
    <div className="studio-metrics"><span>Correct <b>{result.score}</b></span><span>Incorrect <b>{result.incorrect}</b></span><span>Unanswered <b>{result.unanswered}</b></span></div>
    {LEVELS.map(level => { const data = result.difficulty_performance?.[level] || { total: 0, correct: 0 }; return <div className={`level-performance ${level}`} key={level}><label>{level}<span>{data.correct} / {data.total}</span></label><progress aria-label={`${level} performance`} value={data.correct} max={data.total || 1}/></div> })}
    <p>{result.feedback}</p>
    <details><summary>Review incorrect and unanswered questions</summary>{result.results.filter(item => !item.correct).map(item => <article className="review-item" key={item.question_id}><h4>{item.question}</h4><p>Your answer: {item.selected_answer ?? 'Unanswered'}</p><p><strong>Correct answer: {item.correct_answer}</strong></p><p>{item.explanation}</p>{item.evidence && <blockquote>{item.evidence}</blockquote>}{item.timestamp_seconds != null && seek && <button className="text-button" onClick={() => seek(item.timestamp_seconds)}>Watch Explanation · {clock(item.timestamp_seconds)}</button>}</article>)}</details>
  </section>
}

const QuizStudio = forwardRef(function QuizStudio({ video, onAttemptSaved }, ref) {
  const [settings, setSettings] = useState({ max_questions: 60, ai_configured: false })
  const [counts, setCounts] = useState(DEFAULT), [generationMode, setGenerationMode] = useState('default')
  const [quiz, setQuiz] = useState(null), [versions, setVersions] = useState([]), [version, setVersion] = useState('')
  const [transcript, setTranscript] = useState(null), [job, setJob] = useState(null)
  const [loading, setLoading] = useState(true), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const [filter, setFilter] = useState('all'), [index, setIndex] = useState(0)
  const [mode, setMode] = useState('practice'), [minutes, setMinutes] = useState(36)
  const [attempt, setAttempt] = useState(null), [answers, setAnswers] = useState({}), [feedback, setFeedback] = useState({})
  const [result, setResult] = useState(null), [remaining, setRemaining] = useState(0), [retryLocked, setRetryLocked] = useState(false)
  const player = useRef(null), pendingPayload = useRef(null), submitting = useRef(false), answersRef = useRef({}), submitRef = useRef(null), alive = useRef(true)
  const running = ['queued', 'running'].includes(job?.status)
  const active = attempt && !result
  const total = Object.values(counts).reduce((sum, value) => sum + value, 0)
  const questions = quiz?.questions || []
  const filtered = questions.filter(question => filter === 'all' || question.difficulty === filter)
  const question = filtered[Math.min(index, Math.max(0, filtered.length - 1))]
  const answered = questions.filter(q => answers[q.id] != null).length
  const checked = result?.results || Object.values(feedback)
  const correct = checked.filter(item => item.correct).length
  const incorrect = checked.filter(item => !item.correct && item.selected_answer != null).length
  const validation = total < 1 ? 'Select at least one question.' : total > settings.max_questions ? `Maximum ${settings.max_questions} questions.` : ''

  async function loadQuiz(selectedVersion) {
    const next = await request(`/videos/${video.id}/quiz${selectedVersion ? `?version=${selectedVersion}` : ''}`)
    if (!alive.current) return
    setQuiz(next); setVersion(String(next.quiz_version || '')); setFilter('all'); setIndex(0)
    setVersions(await request(`/videos/${video.id}/versions`))
  }

  useEffect(() => {
    alive.current = true
    const controller = new AbortController()
    async function load() {
      setLoading(true)
      try {
        const results = await Promise.allSettled([
          request('/videos/quiz-settings', { signal: controller.signal }),
          request(`/videos/${video.id}/generations`, { signal: controller.signal }),
          request(`/videos/${video.id}/transcript`, { signal: controller.signal }),
          request(`/videos/${video.id}/quiz`, { signal: controller.signal }),
          request(`/videos/${video.id}/versions`, { signal: controller.signal }),
        ])
        if (!alive.current || controller.signal.aborted) return
        const [config, history, source, stored, available] = results
        if (config.status === 'fulfilled') setSettings(config.value)
        if (history.status === 'fulfilled') setJob(history.value[0] || null)
        if (source.status === 'fulfilled') setTranscript(source.value)
        if (stored.status === 'fulfilled') { setQuiz(stored.value); setVersion(String(stored.value.quiz_version || '')) }
        else if (['completed', 'completed_no_speech', 'ready_for_quiz'].includes(video.status)) setError(stored.reason.message)
        if (available.status === 'fulfilled') setVersions(available.value)
      } catch (error) { if (!controller.signal.aborted && alive.current) setError(error.message) }
      finally { if (alive.current) setLoading(false) }
    }
    load()
    return () => { alive.current = false; controller.abort() }
  }, [video.id, video.status])

  useEffect(() => {
    if (!running) return
    let cancelled = false, timer
    async function poll() {
      try {
        const next = await request(`/videos/generations/${job.id}`)
        if (cancelled) return
        setJob(next)
        if (next.status === 'completed') { await loadQuiz(next.quiz_version); setError('') }
        else if (['queued', 'running'].includes(next.status)) timer = setTimeout(poll, 1200)
      } catch (error) { if (!cancelled) { setError(error.message); timer = setTimeout(poll, 3000) } }
    }
    timer = setTimeout(poll, 500)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [job?.id, running])

  useEffect(() => {
    if (!active || !attempt.expires_at) return
    const deadline = new Date(attempt.expires_at + (/[Z+]/.test(attempt.expires_at) ? '' : 'Z')).getTime()
    const tick = () => { const seconds = Math.max(0, Math.ceil((deadline - Date.now()) / 1000)); setRemaining(seconds); if (!seconds && !submitting.current) submitRef.current?.() }
    tick(); const timer = setInterval(tick, 1000)
    return () => clearInterval(timer)
  }, [attempt?.attempt_id, active])

  async function generate() {
    if (validation || running || active) return
    setBusy(true); setError('')
    try { setJob(await request(`/videos/${video.id}/generate`, post({ ...counts, question_generation_mode: generationMode }))) }
    catch (error) { setError(error.message) }
    finally { setBusy(false) }
  }

  async function start(preservePosition = false) {
    setBusy(true); setError('')
    try {
      const next = await request(`/videos/${video.id}/attempts`, post({ idempotency_key: crypto.randomUUID(), mode, quiz_version: quiz.quiz_version, ...(mode === 'exam' ? { time_limit_seconds: Number(minutes) * 60 } : {}) }))
      setAttempt(next); setQuiz(current => ({ ...current, questions: next.questions })); setAnswers({}); answersRef.current = {}; setFeedback({}); setResult(null); if (!preservePosition) { setIndex(0); setFilter('all') } setRetryLocked(false); pendingPayload.current = null
      return next
    } catch (error) { setError(error.message) }
    finally { setBusy(false) }
  }

  async function choose(option) {
    if (busy || retryLocked || result || (!active && mode !== 'practice')) return
    const id = question.id
    const session = attempt || await start(true)
    if (!session) return
    const next = { ...answersRef.current, [id]: option }
    answersRef.current = next; setAnswers(next)
    if (session.mode === 'practice') {
      try {
        const checked = await request(`/videos/attempts/${session.attempt_id}/practice/${id}`, post({ answer: option }))
        if (alive.current && answersRef.current[id] === option) setFeedback(current => ({ ...current, [id]: checked }))
      } catch (error) { setError(error.message) }
    }
  }

  async function submit() {
    if (submitting.current || !attempt || result) return
    submitting.current = true; setBusy(true); setError('')
    pendingPayload.current ||= { answers: { ...answersRef.current } }
    try {
      const evaluated = await request(`/videos/attempts/${attempt.attempt_id}/submit`, post(pendingPayload.current))
      setResult(evaluated); setRetryLocked(false); pendingPayload.current = null; onAttemptSaved?.()
    } catch (error) { setRetryLocked(true); setError(`${error.message} Your submission is locked for a safe retry.`) }
    finally { submitting.current = false; setBusy(false) }
  }
  submitRef.current = submit

  function retake() { setAttempt(null); setResult(null); setAnswers({}); answersRef.current = {}; setFeedback({}); setRetryLocked(false); pendingPayload.current = null; setIndex(0) }
  const currentFeedback = result?.results.find(item => item.question_id === question?.id) || feedback[question?.id]
  const seek = seconds => player.current?.seek(seconds)
  useImperativeHandle(ref, () => ({ seek }))

  return <section className="panel quiz-panel studio" aria-labelledby="quiz-heading">
    <div className="section-heading"><div><span className="section-kicker">VIDEO #{video.id} · STUDY SPACE</span><h2 id="quiz-heading">Quiz dashboard</h2><p>{video.original_filename || video.stored_filename}</p></div>{quiz?.quiz_version && <span className="version-tag">VERSION {quiz.quiz_version}</span>}</div>
    <VideoPlayer video={video} ref={player}/>
    <section className="quiz-configuration" aria-label="Quiz Configuration">
      <div className="studio-heading"><div><h3>Quiz Configuration</h3><p>Choose your mix of recall, understanding, and analysis.</p></div><strong className="total-count">{total} <small>questions</small></strong></div>
      <div className="studio-tabs" role="group" aria-label="Generation mode">{['default', 'custom'].map(value => <button key={value} className={generationMode === value ? 'selected' : ''} disabled={Boolean(active) || running} onClick={() => { setGenerationMode(value); if (value === 'default') setCounts(DEFAULT) }}>{value === 'default' ? 'Default Quiz' : 'Custom Quiz'}</button>)}</div>
      <div className="count-grid">{LEVELS.map(level => <label className={`count-card ${level}`} key={level}><span>{level}<small>{level === 'easy' ? 'Recall & definitions' : level === 'medium' ? 'Apply & compare' : 'Analyze & reason'}</small></span><input aria-label={`${level} question count`} type="number" min="0" max={settings.max_questions} step="1" value={counts[`${level}_count`]} disabled={generationMode === 'default' || Boolean(active) || running} onChange={event => { const value = Number(event.target.value); setCounts(current => ({ ...current, [`${level}_count`]: Number.isFinite(value) ? Math.max(0, Math.floor(value)) : 0 })) }}/></label>)}</div>
      <p className="studio-muted">Maximum {settings.max_questions} questions. {settings.ai_configured ? 'Structured AI generation is configured; validated fallback is reported when used.' : 'No AI model configured. The baseline supports Easy recall only; Medium and Hard requests require a configured Ollama model.'} Visual analysis is not available for this video.</p>
      {validation && <p className="studio-error" role="alert">{validation}</p>}
      <div className="studio-actions"><button className="button button-primary" disabled={busy || running || Boolean(active) || Boolean(validation) || !transcript} onClick={generate}>Generate Quiz</button><button className="button button-outline" disabled={busy || running || Boolean(active)} onClick={() => { setGenerationMode('default'); setCounts(DEFAULT) }}>Reset to Default</button><button className="button button-outline" disabled={busy || running || Boolean(active) || !quiz?.questions?.length || Boolean(validation)} onClick={generate}>Regenerate Quiz</button></div>
      {job && <div className={`generation-status ${job.status}`} role="status"><strong>{job.status.replaceAll('_', ' ')}</strong>{running && <progress aria-label="Quiz generation progress" max="100" value={job.progress}/>}<p>{job.message || 'Waiting for a generation worker.'}</p>{job.generation_method && <small>Method: {job.generation_method}</small>}</div>}
    </section>
    {error && <p className="studio-error" role="alert">{error}</p>}
    {loading && <p role="status">Loading study workspace…</p>}
    {!!questions.length && <>
      <div className="studio-heading"><h3>Your quiz</h3><label>Saved version <select aria-label="Quiz version" disabled={Boolean(active) || running} value={version} onChange={event => { retake(); loadQuiz(event.target.value).catch(error => setError(error.message)) }}>{versions.map(item => <option key={item.quiz_version} value={item.quiz_version}>v{item.quiz_version} · {item.total_questions} questions</option>)}</select></label></div>
      <p className="studio-muted">Generation method: {quiz.generation_method || 'baseline'}{quiz.configuration?.message ? ` · ${quiz.configuration.message}` : ''}</p>
      <div className="studio-metrics"><span>Total <b>{questions.length}</b></span>{LEVELS.map(level => <span className={level} key={level}>{level}<b>{questions.filter(q => q.difficulty === level).length}</b></span>)}<span>Attempted <b>{answered}</b></span><span>Remaining <b>{questions.length - answered}</b></span><span>Correct <b>{active && attempt.mode === 'exam' ? '—' : correct}</b></span><span>Incorrect <b>{active && attempt.mode === 'exam' ? '—' : incorrect}</b></span></div>
      <div className="quiz-progress"><label>Quiz progress <strong>{Math.round(answered / questions.length * 100)}%</strong></label><progress aria-label="Quiz progress" max={questions.length} value={answered}/></div>
      {!attempt && <div className="session-setup"><label>Session <select aria-label="Quiz session mode" value={mode} onChange={event => setMode(event.target.value)}><option value="practice">Practice · instant feedback</option><option value="exam">Timed examination</option></select></label>{mode === 'exam' && <label>Minutes <input type="number" aria-label="Exam time limit in minutes" min="1" max="240" value={minutes} onChange={event => setMinutes(event.target.value)}/></label>}<button className="button button-primary" disabled={busy || running || (mode === 'exam' && (!Number.isInteger(Number(minutes)) || minutes < 1 || minutes > 240))} onClick={() => start()}>{mode === 'exam' ? 'Start exam' : 'Start practice'}</button></div>}
      {!attempt && mode === 'practice' && <p className="studio-muted">Select an answer to start practice automatically, or use Start practice. For a timed exam, choose Timed examination and Start exam.</p>}
      {active && <div className="exam-banner"><strong>{attempt.mode === 'exam' ? 'Timed exam · feedback after submission' : 'Practice · explanations after each answer'}</strong>{attempt.expires_at && <span className="exam-timer" role="timer">Time left {clock(remaining)}</span>}</div>}
      <div className="studio-tabs" role="tablist" aria-label="Difficulty filters">{['all', ...LEVELS].map(level => <button role="tab" aria-selected={filter === level} className={`${level} ${filter === level ? 'selected' : ''}`} key={level} onClick={() => { setFilter(level); setIndex(0) }}>{level === 'all' ? 'All Questions' : level}</button>)}</div>
      <div className="question-workspace"><nav className="question-navigator" aria-label="Question navigation">{questions.map((q, i) => <button className={`${answers[q.id] != null ? 'answered' : 'unanswered'} ${question?.id === q.id ? 'current' : ''}`} aria-label={`Question ${i + 1}, ${answers[q.id] != null ? 'answered' : 'unanswered'}`} aria-current={question?.id === q.id ? 'step' : undefined} key={q.id} onClick={() => { setFilter('all'); setIndex(i) }}>{i + 1}</button>)}</nav>
        {question ? <article className="question-card studio-question"><div className="question-meta"><span>QUESTION {questions.indexOf(question) + 1} OF {questions.length}</span><span className={`difficulty-tag ${question.difficulty}`}>{question.difficulty}</span></div><h3>{question.question}</h3>{question.timestamp_seconds != null && <div className="timestamp-actions"><button className="text-button" onClick={() => seek(question.timestamp_seconds)}>Source: {clock(question.timestamp_seconds)}</button><button className="text-button" onClick={() => seek(question.timestamp_seconds)}>Watch Explanation</button></div>}
          <div className="answer-options">{question.options.map((option, i) => <label className="answer-option" key={option}><input type="radio" name={`studio-question-${question.id}`} value={option} checked={answers[question.id] === option} disabled={Boolean(result) || (!active && mode !== 'practice') || busy || retryLocked} onChange={() => choose(option)}/><span className="option-letter">{String.fromCharCode(65 + i)}</span><span>{option}</span></label>)}</div>
          {currentFeedback && <div className={`answer-feedback ${currentFeedback.correct ? 'positive' : 'negative'}`}><strong>{currentFeedback.correct ? 'Correct answer' : currentFeedback.selected_answer == null ? 'Unanswered' : 'Review this answer'}</strong><p>Correct answer: {currentFeedback.correct_answer}</p><p>{currentFeedback.explanation}</p>{currentFeedback.evidence && <blockquote>{currentFeedback.evidence}</blockquote>}{question.timestamp_seconds != null && <button className="text-button" onClick={() => seek(question.timestamp_seconds)}>Watch Explanation · {clock(question.timestamp_seconds)}</button>}</div>}
        </article> : <p>No questions at this difficulty in this quiz version.</p>}
      </div>
      <div className="studio-actions question-actions"><button className="button button-outline" disabled={index <= 0} onClick={() => setIndex(value => Math.max(0, value - 1))}>Previous Question</button><button className="button button-outline" disabled={index >= filtered.length - 1} onClick={() => setIndex(value => value + 1)}>Next Question</button>{active && <button className="button button-primary" disabled={busy} onClick={submit}>{retryLocked ? 'Retry submission' : 'Submit Quiz'}</button>}</div>
      {result && <><ResultAnalysis result={result} seek={seek}/><button className="button button-primary" onClick={retake}>Retake Quiz</button></>}
    </>}
    {!loading && !questions.length && <p className="studio-muted">No saved quiz yet. Configure question counts above after the transcript is ready.</p>}
    {transcript && <details className="transcript-details"><summary>Source transcript · {transcript.segments.length} timestamped segments</summary><div className="transcript-segments">{transcript.segments.map((segment, i) => <p key={i}><button className="text-button" onClick={() => seek(segment.start)}>{clock(segment.start)}</button> {segment.text}</p>)}</div></details>}
  </section>
})

export default QuizStudio
