import { useEffect, useState, useCallback } from 'react'
import { fetchApi, type FetchConfig } from '../api/fetch'

const SOURCE_LABELS: Record<string, string> = {
  nsf: 'NSF (National Science Foundation)',
  nih: 'NIH (National Institutes of Health)',
  grants_gov: 'Grants.gov',
  web_sources_gov: 'Government Websites (DOE, USDOT, etc.)',
  web_sources_industry: 'Industry (NVIDIA, AMD, Google, etc.)',
  web_sources_university: 'University Internal Funding',
  compute: 'Computing Resources (GPU/HPC/Cloud)',
}

export default function FetchSettings() {
  const [config, setConfig] = useState<FetchConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [triggering, setTriggering] = useState(false)
  const [msg, setMsg] = useState('')

  const fetchData = useCallback(async () => {
    try {
      const res = await fetchApi.getConfig()
      setConfig(res.data)
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const handleToggleSource = (source: string) => {
    if (!config?.sources_enabled) return
    setConfig(c => c ? {
      ...c,
      sources_enabled: { ...c.sources_enabled, [source]: !c.sources_enabled?.[source] },
    } : c)
  }

  const handleSave = async () => {
    if (!config) return
    setSaving(true)
    setMsg('')
    try {
      await fetchApi.updateConfig({
        sources_enabled: config.sources_enabled,
        fetch_frequency: config.fetch_frequency,
      })
      setMsg('Settings saved')
      setTimeout(() => setMsg(''), 3000)
    } catch { setMsg('Error saving') }
    finally { setSaving(false) }
  }

  const handleTrigger = async () => {
    setTriggering(true)
    try {
      await fetchApi.trigger()
      setMsg('Fetch triggered')
      fetchData()
      setTimeout(() => setMsg(''), 3000)
    } catch { setMsg('Error triggering fetch') }
    finally { setTriggering(false) }
  }

  if (loading) return <div className="text-gray-500">Loading...</div>
  if (!config) return <div className="text-gray-500">Error loading config</div>

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Fetch Settings</h1>

      <div className="bg-white shadow rounded-lg p-6 space-y-5">
        <div>
          <h3 className="text-sm font-medium text-gray-900 mb-3">Data Sources</h3>
          <div className="space-y-2">
            {Object.entries(SOURCE_LABELS).map(([key, label]) => (
              <label key={key} className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={config.sources_enabled?.[key] ?? true}
                  onChange={() => handleToggleSource(key)}
                  className="h-4 w-4 text-brand-600 rounded border-gray-300"
                />
                <span className="text-sm text-gray-700">{label}</span>
              </label>
            ))}
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Fetch Frequency</label>
          <select
            value={config.fetch_frequency}
            onChange={(e) => setConfig(c => c ? { ...c, fetch_frequency: e.target.value } : c)}
            className="px-3 py-2 border border-gray-300 rounded-md text-sm"
          >
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="biweekly">Biweekly</option>
          </select>
        </div>

        {config.last_fetched_at && (
          <p className="text-sm text-gray-500">
            Last fetched: {new Date(config.last_fetched_at).toLocaleString()}
          </p>
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
            onClick={handleTrigger}
            disabled={triggering}
            className="px-4 py-2 border border-brand-600 text-brand-600 rounded-md text-sm font-medium hover:bg-brand-50 disabled:opacity-50"
          >
            {triggering ? 'Triggering...' : 'Trigger Fetch Now'}
          </button>
          {msg && <span className="text-sm text-green-600">{msg}</span>}
        </div>
      </div>
    </div>
  )
}
