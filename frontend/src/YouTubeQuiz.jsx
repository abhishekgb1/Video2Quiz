import React, { useEffect, useRef, useState } from 'react'
import QuizStudio, { ResultAnalysis } from './QuizStudio'

const API = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
export function RightsNotice() {
  return <p className="studio-muted">Video2Quiz supports authorized educational content. YouTube videos are opened on YouTube and are not downloaded by this application. <a href="https://www.youtube.com/t/terms" target="_blank" rel="noopener noreferrer">YouTube Terms of Service</a> · <a href="https://developers.google.com/youtube/terms/developer-policies" target="_blank" rel="noopener noreferrer">Developer policies</a></p>
}
export function PermissionCheckbox({ checked, onChange }) {
  return <label className="permission-confirmation"><input type="checkbox" checked={checked} onChange={event => onChange(event.target.checked)}/> I confirm that I own this content or have the necessary rights and permissions to process it for quiz generation.</label>
}
export function youtubeURL(value) {
  try {
    const url = new URL(value.trim())
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password || !['youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be', 'www.youtu.be'].includes(url.hostname)) return null
    const parts = url.pathname.replace(/^\/+|\/+$/g, '').split('/')
    const id = url.hostname.endsWith('youtu.be') ? parts[0] : url.pathname === '/watch' ? url.searchParams.get('v') : parts.length === 2 && ['shorts', 'embed'].includes(parts[0]) ? parts[1] : null
    return /^[A-Za-z0-9_-]{11}$/.test(id || '') ? `https://www.youtube.com/watch?v=${id}` : null
  } catch { return null }
}
async function api(path, options) {
  const response = await fetch(API + path, options)
  const data = await response.json()
  if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Check your input and try again.')
  return data
}
export default function YouTubeQuiz() {
  const [url, setURL] = useState(''), [text, setText] = useState(''), [file, setFile] = useState(null)
  const [inputMode, setInputMode] = useState('paste'), [rights, setRights] = useState(false), [busy, setBusy] = useState(false)
  const [error, setError] = useState(''), [videos, setVideos] = useState([]), [selected, setSelected] = useState(null)
  const [history, setHistory] = useState([]), [result, setResult] = useState(null)
  const studio = useRef(null)
  const link = youtubeURL(url)
  async function refresh() {
    try { setVideos((await api('/videos?source_type=youtube')).filter(video => video.source_type === 'youtube')) }
    catch (error) { setError(error.message) }
  }
  async function loadHistory(id) {
    try { setHistory(await api(`/videos/${id}/attempts`)) } catch (error) { setError(error.message) }
  }
  useEffect(() => { refresh() }, [])
  useEffect(() => { setHistory([]); setResult(null); if (selected) loadHistory(selected.id) }, [selected?.id])
  async function importTranscript() {
    if (!link || !rights) return
    setBusy(true); setError('')
    const body = new FormData()
    body.append('url', link); body.append('rights_confirmed', 'true')
    if (inputMode === 'file' && file) body.append('file', file)
    else body.append('text', text)
    try { const video = await api('/videos/youtube/transcript', { method: 'POST', body }); setSelected(video); await refresh() }
    catch (error) { setError(error.message) }
    finally { setBusy(false) }
  }
  return <section className="panel youtube-workspace" id="youtube-quiz" aria-label="YouTube Quiz">
    <div className="section-heading"><div><span className="section-kicker">AUTHORIZED TRANSCRIPTS</span><h2>YouTube Quiz</h2><p>Open the video on YouTube, then supply a transcript you have permission to process.</p></div></div>
    <RightsNotice/>
    <label className="transcript-input">YouTube video URL<input aria-label="YouTube video URL" value={url} onChange={event => setURL(event.target.value)} placeholder="YouTube watch, youtu.be or Shorts URL"/></label>
    {url && !link && <p className="studio-error" role="alert">Enter a valid YouTube video URL.</p>}
    {link && <a className="button button-outline" href={link} target="_blank" rel="noopener noreferrer">Open on YouTube ↗</a>}
    <div className="studio-tabs" role="group" aria-label="Transcript input method"><button className={inputMode === 'paste' ? 'selected' : ''} onClick={() => setInputMode('paste')}>Paste Transcript</button><button className={inputMode === 'file' ? 'selected' : ''} onClick={() => setInputMode('file')}>Upload Transcript</button></div>
    {inputMode === 'paste' ? <label className="transcript-input">Authorized transcript<textarea aria-label="Authorized transcript" rows="8" maxLength="200000" value={text} onChange={event => setText(event.target.value)} placeholder="Paste educational content you own or have permission to process. Plain text has no source timestamps."/></label> : <label className="transcript-input">TXT, SRT or VTT file (UTF-8, up to 1 MB)<input aria-label="Transcript file" type="file" accept=".txt,.srt,.vtt" onChange={event => setFile(event.target.files?.[0] || null)}/></label>}
    <PermissionCheckbox checked={rights} onChange={setRights}/>
    <button className="button button-primary" disabled={busy || !rights || !link || (inputMode === 'file' ? !file : !text.trim())} onClick={importTranscript}>{busy ? 'Importing transcript…' : 'Use transcript for quiz'}</button>
    {error && <p className="studio-error" role="alert">{error}</p>}
    <h3>Saved YouTube quizzes</h3><button className="button button-outline" onClick={refresh}>Refresh YouTube quizzes</button>
    <div className="youtube-library">{videos.map(video => <button className="button button-outline" key={video.id} onClick={() => { setSelected(video); setURL(video.source_url || ''); setError('') }}>#{video.id} · {video.original_filename || 'YouTube quiz'} · {video.status === 'failed' ? 'Provide an authorized transcript' : video.status.replaceAll('_', ' ')}</button>)}</div>
    {selected && <><QuizStudio key={selected.id} ref={studio} video={selected} onAttemptSaved={() => loadHistory(selected.id)}/><h3>YouTube quiz history</h3>{history.map(attempt => <button className="button button-outline" key={attempt.attempt_id} onClick={async () => { try { setResult(await api(`/videos/attempts/${attempt.attempt_id}`)) } catch (error) { setError(error.message) } }}>Attempt #{attempt.attempt_id} · {attempt.status}</button>)}{result && <ResultAnalysis result={result} seek={seconds => studio.current?.seek(seconds)}/>}</>}
  </section>
}
