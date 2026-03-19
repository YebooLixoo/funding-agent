import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { opportunitiesApi, type Opportunity } from '../api/opportunities'

export default function Dashboard() {
  const { user } = useAuth()
  const [recentOpps, setRecentOpps] = useState<Opportunity[]>([])
  const [totalCount, setTotalCount] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    opportunitiesApi
      .list({ page_size: 5, sort_by: 'fetched_at', sort_order: 'desc' })
      .then((res) => {
        setRecentOpps(res.data.items)
        setTotalCount(res.data.total)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">
        Welcome back, {user?.full_name?.split(' ')[0]}
      </h1>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 mb-8">
        <SummaryCard label="Total Opportunities" value={totalCount} />
        <SummaryCard label="Institution" value={user?.institution || 'Not set'} />
        <SummaryCard label="Position" value={user?.position || 'Not set'} />
      </div>

      <div className="bg-white shadow rounded-lg">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">Recent Opportunities</h2>
          <Link
            to="/opportunities"
            className="text-sm text-brand-600 hover:text-brand-700 font-medium"
          >
            View all
          </Link>
        </div>
        {loading ? (
          <div className="p-6 text-gray-500">Loading...</div>
        ) : recentOpps.length === 0 ? (
          <div className="p-6 text-gray-500">No opportunities found yet.</div>
        ) : (
          <ul className="divide-y divide-gray-200">
            {recentOpps.map((opp) => (
              <li key={opp.id} className="px-6 py-4 hover:bg-gray-50">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <h3 className="text-sm font-medium text-gray-900 truncate">{opp.title}</h3>
                    <p className="text-sm text-gray-500 mt-1">
                      {opp.source} {opp.deadline ? `| Deadline: ${opp.deadline}` : ''}
                    </p>
                  </div>
                  {opp.relevance_score != null && (
                    <ScoreBadge score={opp.relevance_score} />
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

function SummaryCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-white shadow rounded-lg p-6">
      <p className="text-sm text-gray-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-gray-900">{value}</p>
    </div>
  )
}

function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  const color =
    pct >= 70 ? 'bg-green-100 text-green-800' :
    pct >= 40 ? 'bg-yellow-100 text-yellow-800' :
    'bg-gray-100 text-gray-800'
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${color}`}>
      {pct}%
    </span>
  )
}
