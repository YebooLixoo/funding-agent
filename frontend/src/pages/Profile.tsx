import { useEffect, useState, useCallback } from 'react'
import { useAuth } from '../hooks/useAuth'
import { usersApi, type UserUpdate } from '../api/users'
import { keywordsApi, scoringApi, type Keyword, type KeywordsByCategory } from '../api/keywords'

const CATEGORIES = ['primary', 'domain', 'career', 'faculty', 'exclusion', 'custom'] as const
type Category = typeof CATEGORIES[number]

const CATEGORY_LABELS: Record<Category, string> = {
  primary: 'Primary (AI/Methods)',
  domain: 'Domain (Application Areas)',
  career: 'Career Stage',
  faculty: 'Faculty/Institutional',
  exclusion: 'Exclusions (Auto-reject)',
  custom: 'Custom',
}

const CATEGORY_COLORS: Record<Category, string> = {
  primary: 'bg-blue-100 text-blue-800',
  domain: 'bg-green-100 text-green-800',
  career: 'bg-purple-100 text-purple-800',
  faculty: 'bg-orange-100 text-orange-800',
  exclusion: 'bg-red-100 text-red-800',
  custom: 'bg-gray-100 text-gray-800',
}

export default function Profile() {
  const { user } = useAuth()
  const [activeTab, setActiveTab] = useState<Category>('primary')
  const [keywords, setKeywords] = useState<KeywordsByCategory | null>(null)
  const [newKeyword, setNewKeyword] = useState('')
  const [loading, setLoading] = useState(true)
  const [rescoring, setRescoring] = useState(false)
  const [profileForm, setProfileForm] = useState<UserUpdate>({})
  const [saving, setSaving] = useState(false)
  const [profileMsg, setProfileMsg] = useState('')

  // Profile form
  useEffect(() => {
    if (user) {
      setProfileForm({
        full_name: user.full_name,
        institution: user.institution || '',
        department: user.department || '',
        position: user.position || '',
        research_summary: user.research_summary || '',
      })
    }
  }, [user])

  const fetchKeywords = useCallback(async () => {
    try {
      const res = await keywordsApi.list()
      setKeywords(res.data)
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchKeywords() }, [fetchKeywords])

  const handleAddKeyword = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newKeyword.trim()) return
    try {
      await keywordsApi.add({ keyword: newKeyword.trim(), category: activeTab })
      setNewKeyword('')
      fetchKeywords()
    } catch { /* ignore */ }
  }

  const handleRemoveKeyword = async (id: string) => {
    try {
      await keywordsApi.remove(id)
      fetchKeywords()
    } catch { /* ignore */ }
  }

  const handleToggleKeyword = async (kw: Keyword) => {
    try {
      await keywordsApi.update(kw.id, { is_active: !kw.is_active })
      fetchKeywords()
    } catch { /* ignore */ }
  }

  const handleRescore = async () => {
    setRescoring(true)
    try {
      await scoringApi.rescore()
    } catch { /* ignore */ }
    finally { setRescoring(false) }
  }

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setProfileMsg('')
    try {
      await usersApi.updateMe(profileForm)
      setProfileMsg('Profile saved')
      setTimeout(() => setProfileMsg(''), 3000)
    } catch { setProfileMsg('Error saving profile') }
    finally { setSaving(false) }
  }

  const currentKeywords = keywords ? (keywords[activeTab] || []) : []

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold text-gray-900">Profile & Keywords</h1>

      {/* Profile Info */}
      <div className="bg-white shadow rounded-lg p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Personal Information</h2>
        <form onSubmit={handleSaveProfile} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Full Name</label>
            <input
              type="text"
              value={profileForm.full_name || ''}
              onChange={(e) => setProfileForm(f => ({ ...f, full_name: e.target.value }))}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Institution</label>
            <input
              type="text"
              value={profileForm.institution || ''}
              onChange={(e) => setProfileForm(f => ({ ...f, institution: e.target.value }))}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Department</label>
            <input
              type="text"
              value={profileForm.department || ''}
              onChange={(e) => setProfileForm(f => ({ ...f, department: e.target.value }))}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Position</label>
            <input
              type="text"
              value={profileForm.position || ''}
              onChange={(e) => setProfileForm(f => ({ ...f, position: e.target.value }))}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
          <div className="sm:col-span-2">
            <label className="block text-sm font-medium text-gray-700 mb-1">Research Summary</label>
            <textarea
              rows={3}
              value={profileForm.research_summary || ''}
              onChange={(e) => setProfileForm(f => ({ ...f, research_summary: e.target.value }))}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
          <div className="sm:col-span-2 flex items-center gap-3">
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 bg-brand-600 text-white rounded-md text-sm font-medium hover:bg-brand-700 disabled:opacity-50"
            >
              {saving ? 'Saving...' : 'Save Profile'}
            </button>
            {profileMsg && <span className="text-sm text-green-600">{profileMsg}</span>}
          </div>
        </form>
      </div>

      {/* Keyword Management */}
      <div className="bg-white shadow rounded-lg">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">Research Keywords</h2>
          <button
            onClick={handleRescore}
            disabled={rescoring}
            className="px-3 py-1.5 bg-brand-600 text-white rounded-md text-sm font-medium hover:bg-brand-700 disabled:opacity-50"
          >
            {rescoring ? 'Rescoring...' : 'Rescore Opportunities'}
          </button>
        </div>

        {/* Category Tabs */}
        <div className="border-b border-gray-200 px-6">
          <div className="flex gap-1 -mb-px overflow-x-auto">
            {CATEGORIES.map((cat) => {
              const count = keywords ? (keywords[cat]?.length || 0) : 0
              return (
                <button
                  key={cat}
                  onClick={() => setActiveTab(cat)}
                  className={`px-3 py-3 text-sm font-medium border-b-2 whitespace-nowrap transition-colors ${
                    activeTab === cat
                      ? 'border-brand-600 text-brand-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}
                >
                  {CATEGORY_LABELS[cat]} ({count})
                </button>
              )
            })}
          </div>
        </div>

        <div className="p-6">
          {/* Add keyword */}
          <form onSubmit={handleAddKeyword} className="flex gap-2 mb-4">
            <input
              type="text"
              placeholder={`Add ${activeTab} keyword...`}
              value={newKeyword}
              onChange={(e) => setNewKeyword(e.target.value)}
              className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
            <button
              type="submit"
              className="px-4 py-2 bg-brand-600 text-white rounded-md text-sm font-medium hover:bg-brand-700"
            >
              Add
            </button>
          </form>

          {/* Keyword tags */}
          {loading ? (
            <p className="text-gray-500 text-sm">Loading...</p>
          ) : currentKeywords.length === 0 ? (
            <p className="text-gray-500 text-sm">
              No {activeTab} keywords yet. Add some above.
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {currentKeywords.map((kw) => (
                <span
                  key={kw.id}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium ${
                    kw.is_active ? CATEGORY_COLORS[activeTab] : 'bg-gray-100 text-gray-400 line-through'
                  }`}
                >
                  {kw.keyword}
                  <button
                    onClick={() => handleToggleKeyword(kw)}
                    className="hover:opacity-70"
                    title={kw.is_active ? 'Disable' : 'Enable'}
                  >
                    {kw.is_active ? '○' : '●'}
                  </button>
                  <button
                    onClick={() => handleRemoveKeyword(kw.id)}
                    className="hover:opacity-70"
                    title="Remove"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
