import { useEffect, useState, useCallback } from 'react'
import { opportunitiesApi, type Opportunity, type OpportunityFilters } from '../api/opportunities'

export default function Opportunities() {
  const [opportunities, setOpportunities] = useState<Opportunity[]>([])
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)
  const [loading, setLoading] = useState(true)
  const [filters, setFilters] = useState<OpportunityFilters>({
    page: 1,
    page_size: 20,
    sort_by: 'fetched_at',
    sort_order: 'desc',
  })
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')

  const fetchOpps = useCallback(async () => {
    setLoading(true)
    try {
      const params: OpportunityFilters = { ...filters }
      if (search) params.search = search
      const res = await opportunitiesApi.list(params)
      setOpportunities(res.data.items)
      setTotal(res.data.total)
      setTotalPages(res.data.total_pages)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [filters, search])

  useEffect(() => {
    fetchOpps()
  }, [fetchOpps])

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setSearch(searchInput)
    setFilters((f) => ({ ...f, page: 1 }))
  }

  const handleBookmark = async (id: string, isBookmarked: boolean) => {
    try {
      if (isBookmarked) {
        await opportunitiesApi.unbookmark(id)
      } else {
        await opportunitiesApi.bookmark(id)
      }
      setOpportunities((opps) =>
        opps.map((o) => (o.id === id ? { ...o, is_bookmarked: !isBookmarked } : o))
      )
    } catch {
      // ignore
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Opportunities</h1>
        <span className="text-sm text-gray-500">{total} total</span>
      </div>

      {/* Search & Filters */}
      <div className="bg-white shadow rounded-lg p-4 mb-6">
        <form onSubmit={handleSearch} className="flex gap-3">
          <input
            type="text"
            placeholder="Search opportunities..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
          />
          <button
            type="submit"
            className="px-4 py-2 bg-brand-600 text-white rounded-md hover:bg-brand-700 transition-colors text-sm font-medium"
          >
            Search
          </button>
        </form>
        <div className="flex gap-4 mt-3 flex-wrap">
          <select
            value={filters.source_type || ''}
            onChange={(e) =>
              setFilters((f) => ({ ...f, source_type: e.target.value || undefined, page: 1 }))
            }
            className="px-3 py-1.5 border border-gray-300 rounded-md text-sm"
          >
            <option value="">All types</option>
            <option value="government">Government</option>
            <option value="industry">Industry</option>
            <option value="university">University</option>
            <option value="compute">Compute Resources</option>
          </select>
          <select
            value={filters.sort_by}
            onChange={(e) => setFilters((f) => ({ ...f, sort_by: e.target.value }))}
            className="px-3 py-1.5 border border-gray-300 rounded-md text-sm"
          >
            <option value="fetched_at">Date added</option>
            <option value="deadline">Deadline</option>
          </select>
          <select
            value={filters.sort_order}
            onChange={(e) => setFilters((f) => ({ ...f, sort_order: e.target.value }))}
            className="px-3 py-1.5 border border-gray-300 rounded-md text-sm"
          >
            <option value="desc">Newest first</option>
            <option value="asc">Oldest first</option>
          </select>
        </div>
      </div>

      {/* Results */}
      {loading ? (
        <div className="text-center py-12 text-gray-500">Loading...</div>
      ) : opportunities.length === 0 ? (
        <div className="text-center py-12 text-gray-500">No opportunities found.</div>
      ) : (
        <div className="space-y-4">
          {opportunities.map((opp) => (
            <OpportunityCard
              key={opp.id}
              opportunity={opp}
              onBookmark={() => handleBookmark(opp.id, opp.is_bookmarked)}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 mt-8">
          <button
            disabled={filters.page === 1}
            onClick={() => setFilters((f) => ({ ...f, page: (f.page || 1) - 1 }))}
            className="px-3 py-1.5 border border-gray-300 rounded-md text-sm disabled:opacity-50"
          >
            Previous
          </button>
          <span className="text-sm text-gray-600">
            Page {filters.page} of {totalPages}
          </span>
          <button
            disabled={filters.page === totalPages}
            onClick={() => setFilters((f) => ({ ...f, page: (f.page || 1) + 1 }))}
            className="px-3 py-1.5 border border-gray-300 rounded-md text-sm disabled:opacity-50"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}

function OpportunityCard({
  opportunity: opp,
  onBookmark,
}: {
  opportunity: Opportunity
  onBookmark: () => void
}) {
  const pct = opp.relevance_score != null ? Math.round(opp.relevance_score * 100) : null
  const scoreColor =
    pct != null && pct >= 70
      ? 'bg-green-100 text-green-800'
      : pct != null && pct >= 40
        ? 'bg-yellow-100 text-yellow-800'
        : 'bg-gray-100 text-gray-800'

  return (
    <div className="bg-white shadow rounded-lg p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800">
              {opp.source}
            </span>
            {opp.source_type && (
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-600">
                {opp.source_type}
              </span>
            )}
            {opp.resource_type && (
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800">
                {opp.resource_type.toUpperCase()}
              </span>
            )}
            {(opp.deadline_type === 'rolling' || opp.deadline_type === 'quarterly') && (
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">
                {opp.deadline_type === 'quarterly' ? 'Quarterly Review' : 'Rolling'}
              </span>
            )}
            {pct != null && (
              <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${scoreColor}`}>
                {pct}% match
              </span>
            )}
          </div>
          <h3 className="text-base font-semibold text-gray-900">
            {opp.url ? (
              <a
                href={opp.url}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-brand-600"
              >
                {opp.title}
              </a>
            ) : (
              opp.title
            )}
          </h3>
          {opp.summary && (
            <p className="text-sm text-gray-600 mt-2 line-clamp-2">{opp.summary}</p>
          )}
          <div className="flex flex-wrap gap-4 mt-3 text-xs text-gray-500">
            {opp.deadline_type === 'quarterly' && opp.deadline ? (
              <span>Next quarterly review: {opp.deadline}</span>
            ) : opp.deadline_type === 'rolling' ? (
              <span>Rolling — apply anytime</span>
            ) : opp.deadline ? (
              <span>Deadline: {opp.deadline}</span>
            ) : null}
            {opp.funding_amount && <span>Amount: {opp.funding_amount}</span>}
            {opp.allocation_details && <span>Resources: {opp.allocation_details}</span>}
            {opp.eligibility && <span>Eligibility: {opp.eligibility}</span>}
            {opp.posted_date && <span>Posted: {opp.posted_date}</span>}
            {opp.access_url && (
              <a href={opp.access_url} target="_blank" rel="noopener noreferrer"
                 className="text-brand-600 hover:underline font-medium">
                Apply
              </a>
            )}
          </div>
          {opp.matched_keywords && opp.matched_keywords.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {opp.matched_keywords.map((kw, i) => (
                <span
                  key={i}
                  className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-brand-50 text-brand-700"
                >
                  {kw}
                </span>
              ))}
            </div>
          )}
        </div>
        <button
          onClick={onBookmark}
          className={`flex-shrink-0 p-2 rounded-md transition-colors ${
            opp.is_bookmarked
              ? 'text-yellow-500 hover:text-yellow-600'
              : 'text-gray-400 hover:text-gray-600'
          }`}
          title={opp.is_bookmarked ? 'Remove bookmark' : 'Bookmark'}
        >
          <svg className="w-5 h-5" fill={opp.is_bookmarked ? 'currentColor' : 'none'} viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
          </svg>
        </button>
      </div>
    </div>
  )
}
