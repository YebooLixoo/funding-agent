# GPU / HPC / Computing Resource Access Programs for Academic Researchers

**Compiled: April 2, 2026**
**Target audience: Assistant/Associate professors in Engineering, CS, AI**

---

## 1. US Government Programs

### NSF ACCESS (formerly XSEDE)
- **Provider:** National Science Foundation
- **URL:** https://allocations.access-ci.org
- **Resources:** GPU clusters, HPC systems, storage across dozens of national centers (Bridges-2, Expanse, Stampede-3, Delta, etc.)
- **Tiers:**
  - **Explore** -- 1-page abstract, approved in days. Great for benchmarking, pilot runs, grad student projects. No PI status required.
  - **Discover** -- For research grants with modest needs, Campus Champions, large classes.
  - **Accelerate** -- Substantial allocations for active research programs.
  - **Maximize** -- Largest allocations; semi-annual review. Next deadline: **June 15 - July 31, 2026** (awards start Oct 1, 2026).
- **Rolling/Fixed:** Explore, Discover, Accelerate are rolling. Maximize is semi-annual.
- **Scale:** Explore = small pilot; Maximize = millions of CPU/GPU hours.
- **Notes:** Start with Explore and upgrade. Easiest on-ramp to national HPC. A postdoc can get GPU access within a week via Explore.

### DOE INCITE (Innovative and Novel Computational Impact on Theory and Experiment)
- **Provider:** Department of Energy / OLCF + ALCF
- **URL:** https://doeleadershipcomputing.org/call-for-proposals/
- **Resources:** Up to 60% of allocatable time on Frontier (ORNL, exascale) and Aurora (ANL, exascale)
- **Rolling/Fixed:** Annual call, typically April-June for next calendar year
- **Scale:** Large -- typically 500,000 to 1,000,000 node-hours per award on Frontier or Aurora
- **Notes:** Flagship DOE program. Competitive. Open to academia, industry, national labs.

### DOE ALCC (ASCR Leadership Computing Challenge)
- **Provider:** Department of Energy / ASCR
- **URL:** https://science.osti.gov/ascr/Facilities/Accessing-ASCR-Facilities/ALCC
- **Resources:** Time on Frontier, Aurora, Polaris, Perlmutter. 2026-2027 cycle includes:
  - 20M node-hours on Frontier (OLCF)
  - 16M node-hours on Aurora (ALCF)
  - 1M node-hours on Polaris (ALCF)
  - 2.25M CPU-node-hours + 1.25M GPU-node-hours on Perlmutter (NERSC)
- **Rolling/Fixed:** Annual. 2026-2027 proposals were due Jan 26, 2026. Now accepts multi-year proposals (up to 3 years).
- **Scale:** Large -- 10-30% of ASCR facility time
- **Notes:** Simplified single-proposal process (no pre-proposal). Targets high-risk, high-payoff research aligned with DOE missions.

### DOE NERSC Allocations (ERCAP)
- **Provider:** National Energy Research Scientific Computing Center (LBNL)
- **URL:** https://www.nersc.gov/users/become-a-nersc-user/
- **Resources:** Perlmutter supercomputer with 7,000+ NVIDIA A100 GPUs. Separate CPU and GPU allocation pools.
- **Rolling/Fixed:** Annual ERCAP call typically opens August, closes early October
- **Scale:** Medium to large
- **Notes:** Requires DOE Office of Science sponsorship (active DOE grant). "Startup" allocations also available for new users.

### NAIRR (National AI Research Resource) Pilot
- **Provider:** NSF + 13 federal agencies + 28 industry partners
- **URL:** https://nairrpilot.org/opportunities/allocations
- **Resources:** Compute allocations, datasets, pre-trained models, cloud credits. Includes NVIDIA A100 GPUs, access at SDSC, and Azure credits (Microsoft committed $20M in credits).
- **Rolling/Fixed:** Rolling; projects awarded for 12 months
- **Scale:** Total pilot ~3.77 exaFLOPS (~5,000 H100 equivalent). Individual awards vary.
- **Eligibility:** US-based researchers at academic institutions, nonprofits, federal agencies, startups with federal grants. Grad students eligible with faculty support letter.
- **Notes:** Specifically designed for AI research. Supported 600+ projects and 6,000+ students across all 50 states.

### DOD HPCMP (High Performance Computing Modernization Program)
- **Provider:** Department of Defense
- **URL:** https://www.hpc.mil/ and https://orise.orau.gov/hpcmp/
- **Resources:** Five DoD Supercomputing Resource Centers (DSRCs) at ERDC, ARL, NAVO, AFRL, and Maui HPC Center
- **Rolling/Fixed:** Ongoing; academic access primarily through:
  - **HIP** (HPC Internship Program) -- 10-week summer internships for STEM students
  - **FIX** (Faculty Immersion Experience) -- 10-week summer research for faculty
- **Scale:** Medium (project-dependent)
- **Notes:** Primarily serves DoD-sponsored research. Academic access mainly via summer programs and collaborations with DoD researchers.

### NASA High-End Computing (HEC)
- **Provider:** NASA / NAS Facility (Ames) + NCCS (Goddard)
- **URL:** https://hec.nasa.gov/ and https://www.nas.nasa.gov/hecc/
- **Resources:** Athena supercomputer (replaced Pleiades, decommissioned Jan 2026). More powerful than predecessors.
- **Rolling/Fixed:** Quarterly allocation decisions (Jan 1, Apr 1, Jul 1, Oct 1)
- **Scale:** Variable based on project needs
- **Notes:** Requires NASA Science Mission Directorate (SMD) funding. If you have a NASA grant, you can request HEC time annually.

### OLCF Director's Discretionary (DD) Allocations
- **Provider:** Oak Ridge National Laboratory
- **URL:** https://www.olcf.ornl.gov/for-users/documents-forms/olcf-directors-discretion-project-application/
- **Resources:** ~10% of Frontier hours per year; typical awards 15,000-20,000 node-hours
- **Rolling/Fixed:** Rolling, year-round applications
- **Scale:** Small to medium (preparation/scaling work)
- **Notes:** Good for preparing INCITE/ALCC proposals, benchmarking, code porting. Also "Pathways to Supercomputing" for HBCUs, HSIs, community colleges.

### ALCF Director's Discretionary + APEX Program
- **Provider:** Argonne National Laboratory
- **URL:** https://www.alcf.anl.gov/
- **Resources:** Aurora (exascale), Polaris. DD allocations for preparation work.
- **APEX Program:** Leadership-scale computing on Aurora + embedded ALCF staff/postdoc support. Most recent deadline: Feb 27, 2026. Duration: 2 years with 1-year renewal.
- **Rolling/Fixed:** DD is rolling; APEX has fixed deadlines
- **Scale:** DD = small/medium; APEX = large
- **Notes:** ALCF AI Testbed also provides access to Cerebras CS-2 and SambaNova DataScale systems for AI research.

---

## 2. Cloud Provider Academic Programs

### AWS Cloud Credit for Research
- **Provider:** Amazon Web Services
- **URL:** https://aws.amazon.com/cloud-credit-for-research/
- **Resources:** AWS promotional credits for EC2 (including GPU instances), S3, SageMaker, etc.
- **Scale:** Student awards up to $5,000; faculty/staff awards uncapped (typical review: 90-120 days)
- **Rolling/Fixed:** Rolling applications
- **Notes:** As of Feb 16, 2026, Free Tier accounts are ineligible for promotional credits. Credits expire after 1 year.

### Google Cloud Research Credits
- **Provider:** Google Cloud
- **URL:** https://edu.google.com/programs/credits/research/
- **Resources:** Compute Engine, Cloud Storage, BigQuery, TPU access credits
- **Scale:** Faculty/postdocs: up to $5,000; PhD students: up to $1,000
- **Rolling/Fixed:** Rolling
- **Notes:** Brief research proposal required. Quick turnaround.

### Google TPU Research Cloud (TRC)
- **Provider:** Google Research
- **URL:** https://sites.research.google/trc/about/
- **Resources:** Free access to 1,000+ Cloud TPU devices. Supports TensorFlow, PyTorch, JAX, Julia.
- **Scale:** Large -- significant TPU allocation on a temporary basis
- **Rolling/Fixed:** Rolling applications; invitations sent on rolling basis
- **Notes:** Participants expected to share research publicly (papers, open-source code, blog posts). Other GCP costs (VMs, storage) are minimal but not covered.

### Microsoft Azure for Research
- **Provider:** Microsoft
- **URL:** https://www.microsoft.com/en-us/azure-academic-research/
- **Resources:** Azure credits for proof-of-concept, migration, tool development. GPU VMs including A100s, H100s.
- **Scale:** Variable; through NAIRR channel up to $3.5M per grand challenge project
- **Rolling/Fixed:** Rolling
- **Notes:** Also available through NAIRR pilot partnership.

### Oracle for Research
- **Provider:** Oracle
- **URL:** https://go.oracle.com/research-project-award
- **Resources:** Oracle Cloud Infrastructure credits (compute, GPU, HPC, storage)
- **Tiers:**
  - **Cloud Starter Awards:** ~$750 in credits, no credit card needed
  - **Research Project Awards:** 12-month projects with substantial OCI credits
  - **Doctoral Project Awards:** Same as above plus networking/community opportunities for PhD students
- **Rolling/Fixed:** Rolling applications
- **Scale:** Small (starter) to medium (project awards)
- **Notes:** Non-revenue arm of Oracle. Selection based on project impact and OCI fit.

### IBM Academic Initiative / SkillsBuild
- **Provider:** IBM
- **URL:** https://www.ibm.com/academic/topic/cloud
- **Resources:** No-charge access to IBM Cloud, training materials, curriculum, and software
- **Rolling/Fixed:** Rolling
- **Scale:** Small to medium
- **Notes:** More education-focused than research-compute-focused. IBM Impact Accelerator RFP in 2026 for AI workforce development.

---

## 3. GPU / AI Hardware Company Programs

### NVIDIA Academic Grant Program
- **Provider:** NVIDIA
- **URL:** https://www.nvidia.com/en-us/industries/higher-education-research/academic-grant-program/
- **Resources:** Choose from:
  - Up to 30,000 NVIDIA H100 80GB GPU-hours (cloud compute)
  - Up to 8x NVIDIA RTX PRO 6000 GPUs (physical hardware)
  - Up to 2x NVIDIA DGX Spark supercomputers
- **Focus areas (2026):** Generative AI training/modeling, GenAI alignment/inferencing, simulation/modeling, robotics, autonomous vehicles, 5G/6G, federated learning
- **Rolling/Fixed:** Rolling; recent deadline was June 30 with September award decisions
- **Scale:** Medium to large
- **Notes:** Hardware grants ship physical GPUs to your lab. Very competitive.

### NVIDIA Applied Research Accelerator Program
- **Provider:** NVIDIA
- **URL:** https://cfr.gwu.edu/nvidia-applied-research-accelerator-program
- **Resources:** Up to $160K in hardware, cloud compute, and/or cash for converting research to production
- **Rolling/Fixed:** By invitation / application
- **Scale:** Large
- **Notes:** Requires commercial or government co-investment. More industry-partnership focused.

### NVIDIA Graduate Fellowship Program
- **Provider:** NVIDIA
- **URL:** https://research.nvidia.com/graduate-fellowships
- **Resources:** Up to $60,000 per award for PhD students + potential GPU access
- **Rolling/Fixed:** Annual; 2026-2027 deadline was Sept 15, 2025
- **Scale:** Medium (fellowship + compute)

### AMD Instinct Education and Research Initiative (AIER) 2.0
- **Provider:** AMD
- **URL:** https://www.amd.com/en/products/accelerators/instinct/aier.html
- **Resources:** AMD Instinct GPU access, ROCm software support
- **Eligibility:** Faculty, researchers, scientists at universities and non-profits
- **Rolling/Fixed:** Rolling
- **Scale:** Variable

### AMD AI & HPC Cluster Program
- **Provider:** AMD
- **URL:** https://www.amd.com/en/corporate/university-program/ai-hpc-cluster.html
- **Resources:** Compute nodes with dual AMD EPYC processors + AMD Instinct accelerators. Node-hour based allocations.
- **Rolling/Fixed:** Quarterly proposal submissions; access for up to 1 year
- **Scale:** Medium
- **Notes:** Must be non-profit research or academic institution. Open-source focus required.

### ALCF AI Testbed (Cerebras + SambaNova)
- **Provider:** Argonne National Laboratory
- **URL:** https://www.alcf.anl.gov/
- **Resources:** Cerebras CS-2 wafer-scale systems and SambaNova DataScale systems
- **Rolling/Fixed:** Proposals accepted on rolling basis
- **Scale:** Small to medium (exploratory)
- **Notes:** Intel acquired SambaNova in early 2026. Unique opportunity to test non-GPU AI accelerators. Apply through ALCF.

---

## 4. Tech Company AI Research Programs

### OpenAI Researcher Access Program
- **Provider:** OpenAI
- **URL:** https://openai.com/form/researcher-access-program/
- **Resources:** Up to $1,000 in OpenAI API credits
- **Rolling/Fixed:** Reviewed quarterly (March, June, September, December)
- **Scale:** Small (API credits, not raw GPU compute)
- **Notes:** Credits expire after 1 year. Cannot be extended or renewed. Good for LLM-based research.

### Anthropic External Researcher Access Program
- **Provider:** Anthropic
- **URL:** https://support.claude.com/en/articles/9125743
- **Resources:** Free API credits for Anthropic's model suite (Claude)
- **Focus:** AI safety and alignment research
- **Rolling/Fixed:** Rolling
- **Scale:** Small to medium (API credits)

### Anthropic Fellows Program (2026)
- **Provider:** Anthropic
- **URL:** https://alignment.anthropic.com/2025/anthropic-fellows-program-2026/
- **Resources:** ~$15,000/month in compute + $3,850/week stipend
- **Rolling/Fixed:** Fixed cohorts: May 2026 and July 2026 start dates
- **Scale:** Large (compute-wise)
- **Duration:** 4-month fellowships
- **Notes:** Highly competitive. Focused on AI safety research.

### Meta Research Awards
- **Provider:** Meta / FAIR
- **URL:** https://research.facebook.com/research-awards/
- **Resources:** Research funding (cash grants, some with compute)
- **Rolling/Fixed:** Periodic RFPs by topic area
- **Scale:** Variable
- **Notes:** No dedicated "GPU access program" found; Meta provides compute through research awards and direct collaborations.

### Google DeepMind Programs
- **Provider:** Google DeepMind
- **URL:** https://deepmind.google/education/
- **Resources:** Student Researcher Program (paid placement on DeepMind teams), Research Ready Programme, community compute grants
- **Rolling/Fixed:** Annual application cycles
- **Scale:** Variable
- **Notes:** Not a direct compute grant program for external PIs; more internship/collaboration-focused.

---

## 5. Startup / Emerging Provider Programs

### Lambda Labs Academic Discount
- **Provider:** Lambda Labs
- **URL:** https://lambdalabs.com/
- **Resources:** Cloud GPU access (H100, A100, etc.)
- **Scale:** 50% academic discount on cloud pricing
- **Rolling/Fixed:** Ongoing
- **Notes:** No formal grant program, but the academic discount makes Lambda one of the most cost-effective cloud GPU options for researchers.

### Lambda AI Research Grant
- **Provider:** Lambda Labs
- **URL:** https://lambda.ai/research
- **Resources:** Up to $5,000 in cloud credits for qualifying researchers
- **Rolling/Fixed:** Rolling
- **Scale:** Small

### Together AI Research Credits Program
- **Provider:** Together AI
- **URL:** https://www.together.ai/research-credits-program-request
- **Resources:** Small grants for student research projects (few hundred dollars in credits)
- **Rolling/Fixed:** Invite-only / rolling
- **Scale:** Small
- **Notes:** Good for inference-focused research on open-source models.

### Nebius Research Credits Program
- **Provider:** Nebius
- **URL:** https://nebius.com/nebius-research-credits-program
- **Resources:** Up to 8 GPUs for a full year on Nebius GPU cloud, or up to 10M tokens for inference
- **Rolling/Fixed:** Monthly application windows (2-week open periods), up to 6 winners/month
- **Scale:** Medium
- **Notes:** For researchers at accredited academic/non-profit institutions.

### Strong Compute Research Grants
- **Provider:** Strong Compute
- **URL:** https://strongcompute.com/research-grants
- **Resources:** GPU compute for AI research
- **Rolling/Fixed:** Rolling
- **Scale:** Variable (details limited)

### HOSTKEY GPU Grant Program
- **Provider:** HOSTKEY
- **URL:** https://hostkey.com/about-us/grants-for-scientific-projects-and-startups/
- **Resources:** GPU credits for data science projects
- **Rolling/Fixed:** Rolling
- **Scale:** Small to medium

### Gradient Research Grant
- **Provider:** Gradient
- **URL:** https://gradient.ai/research-grant
- **Resources:** Subsidized compute access for academic researchers
- **Rolling/Fixed:** Rolling
- **Scale:** Small

### Fal Research Grants
- **Provider:** fal.ai
- **URL:** https://fal.ai/grants
- **Resources:** Cloud credits for open-source AI advancement
- **Rolling/Fixed:** Rolling
- **Scale:** Small

### Prime Intellect Fast Compute Grants
- **Provider:** Prime Intellect
- **URL:** https://www.primeintellect.ai/blog/scaling-environments-program
- **Resources:** $500 to $100K in compute credits + ecosystem exposure
- **Rolling/Fixed:** Rolling
- **Scale:** Small to large

---

## 6. University / Consortium HPC Centers

### TACC (Texas Advanced Computing Center)
- **Provider:** UT Austin / NSF
- **URL:** https://tacc.utexas.edu/use-tacc/allocations/
- **Resources:** Stampede-3 (via ACCESS), Vista. Frontera winding down ~May 31, 2026. Horizon (successor) expected spring 2026.
- **Rolling/Fixed:** ACCESS allocations are rolling; TACC-direct LRAC allocations paused for Frontera
- **Scale:** Large
- **Notes:** Stampede-3 accessible through NSF ACCESS. Watch for Horizon LRAC announcements.

### Pittsburgh Supercomputing Center (PSC)
- **Provider:** CMU + Pitt / NSF
- **URL:** https://www.psc.edu/resources/allocations/
- **Resources:** Bridges-2 supercomputer (GPU + CPU nodes). Accessible via NSF ACCESS.
- **Rolling/Fixed:** Through ACCESS tiers
- **Scale:** Medium to large

### San Diego Supercomputer Center (SDSC)
- **Provider:** UC San Diego / NSF
- **URL:** https://www.sdsc.edu/
- **Resources:** Expanse supercomputer. Also hosts NAIRR pilot GPU resources. Accessible via ACCESS.
- **Rolling/Fixed:** Through ACCESS tiers
- **Scale:** Medium to large

### National Center for Supercomputing Applications (NCSA)
- **Provider:** UIUC / NSF
- **Resources:** Delta supercomputer (NVIDIA A100 + A40 GPUs). Accessible via ACCESS.
- **Rolling/Fixed:** Through ACCESS tiers
- **Scale:** Medium to large

### Ohio Supercomputer Center (OSC)
- **Provider:** State of Ohio
- **URL:** https://www.osc.edu/
- **Resources:** Owens and Pitzer clusters. Available to Ohio researchers; out-of-state via special arrangements.
- **Rolling/Fixed:** Rolling for Ohio researchers
- **Scale:** Medium

### National Labs User Programs
- **ORNL (Oak Ridge):** OLCF Director's Discretionary + Pathways to Supercomputing (see Section 1)
- **ANL (Argonne):** ALCF DD + APEX + AI Testbed (see Section 1)
- **LBNL (Lawrence Berkeley):** NERSC allocations (see Section 1)

---

## 7. International Programs (US Researchers Eligible)

### EuroHPC JU
- **Provider:** European High Performance Computing Joint Undertaking
- **URL:** https://www.eurohpc-ju.europa.eu/
- **Resources:** Access to European exascale/pre-exascale/petascale supercomputers. Free of charge.
- **Access modes:**
  - **Benchmark Access:** Rolling, monthly deadlines (1st of each month)
  - **Development Access:** Rolling, monthly deadlines
  - **Regular Access:** Fixed calls throughout 2026
  - **AI Access:** For publicly funded research and Horizon Europe projects
- **US Eligibility:** Limited. Researchers must be at institutions in EU Member States or Participating/Associated States. US researchers may be eligible through collaborations with European partners.
- **Scale:** Large

### Digital Research Alliance of Canada (formerly Compute Canada)
- **Provider:** Government of Canada
- **URL:** https://alliancecan.ca/
- **Resources:** HPC clusters (Cedar, Graham, Narval, Niagara), cloud, storage
- **US Eligibility:** Primarily for Canadian researchers. US collaborators may access through Canadian PI partnerships.
- **Scale:** Large

### ARCHER2 (UK)
- **Provider:** UKRI / EPSRC
- **URL:** https://www.archer2.ac.uk/support-access/access.html
- **Resources:** UK national HPC service (AMD EPYC-based). Service end date: Nov 21, 2026.
- **US Eligibility:** Limited. Access primarily for UK-funded researchers. International access possible through EPSRC-funded collaborations.
- **Scale:** Large

### International HPC Summer School 2026
- **Provider:** Multi-national (Pawsey, DRAC, EuroHPC JU, RIKEN, US partners)
- **URL:** Via NERSC/PRACE event listings
- **Resources:** Training + networking + HPC access. July 12-17, 2026 in Perth, Australia.
- **US Eligibility:** Yes -- US grad students and postdocs eligible to apply
- **Notes:** Not a compute grant, but excellent networking for future allocations.

---

## 8. Other Notable Programs

### Trelis AI Grants
- **Provider:** Trelis Research
- **URL:** https://trelis.com/trelis-ai-grants/
- **Resources:** Up to five $500 awards quarterly for AI model advancement
- **Rolling/Fixed:** Quarterly
- **Scale:** Small

### AI Grant
- **Provider:** AI Grant (independent)
- **URL:** https://aigrant.com/
- **Resources:** Grants for open-source AI projects
- **Rolling/Fixed:** Periodic batches
- **Scale:** Small to medium

### a16z Open Source AI Grant
- **Provider:** Andreessen Horowitz
- **URL:** https://a16z.com/supporting-the-open-source-ai-community/
- **Resources:** Non-dilutive funding for independent developers
- **Rolling/Fixed:** Periodic
- **Scale:** Small to medium

### Zoltan's FLOPs
- **Provider:** Independent
- **URL:** https://tcz.hu/zoltans-flops
- **Resources:** Mini-grant totaling $5,000 for GPU cloud projects
- **Rolling/Fixed:** Rolling
- **Scale:** Small

---

## Quick Reference: Recommended Strategy for a New Assistant Professor

1. **Immediate (this week):** Apply for NSF ACCESS Explore -- get GPU access within days with a 1-page abstract.
2. **Short-term (this month):** Apply for Google TRC (free TPUs), Google Cloud Research Credits ($5K), AWS Research Credits (uncapped for faculty).
3. **Medium-term (next quarter):** Submit NVIDIA Academic Grant Program proposal (H100 hours or physical GPUs). Apply for NAIRR pilot allocations.
4. **Large-scale (next cycle):** Prepare INCITE or ALCC proposals for DOE supercomputers. Apply for ACCESS Maximize.
5. **Opportunistic:** Check AMD AIER 2.0, Oracle for Research, Nebius credits, Lambda academic discount for supplemental compute.
6. **If AI safety focused:** Anthropic Fellows Program, OpenAI Researcher Access.
