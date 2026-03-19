import { useEffect, useState, useCallback } from 'react'
import { emailApi, type EmailPref, type EmailHistory } from '../api/email'

const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

export default function EmailSettings() {
  const [pref, setPref] = useState<EmailPref | null>(null)
  const [history, setHistory] = useState<EmailHistory[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  const fetchData = useCallback(async () => {
    try {
      const [prefRes, histRes] = await Promise.all([
        emailApi.getPreferences(),
        emailApi.history(),
      ])
      setPref(prefRes.data)
      setHistory(histRes.data)
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const handleSave = async () => {
    if (!pref) return
    setSaving(true)
    setMsg('')
    try {
      const res = await emailApi.updatePreferences({
        is_subscribed: pref.is_subscribed,
        frequency: pref.frequency,
        day_of_week: pref.day_of_week,
        time_of_day: pref.time_of_day,
        min_relevance_score: pref.min_relevance_score,
        deadline_lookahead_days: pref.deadline_lookahead_days,
      })
      setPref(res.data)
      setMsg('Settings saved')
      setTimeout(() => setMsg(''), 3000)
    } catch { setMsg('Error saving') }
    finally { setSaving(false) }
  }

  const handleSendTest = async () => {
    try {
      await emailApi.sendTest()
      setMsg('Test email sent')
      fetchData()
      setTimeout(() => setMsg(''), 3000)
    } catch { setMsg('Error sending test') }
  }

  if (loading) return <div className="text-gray-500">Loading...</div>
  if (!pref) return <div className="text-gray-500">Error loading preferences</div>

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Email Settings</h1>

      <div className="bg-white shadow rounded-lg p-6 space-y-5">
        {/* Subscribe toggle */}
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-medium text-gray-900">Email Digest</h3>
            <p className="text-sm text-gray-500">Receive personalized funding opportunities by email</p>
          </div>
          <button
            onClick={() => setPref(p => p ? { ...p, is_subscribed: !p.is_subscribed } : p)}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
              pref.is_subscribed ? 'bg-brand-600' : 'bg-gray-300'
            }`}
          >
            <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
              pref.is_subscribed ? 'translate-x-6' : 'translate-x-1'
            }`} />
          </button>
        </div>

        {pref.is_subscribed && (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Frequency</label>
                <select
                  value={pref.frequency}
                  onChange={(e) => setPref(p => p ? { ...p, frequency: e.target.value } : p)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                >
                  <option value="daily">Daily</option>
                  <option value="weekly">Weekly</option>
                  <option value="biweekly">Biweekly</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Day</label>
                <select
                  value={pref.day_of_week}
                  onChange={(e) => setPref(p => p ? { ...p, day_of_week: Number(e.target.value) } : p)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                >
                  {DAY_NAMES.map((name, i) => (
                    <option key={i} value={i}>{name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Time</label>
                <input
                  type="time"
                  value={pref.time_of_day}
                  onChange={(e) => setPref(p => p ? { ...p, time_of_day: e.target.value } : p)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Min relevance score: {Math.round(pref.min_relevance_score * 100)}%
                </label>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={Math.round(pref.min_relevance_score * 100)}
                  onChange={(e) => setPref(p => p ? { ...p, min_relevance_score: Number(e.target.value) / 100 } : p)}
                  className="w-full"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Deadline lookahead: {pref.deadline_lookahead_days} days
                </label>
                <input
                  type="range"
                  min="7"
                  max="90"
                  value={pref.deadline_lookahead_days}
                  onChange={(e) => setPref(p => p ? { ...p, deadline_lookahead_days: Number(e.target.value) } : p)}
                  className="w-full"
                />
              </div>
            </div>
          </>
        )}

        <div className="flex items-center gap-3 pt-2">
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 bg-brand-600 text-white rounded-md text-sm font-medium hover:bg-brand-700 disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
          <button
            onClick={handleSendTest}
            className="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium hover:bg-gray-50"
          >
            Send Test Email
          </button>
          {msg && <span className="text-sm text-green-600">{msg}</span>}
        </div>
      </div>

      {/* Send History */}
      <div className="bg-white shadow rounded-lg">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Send History</h2>
        </div>
        {history.length === 0 ? (
          <div className="p-6 text-gray-500 text-sm">No emails sent yet.</div>
        ) : (
          <ul className="divide-y divide-gray-200">
            {history.map((h) => (
              <li key={h.id} className="px-6 py-3 flex items-center justify-between">
                <div>
                  <span className="text-sm text-gray-900">
                    {new Date(h.sent_at).toLocaleString()}
                  </span>
                  <span className="text-sm text-gray-500 ml-2">
                    ({h.opportunity_count} opportunities)
                  </span>
                </div>
                <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                  h.success ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                }`}>
                  {h.success ? 'Sent' : 'Failed'}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
