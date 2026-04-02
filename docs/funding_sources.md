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
| 4 | AMD | University Program AI & HPC Cluster | https://www.amd.com/en/corporate/university-program/ai-hpc-cluster.html | Very High |
| 5 | Microsoft | Azure Research Credits | https://www.microsoft.com/en-us/azure-academic-research/ | Medium |
| 6 | Meta | Llama Impact Grants | https://www.llama.com/llama-ai-innovation/ | Medium |
| 7 | Apple | Scholars in AI/ML | https://machinelearning.apple.com/ | Medium |
| 8 | Qualcomm | Innovation Fellowship | https://www.qualcomm.com/research/university-relations/innovation-fellowship | High |
| 9 | Samsung | Global Research Outreach | https://semiconductor.samsung.com/sait/event/global-research-outreach/ | Medium |
| 10 | Toyota | Research Institute | https://www.tri.global/ | Very High |
| 11 | Ford | University Research | https://research.ford.com/ | Very High |
| 12 | Bosch | University Partnerships | https://www.bosch.com/research/ | High |
| 13 | Cisco | Research Funding | https://research.cisco.com/research-funding | Medium |
| 14 | IBM | Faculty Awards | https://research.ibm.com/university/awards | Medium |
| 15 | Adobe | Data Science Awards | https://research.adobe.com/data-science-research-awards/ | Low |
| 16 | DOE | Funding Opportunities | https://www.energy.gov/funding-financing | High |
| 17 | USDOT | Grant Programs | https://www.transportation.gov/grants | Very High |

## Computing Resources (GPU/HPC/Cloud)

### Government Programs

| # | Program | Provider | Type | Scale | Deadline |
|---|---------|----------|------|-------|----------|
| 1 | NSF ACCESS Explore | NSF ACCESS | GPU | Small | Rolling |
| 2 | NSF ACCESS Discover | NSF ACCESS | GPU | Medium | Rolling |
| 3 | NSF ACCESS Accelerate | NSF ACCESS | GPU | Large | Rolling |
| 4 | NSF ACCESS Maximize | NSF ACCESS | GPU | Large | Quarterly |
| 5 | DOE INCITE | DOE OLCF/ALCF | HPC | Large | Fixed |
| 6 | DOE ALCC | DOE OLCF/ALCF/NERSC | HPC | Large | Fixed |
| 7 | DOE NERSC ERCAP | NERSC | GPU | Large | Fixed |
| 8 | DOE NERSC Startup | NERSC | GPU | Small | Rolling |
| 9 | NAIRR Pilot | NSF / NAIRR | GPU | Medium | Rolling |
| 10 | NAIRR Classroom | NSF / NAIRR | GPU | Small | Rolling |
| 11 | DOD HPC Modernization | DOD HPCMP | HPC | Large | Rolling |
| 12 | DOD HPC Frontier | DOD HPCMP | HPC | Large | Fixed |
| 13 | NASA HEC | NASA NAS | HPC | Large | Rolling |
| 14 | NASA NCCS Discover | NASA NCCS | HPC | Large | Rolling |
| 15 | NOAA R&D HPC | NOAA | HPC | Large | Rolling |

### Industry Programs

| # | Company | Program | Type | Notes |
|---|---------|---------|------|-------|
| 1 | NVIDIA | Academic Hardware Grant | Hardware | GPUs for research |
| 2 | NVIDIA | DGX Cloud Academic | GPU | Cloud H100 hours |
| 3 | Google | TPU Research Cloud (TRC) | TPU | Free TPU v4/v5 access |
| 4 | Google Cloud | Research Credits | Cloud Credits | Up to $5K |
| 5 | AWS | Cloud Credit for Research | Cloud Credits | EC2 GPU instances |
| 6 | Microsoft | Azure for Research | Cloud Credits | Up to $25K AI for Good |
| 7 | AMD | University Program | GPU | MI250X/MI300X clusters |
| 8 | IBM | Academic Initiative | Cloud Credits | IBM Cloud + Watson |
| 9 | Oracle | OCI for Research | Cloud Credits | Up to $5K |
| 10 | Meta | Research GPU Program | GPU | Open-source AI focus |
| 11 | Intel | Developer Cloud | GPU | Gaudi2/3 accelerators |
| 12 | Cerebras | Academic Access | GPU | CS-2/CS-3 wafer-scale |
| 13 | Lambda Labs | Academic Program | GPU | 50% academic discount |
| 14 | CoreWeave | Academic Program | GPU | H100/H200 clusters |
| 15 | Nebius | Academic GPU | GPU | Academic credits |
| 16 | Prime Intellect | Compute Credits | GPU | Distributed compute |
| 17 | Together AI | Research Cloud | GPU | Open-source AI credits |

### University/National Centers

| # | Center | System | Type | Access |
|---|--------|--------|------|--------|
| 1 | TACC | Frontera, Lonestar6 | HPC | ACCESS or direct |
| 2 | PSC | Bridges-2 | GPU | NSF ACCESS |
| 3 | SDSC | Expanse | GPU | NSF ACCESS |
| 4 | OSC | Owens, Pitzer | HPC | Ohio + partners |
| 5 | NCSA | Delta | GPU | NSF ACCESS |
| 6 | Purdue RCAC | Anvil | HPC | NSF ACCESS |
| 7 | Utah CHPC | Local cluster | GPU | Faculty allocation |

## Aggregator Sources (Reference)

| Source | URL | Notes |
|--------|-----|-------|
| GrantForward | https://www.grantforward.com/ | University grant search engine |
| GrantedAI | https://grantedai.com/ | AI-specific grant aggregator |
