import { useEffect, useState } from 'react'
import { opportunitiesApi, type Opportunity } from '../api/opportunities'

export default function Deadlines() {
  const [opportunities, setOpportunities] = useState<Opportunity[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    opportunitiesApi
      .list({ page_size: 100, sort_by: 'deadline', sort_order: 'asc' })
      .then((res) => {
        // Filter to only those with deadlines
        const withDeadlines = res.data.items.filter((o) => o.deadline)
        setOpportunities(withDeadlines)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  // Group by month
  const grouped: Record<string, Opportunity[]> = {}
  for (const opp of opportunities) {
    if (!opp.deadline) continue
    // Try to parse deadline month
    const dateStr = opp.deadline
    let monthKey = 'Other'
    try {
      const d = new Date(dateStr)
      if (!isNaN(d.getTime())) {
        monthKey = d.toLocaleString('default', { month: 'long', year: 'numeric' })
      }
    } catch {
      // Use raw string
      monthKey = dateStr.substring(0, 7) || 'Other'
    }
    if (!grouped[monthKey]) grouped[monthKey] = []
    grouped[monthKey].push(opp)
  }

  if (loading) return <div className="text-gray-500">Loading...</div>

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Upcoming Deadlines</h1>

      {opportunities.length === 0 ? (
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
