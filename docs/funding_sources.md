# Funding Sources Reference

Complete list of all monitored funding sources for AI + Transportation research.

## Government Sources (API-based)

### SAM.gov
- **API**: `GET https://api.sam.gov/opportunities/v2/search`
- **Auth**: API key (query param `api_key`)
- **Rate Limit**: 10 requests/day
- **Registration**: https://sam.gov/ → Account Details → Request public API key
- **Notes**: Federal contract opportunities and grants. Supports keyword search, date range filtering, and opportunity type filtering.

### NSF (National Science Foundation)
- **Awards API**: `GET http://api.nsf.gov/services/v1/awards.json`
- **RSS Feed**: https://www.nsf.gov/rss/rss_www_funding.xml
- **Auth**: None required
- **Notes**: Dual approach — Awards API for keyword search (indicates funded research topics), RSS feed for new funding announcements.

### Grants.gov (Simpler API)
- **API**: `POST https://api.simpler.grants.gov/v1/opportunities/search`
- **Auth**: API key (header `X-Api-Key`)
- **Rate Limit**: 60 requests/minute
- **Registration**: https://simpler.grants.gov/developer or contact Help Desk
- **Notes**: Federal grant opportunities aggregator. Supports JSON body search with query, date filters, pagination.

## Industry Sources (Web Scraping)

| # | Company | Program | URL | Relevance |
|---|---------|---------|-----|-----------|
| 1 | Amazon | Research Awards | https://www.amazon.science/research-awards | High |
| 2 | Google | Research Scholar Program | https://research.google/programs-and-events/research-scholar-program/ | High |
| 3 | NVIDIA | Academic Hardware Grant | https://www.nvidia.com/en-us/industries/higher-education-research/academic-grant-program/ | Very High |
| 4 | Microsoft | Azure Research Credits | https://www.microsoft.com/en-us/azure-academic-research/ | Medium |
| 5 | Meta | Llama Impact Grants | https://www.llama.com/llama-ai-innovation/ | Medium |
| 6 | Apple | Scholars in AI/ML | https://machinelearning.apple.com/ | Medium |
| 7 | Qualcomm | Innovation Fellowship | https://www.qualcomm.com/research/university-relations/innovation-fellowship | High |
| 8 | Samsung | Global Research Outreach | https://semiconductor.samsung.com/sait/event/global-research-outreach/ | Medium |
| 9 | Toyota | Research Institute | https://www.tri.global/ | Very High |
| 10 | Ford | University Research | https://research.ford.com/ | Very High |
| 11 | Bosch | University Partnerships | https://www.bosch.com/research/ | High |
| 12 | Cisco | Research Funding | https://research.cisco.com/research-funding | Medium |
| 13 | IBM | Faculty Awards | https://research.ibm.com/university/awards | Medium |
| 14 | Adobe | Data Science Awards | https://research.adobe.com/data-science-research-awards/ | Low |
| 15 | DOE | Funding Opportunities | https://www.energy.gov/funding-financing | High |
| 16 | USDOT | Grant Programs | https://www.transportation.gov/grants | Very High |

## Aggregator Sources (Reference)

| Source | URL | Notes |
|--------|-----|-------|
| GrantForward | https://www.grantforward.com/ | University grant search engine |
| GrantedAI | https://grantedai.com/ | AI-specific grant aggregator |
