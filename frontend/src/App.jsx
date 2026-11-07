import { useState, useEffect, useCallback, useRef } from 'react'

const API = ''

export default function App() {
  const [sessions, setSessions] = useState([])
  const [sessionDetail, setSessionDetail] = useState(null)
  const [visits, setVisits] = useState([])
  const [sharers, setSharers] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [copied, setCopied] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  // Read session from URL on load
  const urlParams = new URLSearchParams(window.location.search)
  const initialSession = urlParams.get('session')
  const [view, setView] = useState(initialSession ? 'detail' : 'list')
  const [activeSessionId, setActiveSessionId] = useState(initialSession)
  const [deleteConfirm, setDeleteConfirm] = useState(null) // session id to delete
  const pollRef = useRef(null)

  // Form state
  const [teacherName, setTeacherName] = useState('')
  const [meetUrl, setMeetUrl] = useState('')
  const [emailTemplate, setEmailTemplate] = useState(
    'Hi everyone,\n\nJoin today\'s class here: {{LINK}}\n\nSee you at 10 AM!\n\n— Teacher'
  )
  const [emailsText, setEmailsText] = useState('')
  const [emails, setEmails] = useState([])

  // Fetch all sessions
  const fetchSessions = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/sessions`)
      if (res.ok) {
        const data = await res.json()
        setSessions(data.sessions || [])
      }
    } catch (e) { /* silent */ }
  }, [])

  useEffect(() => {
    fetchSessions()
  }, [fetchSessions])

  // Parse emails from textarea
  const parseEmails = (text) =>
    text.split(/[\n,;]+/).map((e) => e.trim().toLowerCase()).filter((e) => e && e.includes('@'))

  const handleEmailsTextChange = (val) => {
    setEmailsText(val)
    setEmails(parseEmails(val))
  }

  const handleFileUpload = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await fetch(`${API}/api/upload-emails`, { method: 'POST', body: formData })
      const data = await res.json()
      if (data.emails) {
        const merged = [...new Set([...emails, ...data.emails])]
        setEmails(merged)
        setEmailsText(merged.join('\n'))
        setSuccess(`Loaded ${data.count} emails from file`)
        setTimeout(() => setSuccess(''), 3000)
      }
    } catch (err) {
      setError('Failed to parse file')
    }
    e.target.value = ''
  }

  // Start new session
  const startSession = async () => {
    setError('')
    setSuccess('')
    const parsedEmails = emails.length > 0 ? emails : parseEmails(emailsText)
    if (!teacherName.trim()) { setError('Teacher name is required'); return }
    if (!meetUrl.trim()) { setError('Meet URL is required'); return }
    if (parsedEmails.length === 0) { setError('Add at least one student email'); return }
    if (!emailTemplate.includes('{{LINK}}')) {
      setError('Email template must contain {{LINK}} placeholder')
      return
    }

    setLoading(true)
    try {
      const res = await fetch(`${API}/api/session/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          teacher_name: teacherName.trim(),
          meet_url: meetUrl.trim(),
          email_template: emailTemplate,
          emails: parsedEmails,
        }),
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.detail || 'Failed to start session')
        return
      }
      setActiveSessionId(data.session_id)
      setView('detail')
      // Update URL so refresh keeps the session
      const url = new URL(window.location.href)
      url.searchParams.set('session', data.session_id)
      window.history.replaceState({}, '', url.toString())
      setSuccess(`✅ ${data.sent} of ${data.student_count} emails sent successfully!`)
      if (data.failed > 0) {
        setError(`⚠️ ${data.failed} emails failed: ${data.errors.join(', ')}`)
      }
      fetchSessions()
    } catch (err) {
      setError('Network error: ' + err.message)
    } finally {
      setLoading(false)
    }
  }

  // Fetch session detail + visits
  const fetchSessionDetail = useCallback(async (sid) => {
    if (!sid) return
    try {
      const [detailRes, visitsRes] = await Promise.all([
        fetch(`${API}/api/session/${sid}`),
        fetch(`${API}/api/session/${sid}/visits`),
      ])
      if (detailRes.ok) {
        setSessionDetail(await detailRes.json())
      } else {
        // Session not found (deleted) - go back to list
        setActiveSessionId(null)
        setView('list')
        const url = new URL(window.location.href)
        url.searchParams.delete('session')
        window.history.replaceState({}, '', url.toString())
      }
      if (visitsRes.ok) {
        const vd = await visitsRes.json()
        setVisits(vd.visits || [])
        setSharers(vd.sharers || [])
      }
    } catch (e) { /* silent */ }
  }, [])

  useEffect(() => {
    if (activeSessionId && view === 'detail') {
      fetchSessionDetail(activeSessionId)
      pollRef.current = setInterval(() => fetchSessionDetail(activeSessionId), 3000)
      return () => clearInterval(pollRef.current)
    }
  }, [activeSessionId, view, fetchSessionDetail])

  // Delete session
  const deleteSession = async (sid) => {
    setDeleteConfirm(sid)
  }

  const confirmDelete = async () => {
    const sid = deleteConfirm
    setDeleteConfirm(null)
    try {
      const res = await fetch(`${API}/api/session/${sid}`, {
        method: 'DELETE',
      })
      if (res.ok) {
        if (activeSessionId === sid) {
          setActiveSessionId(null)
          setSessionDetail(null)
          setVisits([])
          setSharers([])
          setView('list')
          // Clear session from URL
          const url = new URL(window.location.href)
          url.searchParams.delete('session')
          window.history.replaceState({}, '', url.toString())
        }
        fetchSessions()
        setSuccess('Session deleted')
        setTimeout(() => setSuccess(''), 3000)
      } else {
        const d = await res.json()
        setError(d.detail || 'Delete failed')
      }
    } catch (e) {
      setError('Delete failed')
    }
  }

  const selectSession = (sid) => {
    setActiveSessionId(sid)
    setView('detail')
    setSidebarOpen(false)
    // Update URL so refresh keeps the session
    const url = new URL(window.location.href)
    url.searchParams.set('session', sid)
    window.history.replaceState({}, '', url.toString())
  }

  const newSession = () => {
    setActiveSessionId(null)
    setSessionDetail(null)
    setVisits([])
    setSharers([])
    setTeacherName('')
    setMeetUrl('')
    setEmailsText('')
    setEmails([])
    setView('new')
    setSidebarOpen(false)
    // Clear session from URL
    const url = new URL(window.location.href)
    url.searchParams.delete('session')
    window.history.replaceState({}, '', url.toString())
  }

  const copyDashboardUrl = (sid) => {
    const url = `${window.location.origin}/dashboard?session=${sid || activeSessionId}`
    navigator.clipboard.writeText(url).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  const formatTime = (ts) => {
    try { return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) }
    catch { return ts }
  }

  const formatDate = (ts) => {
    try { return new Date(ts).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }
    catch { return ts }
  }

  return (
    <div className="app-layout">
      {/* Mobile sidebar toggle */}
      <button className="sidebar-toggle" onClick={() => setSidebarOpen(!sidebarOpen)}>
        {sidebarOpen ? '✕' : '☰'}
      </button>

      {/* Sidebar */}
      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-header">
          <div className="sidebar-brand">
            <div className="sidebar-brand-icon">C</div>
            <span className="sidebar-brand-text">ClassLink</span>
          </div>
          <button className="btn btn-small" onClick={newSession}>+ New</button>
        </div>
        <div className="session-list">
          {sessions.length === 0 && (
            <p className="empty-sidebar">No sessions yet. Create one!</p>
          )}
          {sessions.map((s) => (
            <div
              key={s.id}
              className={`session-item ${activeSessionId === s.id ? 'active' : ''}`}
              onClick={() => selectSession(s.id)}
            >
              <div className="session-item-name">{s.teacher_name}</div>
              <div className="session-item-meta">
                {formatDate(s.created_at)} • {s.student_count} students • {s.visit_count} visits
              </div>
              <button
                className="session-delete-btn"
                onClick={(e) => { e.stopPropagation(); deleteSession(s.id) }}
                title="Delete"
              >🗑</button>
            </div>
          ))}
        </div>
      </aside>

      {/* Overlay for mobile */}
      {sidebarOpen && <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)} />}

      {/* Main content */}
      <main className="main-content">
        <header className="header">
          <h1>Class Link Tracker</h1>
          <p className="subtitle">Find who shared your class link</p>
        </header>

        {error && <div className="alert alert-error">{error}</div>}
        {success && <div className="alert alert-success">{success}</div>}

        {view === 'new' && (
          <div className="card">
            <h2>Start a New Session</h2>
            <div className="form-group">
              <label>Teacher Name (sender name)</label>
              <input type="text" value={teacherName} onChange={(e) => setTeacherName(e.target.value)} placeholder="e.g. Mrs. Sharma" />
            </div>
            <div className="form-group">
              <label>Google Meet Link</label>
              <input type="url" value={meetUrl} onChange={(e) => setMeetUrl(e.target.value)} placeholder="https://meet.google.com/xxx-yyy-zzz" />
            </div>
            <div className="form-group">
              <label>Email Template (use {'{{LINK}}'} for the unique link)</label>
              <textarea value={emailTemplate} onChange={(e) => setEmailTemplate(e.target.value)} rows={6} />
              <small className="hint">Use {'{{LINK}}'} where each student's unique link should appear</small>
            </div>
            <div className="form-group">
              <label>Student Emails</label>
              <textarea value={emailsText} onChange={(e) => handleEmailsTextChange(e.target.value)} rows={4} placeholder="ahmed@gmail.com&#10;sara@gmail.com" />
              <div className="file-upload-row">
                <label className="file-btn">
                  📎 Upload CSV / Excel
                  <input type="file" accept=".csv,.xlsx,.xls" onChange={handleFileUpload} hidden />
                </label>
                <span className="email-count">{emails.length > 0 ? `${emails.length} emails ready` : 'or type above'}</span>
              </div>
            </div>
            <button className="btn btn-primary btn-large" onClick={startSession} disabled={loading}>
              {loading ? 'Sending...' : '🚀 Send Links to All Students'}
            </button>
          </div>
        )}

        {view === 'detail' && sessionDetail && (
          <div className="dashboard">
            <div className="card session-info">
              <h2>Session: {sessionDetail.teacher_name}</h2>
              <div className="info-grid">
                <div className="info-item">
                  <div className="label">Students</div>
                  <div className="value">{sessionDetail.student_count}</div>
                </div>
                <div className="info-item">
                  <div className="label">Visits</div>
                  <div className="value">{visits.length}</div>
                </div>
                <div className="info-item">
                  <div className="label">Sharers</div>
                  <div className="value">{sharers.length}</div>
                </div>
                <div className="info-item">
                  <div className="label">Created</div>
                  <div className="value" style={{ fontSize: '14px' }}>{formatDate(sessionDetail.created_at)}</div>
                </div>
              </div>
              <div className="dashboard-url-row">
                <code className="dashboard-url">{window.location.origin}/dashboard?session={activeSessionId}</code>
                <button className="btn btn-small" onClick={() => copyDashboardUrl(activeSessionId)}>
                  {copied ? '✅ Copied!' : '📋 Copy URL'}
                </button>
              </div>
            </div>

            {sharers.length > 0 && (
              <div className="card sharers-card">
                <h2>🚨 People Who Shared the Link</h2>
                <div className="sharers-list">
                  {sharers.map((s, i) => (
                    <div key={i} className="sharer-item">
                      <div className="sharer-header">
                        <span className="sharer-name">{s.student_email}</span>
                        <span className="sharer-badge">{s.outsider_count} outsider(s)</span>
                      </div>
                      <div className="outsider-details">
                        {s.outsiders.map((o, j) => (
                          <div key={j} className="outsider-row">
                            <span className="outsider-icon">👤</span>
                            <div className="outsider-info">
                              <strong>{o.city}, {o.country}</strong>
                              <span>{o.device} • {o.os}</span>
                              <span>via {o.referrer_app} • {formatTime(o.time)}</span>
                              {o.is_crawler && <span className="crawler-tag"> (link preview)</span>}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="card">
              <h2>📊 Live Visit Feed</h2>
              {visits.length === 0 ? (
                <p className="empty-state">No visits yet. Waiting for students to click their links...</p>
              ) : (
                <div className="table-wrapper">
                  <table className="visit-table">
                    <thead>
                      <tr>
                        <th>Time</th>
                        <th>Student (link owner)</th>
                        <th>City</th>
                        <th>Device</th>
                        <th>Via</th>
                        <th>Crawler?</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visits.map((v) => (
                        <tr key={v.id} className={v.is_crawler ? 'crawler-row' : ''}>
                          <td>{formatTime(v.timestamp)}</td>
                          <td>{v.student_email}</td>
                          <td>{v.city}, {v.country}</td>
                          <td>{v.device} ({v.os})</td>
                          <td>{v.referrer_app}</td>
                          <td>{v.is_crawler ? '🤖 Yes' : 'No'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="reset-row">
              <button className="btn btn-danger" onClick={() => deleteSession(activeSessionId)}>
                🗑 Delete Session (wipe all data)
              </button>
            </div>
          </div>
        )}

        {view === 'list' && (
          <div className="card welcome-card">
            <h2>Welcome to ClassLink</h2>
            <p>Select a session from the sidebar to view details, or create a new one to get started.</p>
            <button className="btn btn-primary" onClick={newSession}>
              + New Session
            </button>
          </div>
        )}
      </main>

      {/* Delete confirmation modal */}
      {deleteConfirm && (
        <div className="modal-overlay" onClick={() => setDeleteConfirm(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Delete Session?</h3>
            <p>This will permanently delete the session and all its data — visits, emails, tokens. This cannot be undone.</p>
            <div className="modal-actions">
              <button className="btn btn-outline" onClick={() => setDeleteConfirm(null)}>Cancel</button>
              <button className="btn btn-danger" onClick={confirmDelete}>Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
