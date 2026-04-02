import { useEffect, useState } from 'react'
import { opportunitiesApi, type Opportunity } from '../api/opportunities'

export default function Deadlines() {
  const [opportunities, setOpportunities] = useState<Opportunity[]>([])
  const [rollingOpps, setRollingOpps] = useState<Opportunity[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    opportunitiesApi
      .list({ page_size: 100, sort_by: 'deadline', sort_order: 'asc', opportunity_status: 'open' })
      .then((res) => {
        const rolling: Opportunity[] = []
        const withDeadlines: Opportunity[] = []
        for (const o of res.data.items) {
          if (o.deadline_type === 'rolling' || o.deadline_type === 'quarterly') {
            rolling.push(o)
          } else if (o.deadline) {
            withDeadlines.push(o)
          }
        }
        setOpportunities(withDeadlines)
        setRollingOpps(rolling)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  // Group by month
  const grouped: Record<string, Opportunity[]> = {}
  for (const opp of opportunities) {
    if (!opp.deadline) continue
    const dateStr = opp.deadline
    let monthKey = 'Other'
    try {
      const d = new Date(dateStr)
      if (!isNaN(d.getTime())) {
        monthKey = d.toLocaleString('default', { month: 'long', year: 'numeric' })
      }
    } catch {
      monthKey = dateStr.substring(0, 7) || 'Other'
    }
    if (!grouped[monthKey]) grouped[monthKey] = []
    grouped[monthKey].push(opp)
  }

  if (loading) return <div className="text-gray-500">Loading...</div>

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Upcoming Deadlines</h1>

      {/* Always Open / Rolling Section */}
      {rollingOpps.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-green-800 mb-3 border-b border-green-200 pb-2">
            Always Open &amp; Rolling Deadlines
          </h2>
          <div className="space-y-3">
            {rollingOpps.map((opp) => (
              <div key={opp.id} className="bg-green-50 border border-green-200 shadow rounded-lg p-4 flex items-center justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">
                      {opp.deadline_type === 'quarterly' ? 'Quarterly Review' : 'Rolling'}
                    </span>
                    <span className="px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800">
                      {opp.source}
                    </span>
                  </div>
                  <h3 className="text-sm font-medium text-gray-900 truncate">
                    {opp.url ? (
                      <a href={opp.url} target="_blank" rel="noopener noreferrer" className="hover:text-brand-600">
                        {opp.title}
                      </a>
                    ) : opp.title}
                  </h3>
                  {opp.deadline_type === 'quarterly' && opp.deadline && (
                    <p className="text-xs text-green-700 mt-1">Next quarterly review: {opp.deadline}</p>
                  )}
                  {opp.deadline_type === 'rolling' && (
                    <p className="text-xs text-green-700 mt-1">Apply anytime — reviewed on a rolling basis</p>
                  )}
                  {opp.funding_amount && (
                    <p className="text-xs text-gray-500 mt-1">Amount: {opp.funding_amount}</p>
                  )}
                </div>
                {opp.relevance_score != null && (
                  <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium flex-shrink-0 ${
                    opp.relevance_score >= 0.7 ? 'bg-green-100 text-green-800' :
                    opp.relevance_score >= 0.4 ? 'bg-yellow-100 text-yellow-800' :
                    'bg-gray-100 text-gray-800'
                  }`}>
                    {Math.round(opp.relevance_score * 100)}%
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Fixed Deadlines */}
      {opportunities.length === 0 && rollingOpps.length === 0 ? (
        <div className="text-center py-12 text-gray-500">No upcoming deadlines found.</div>
      ) : (
        <div className="space-y-8">
          {Object.entries(grouped).map(([month, opps]) => (
            <div key={month}>
              <h2 className="text-lg font-semibold text-gray-800 mb-3 border-b pb-2">{month}</h2>
              <div className="space-y-3">
                {opps.map((opp) => (
                  <div key={opp.id} className="bg-white shadow rounded-lg p-4 flex items-center justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800">
                          {opp.deadline}
                        </span>
                        <span className="px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800">
                          {opp.source}
                        </span>
                      </div>
                      <h3 className="text-sm font-medium text-gray-900 truncate">
                        {opp.url ? (
                          <a href={opp.url} target="_blank" rel="noopener noreferrer" className="hover:text-brand-600">
                            {opp.title}
                          </a>
                        ) : opp.title}
                      </h3>
                      {opp.funding_amount && (
                        <p className="text-xs text-gray-500 mt-1">Amount: {opp.funding_amount}</p>
                      )}
                    </div>
                    {opp.relevance_score != null && (
                      <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium flex-shrink-0 ${
                        opp.relevance_score >= 0.7 ? 'bg-green-100 text-green-800' :
                        opp.relevance_score >= 0.4 ? 'bg-yellow-100 text-yellow-800' :
                        'bg-gray-100 text-gray-800'
                      }`}>
                        {Math.round(opp.relevance_score * 100)}%
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
