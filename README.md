# MarketIntel AI

A Python + LangGraph competitor research system with a Streamlit interface.
It discovers up to three competitors, collects web evidence, extracts structured
profiles, checks claims against sources, requests human approval, and produces a
downloadable Markdown briefing. Missing evidence remains **Not verified**.

Prepared for submission on **November 11, 2026**. This repository documents an
implemented prototype and its observed results, not independently validated market research.

- [Architecture and actual graph](docs/architecture.md)
- [Evaluation: observations, tests, and unmeasured targets](docs/evaluation.md)
- [Five-minute saved-evidence demo](docs/demo-script.md)
- [Sample Notion briefing](examples/notion-competitor-briefing.md)
- [Full workflow operation](docs/full-workflow.md)
- [Report formatting and regeneration](docs/report-presentation.md)

## Setup and execution

Use the existing `.venv`; no new environment is required. The inspected environment
uses Python 3.11.9, LangGraph 1.2.20, SQLite checkpointer 3.1.3, Streamlit 1.67.0,
langchain-fireworks 1.7.2, and tavily-python 0.8.5. `requirements.txt` specifies
compatible version ranges rather than a reproducible lockfile.

For a reviewer starting from a fresh checkout, virtual environments are deliberately
not bundled: provision a Python 3.11 environment named `.venv` first. The preparation
on this machine reused its existing environment and did not create another one.

From the project directory in a normal PowerShell terminal with network access:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8501
```

Open the URL printed by Streamlit, normally http://localhost:8501. Stop an existing
server with Ctrl+C before restarting. Bare `python` can resolve to an inaccessible
Windows alias on this machine; use the explicit `.venv` interpreter above.

Configure the local, ignored `.env` using `.env.example` as a blank template:

```dotenv
TAVILY_API_KEY=
FIREWORKS_API_KEY=
FIREWORKS_MODEL=
```

Supply your own provider keys and a model/deployment ID enabled for inference in
your Fireworks account with JSON mode support. There is no implicit model default.
Do not submit the populated `.env`. Both workflow paths load the project-root `.env`;
existing process environment variables take precedence. Restart after changing it.

**Fresh research calls paid external services.** Use saved evidence or the sample
for a predictable demonstration. Loading, approval, report formatting, regeneration,
and downloads do not call research providers. Request Revision and Continue Saved
Run can call providers; they require explicit user actions.

## Agents and tools

| Agent/stage | Implementation | Responsibility |
|---|---|---|
| Competitor discovery | `src/discovery_agent.py` | Fireworks query planning, Tavily search, structured competitor selection and evidence checks |
| Web research | `src/research_agent.py` | Pricing, features, positioning/customer use cases, news; official-page extraction and bounded follow-up |
| Intelligence extraction | `src/extraction_agent.py` | Fireworks JSON-mode profiles validated with Pydantic |
| Evidence verification | `src/verification_agent.py`, `src/evidence.py` | Deterministic quote/citation checks, numeric boundaries, pricing context, conflicts, missing evidence and inference labels |
| Human review | `src/full_workflow.py` | LangGraph interrupt, approval, rejection and bounded revision |
| Briefing/report | `src/report_agent.py` | Deterministic presentation of approved evidence, comparisons, pricing, dated news, hypotheses and limitations |

Tavily Search and Extract retrieve evidence; Fireworks supplies the LLM; LangGraph
orchestrates typed state; the official SQLite checkpointer stores runs; Pydantic
validates model outputs; Streamlit presents results and review controls. The
verification and report agents use Python rules, not additional LLM calls.

## LangGraph control flow

The complete graph is defined in `src/full_workflow.py`:

`discovery → web_research → extraction → verification → prepare_review → human_review → briefing`

Conditional routes skip discovery when competitors already exist, end safely on
discovery failure, repair evidence gaps before review, and handle approve/revise/reject
decisions. Verification can route to `targeted_research → extraction → verification`
for at most two automatic repairs. Human review allows at most two additional
revision requests; exceeding that limit or rejecting ends without an approved report.
The exact nodes, fourteen edges, and routing predicates are documented in
[architecture.md](docs/architecture.md).

The original discovery-only graph and Phase 2 research/extraction graph remain
available through **Discover Competitors** and **Generate Research Profiles**.
Those debug paths do not provide the full graph's durable approval/report workflow.

## Persistent state and human approval

Each full run uses a stable UUID as LangGraph `thread_id`. SQLite checkpoints live
locally in `.marketintel/checkpoints.sqlite`; this directory is excluded from Git.
State includes competitor selections, evidence and source history, profiles,
verification results, gaps, retry/repair/revision counts, review history, and reports.
Provider clients and API keys are not passed into graph state.

The run ID appears in the page URL. After a rerun or restart, retain that URL or
enter the ID in **Saved research run ID** and select **Load Saved Run**. Loading is
read-only with respect to graph execution. **Continue Saved Run** explicitly resumes
unfinished execution. Ordinary Streamlit reruns do not repeat searches.

`interrupt()` pauses `human_review`. **Approve**, **Request Revision**, and **Reject**
resume with `Command(resume=...)` and the same thread ID. Review tokens reject stale
or duplicate decisions; a per-run OS file lock prevents concurrent start/resume
operations. Reports require approval even when evidence is incomplete. Approval
does not promote unsupported claims or fill missing values.

**Regenerate Briefing from Saved Evidence** is available for completed approved runs.
It formats the saved evidence and checkpoints the terminal briefing update without
executing other nodes or repeating approval. The original report and prior versions
are preserved. Repeating identical regeneration does not add another checkpoint.

Checkpoints commit at node boundaries. A process crash inside an unfinished node
can repeat that node's calls on continuation; this is not exactly-once tool execution.

## Error recovery and runtime limits

- Fireworks uses explicit JSON mode (`response_format={"type":"json_object"}`),
  schema instructions, and local Pydantic validation. It allows one output repair
  and at most two transient retries, with three calls total per invocation.
- Transient Fireworks failures use 0.5/1-second backoff. HTTP 401/403/404 and network
  permission failures are not retried. Logs distinguish HTTP errors, rate limits,
  timeouts, connection failures, JSON syntax and schema validation failures.
- Discovery Tavily searches have at most two transient retries. Each competitor
  research pass has five search attempts total and one extract batch of up to four
  URLs; search/extract allow one transient retry. Search/extract timeouts are 20
  seconds in research; discovery search uses 40 seconds; Fireworks uses 45 seconds.
- Search ledgers and source history retain successful work. Repairs target gap
  categories. Extract failures retain search snippets, and per-competitor failures
  do not discard other competitors' completed research.
- Diagnostic logs exclude keys, authorization headers, full payloads and raw
  exception bodies. Exception chaining retains the underlying failure for debugging.

## Data sources and evidence policy

Research prioritizes the discovered vendor hostname and subdomains for pricing and
features; news searches can include external publications. Sources retain URL,
title, snippet, category, retrieval time, official-domain flag, and publication
date when available. Hostname matching is not proof of domain ownership.

Claims must cite retrieved URLs and match supporting text. Exact decimal matching
rejects `$10` against `$10.99`; comparable official pricing disagreements are flagged.
Verified, unsupported, conflicting, missing and inferred statuses remain distinct.
Strategic inferences never become facts merely by having a citation.

The formatter retains restrictive context, omits claims it cannot shorten safely,
and withholds ambiguous plan/rate associations. Currency symbols do not establish
currency codes. Custom pricing never means zero. Recent-news presentation requires
a verified date within 90 calendar days of research; the collection query itself
searches the last month, so 90-day collection coverage is not guaranteed.

## Prompts and instructions

Prompts are versioned in source, not hidden configuration:

| Location | Key instructions |
|---|---|
| `discovery_agent.py`: query planning | One to three focused competitor queries; company/industry are data |
| `discovery_agent.py`: selection | Up to three direct competitors, exact returned URLs, explicit source names, no guessed facts/domains |
| `research_agent.py`: follow-up | At most one targeted query to fill source gaps, preferring official evidence |
| `extraction_agent.py` | Exact quotes/citations, official pricing/features, explicit inference labels, missing data as Not verified, no invented news dates |
| `JsonResponseModel` | Return only JSON matching the Pydantic schema; bounded invalid-output repair |

Retrieved content is explicitly treated as untrusted data rather than instructions.
Verification, graph routing, review authorization and formatting are deterministic
Python controls; they do not rely on prompt compliance alone.

## Iterations and learnings

1. Replaced a temporary Streamlit test page with real discovery and offline tests.
2. Diagnosed an inaccessible legacy model (HTTP 404); the account-selected DeepSeek
   model later returned successful JSON planning. Availability is account-dependent.
3. Traced recurring connection failures to a restricted server launch ending in
   `PermissionError(errno=13)`, rather than assuming a prompt/model regression.
4. Added research/extraction, then verified-evidence repair, SQLite persistence,
   human review and approved-only reporting. Fixed numeric prefix, negation,
   billing-unit conflict, and overwritten-evidence defects with regression tests.
5. Replaced long excerpt reports with concise comparisons, strict news filtering,
   and preserved/versioned regeneration. The original download stayed unchanged
   until regeneration explicitly updated the saved report.

Key lessons: a valid URL is not proof of a claim; structured JSON is not factual
accuracy; checkpoints do not eliminate in-node repetition after a crash; and a
reliable demo should disclose gaps instead of silently substituting invented data.

## Testing and evaluation

```powershell
.\.venv\Scripts\python.exe -m compileall -q app.py src tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use mock providers, temporary SQLite databases and Streamlit AppTest. They
cover discovery, failures/retries, precision, citations/conflicts, partial results,
checkpoint reopening in a fresh process, interrupt/resume, approval/rejection,
revision limits, report filtering, regeneration authorization and UI idempotency.

**71 passing tests** is a previously reported milestone. The fresh submission
verification result and its date are recorded in [evaluation.md](docs/evaluation.md).
The saved live Notion run covers Airtable, Slite and MeisterTask with two repairs,
64 internally verified, 32 unsupported and four inferred claims, plus two extraction
warnings. These are observed internal outcomes, not external accuracy measurements.

## Limitations and submission hygiene

- Verification is conservative textual checking, not exhaustive semantic or
  independent factual validation. Vendor claims can remain biased or incomplete.
- Complex pricing tables, locale-specific amounts, negation/context subtleties,
  incomplete news metadata and stale evidence still require human review.
- No benchmark measures end-to-end accuracy, latency, token cost, reproducibility
  across companies, or business impact. A single observed run cannot establish these.
- Local SQLite is not a hosted multi-tenant service. No authentication, encrypted
  checkpoint storage, or cloud deployment is supplied. Version ranges are not a lockfile.
- `.env`, private credentials, SQLite files, virtual environments, raw local reports,
  and checkpoint manifests are excluded by `.gitignore`. Only the curated report in
  `examples/` is intended as sample output. A shared checkout does not include the
  local saved run database; use the static sample when it is unavailable.
- At documentation preparation time this folder had no `.git` repository. Ignore rules do not remove
  previously tracked secrets in another repository; inspect its index before submission.

No commit, push, checkpoint modification, or external API call is part of the
submission-documentation preparation.
