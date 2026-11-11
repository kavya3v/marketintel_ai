# Evaluation and evidence record

Submission deadline: **November 11, 2026**. Evidence below separates historical
reports, saved-state observations, new offline checks, and unmeasured goals. No live
provider requests were made during submission preparation.

## Historical test milestone

**71 offline tests passing** was previously reported when the full verification,
checkpoint, approval and briefing workflow was completed. It is a historical
milestone, not the current suite size and not a measurement repeated at that old
code revision during this documentation pass. Report-presentation and regeneration
regressions were added afterward; a later development run reported 87 passing tests.

## Observed live Notion run

Source: the existing local SQLite checkpoint and the regenerated report, inspected
read-only. The database is not included in submission artifacts. The approved
Markdown sample is [examples/notion-competitor-briefing.md](../examples/notion-competitor-briefing.md).

| Observation | Recorded result | Interpretation |
|---|---|---|
| Target / industry | Notion / Productivity software | One observed scenario, not a benchmark dataset |
| Research timestamp | 2026-11-10 03:57:15 UTC (November 9, 2026, Pacific time) | Run timestamp, not a measured completion duration |
| Competitors | Airtable, Slite, MeisterTask | Real saved research results; no new searches in this preparation |
| Automatic repair cycles | 2 | Reached the configured automatic limit |
| Human revision requests | 0 | No evidence of revision use in this live run |
| Internally verified claim records | 64 | Textual evidence status; **not independently audited factual accuracy** |
| Unsupported claim records | 32 | Excluded from report factual comparisons |
| Inferred claim records | 4 | Not promoted to verified facts |
| Recorded gap entries | 33 | Raw entries can overlap/repeat; not 33 independent product deficiencies |
| Extraction warnings | 2 | Airtable and MeisterTask: extraction failed; evidence retained for review |
| Approval / terminal state | Approved; no pending nodes | Human approval recorded before report generation |
| Regenerated formatter | 2.0 | Deterministic saved-evidence report, with the original preserved |
| Numeric pricing / recent news | Missing/ambiguous rates disclosed; no qualifying dated news for these profiles | Lack of verified coverage does not prove absence of prices or announcements |

The counts total 100 recorded claim statuses for this run. The 64 internally verified
records must not be described as “64% accuracy”: there is no independent ground
truth, adjudication sample, or error-rate measurement. Approval is a workflow decision,
not proof that every accepted source statement is true.

The saved report retains warnings rather than inventing replacements. Slite and
MeisterTask custom enterprise pricing are not represented as zero. Airtable numeric
pricing is not verified in the saved findings. An undated historical funding entry
was removed from recent-news presentation by the report's date policy; no article
was fetched again to achieve this.

## Fresh submission verification

**Performed November 10, 2026 (Pacific time), using the existing `.venv`:**

| Check | Exact result |
|---|---|
| Full offline suite | **87 tests passed, 0 failures, 0 errors** |
| Reported unittest duration | **7.714 seconds** for this run; not research latency |
| Syntax | `compileall` succeeded; AST parsing passed for **24 Python files** |
| External socket attempts | **0**; external connections were blocked during the suite |
| Architecture diagram | All **14 edges** matched compiled graph introspection |
| Relative documentation file links | **19** checked successfully |
| Ignore-rule check | **29** private/local paths excluded; **9** submission paths allowed |
| Curated sample | Exact copy of the regenerated artifact; six credential/internal-data checks passed |
| Configured-secret scan | **35** submission candidate files checked; no configured secret values found |
| Saved checkpoint database | Byte-for-byte SHA-256 match before/after preparation |

Test counts by module:

| Module | Passing tests |
|---|---:|
| `test_app` | 4 |
| `test_discovery_agent` | 11 |
| `test_fireworks` | 14 |
| `test_full_workflow` | 6 |
| `test_phase2` | 13 |
| `test_recovery` | 6 |
| `test_report` | 3 |
| `test_report_presentation` | 12 |
| `test_report_regeneration` | 4 |
| `test_verification` | 12 |
| `test_workflow_ui` | 2 |
| **Total** | **87** |

Expected fixture failure logs and Streamlit's bare-mode `missing ScriptRunContext`
warnings appeared; no test failure resulted. No measured result above is a live
research performance or correctness metric.

Commands use the existing environment:

```powershell
.\.venv\Scripts\python.exe -m compileall -q app.py src tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The preparation test runner additionally blocks external socket connections while
allowing localhost sockets needed by Streamlit AppTest. It records connection
attempts. Tests use injected Tavily/Fireworks responses and temporary SQLite
databases. Their runtime is not an end-to-end research latency measurement.

Coverage includes discovery validation, safe failures, bounded retries, exact
decimal prices, negation, billing-unit conflicts, retained evidence, unsupported
citations, partial failures, missing news, SQLite reopening in a fresh Python
process, interrupt/resume, approval/rejection, revision bounds, report date windows,
ambiguous pricing, Markdown safety, and regeneration authorization/idempotency.

## Unmeasured success targets

These are evaluation goals, **not achieved measurements**:

| Proposed target | How it would be measured | Current status |
|---|---|---|
| High factual precision | Independent reviewers label sampled claims and citation entailment | Not measured; no precision/recall claim |
| Reliable competitor relevance | Multiple target companies and a curated relevance rubric | Not measured beyond one observed run |
| Acceptable runtime and cost | Instrument wall time, tool attempts, tokens and provider charges | Not measured; no latency or dollar target claimed achieved |
| Broad pricing/news coverage | Ground-truth page/date inventory over multiple vendors | Not measured; observed gaps remain |
| User usefulness | PM participants complete a decision task and rate reports | Not measured; recommendations are hypotheses |
| Crash-safe exactly-once calls | Fault injection during provider calls and restart analysis | Not guaranteed; checkpointing is at node boundaries |

Offline tests demonstrate implementation behavior under their fixtures; they do not
establish provider availability, source reliability, market coverage, or business value.

## Reproducibility and submission limits

- The inspected Python version is 3.11.9. Installed libraries are recorded in the
  README; dependency ranges do not freeze a fully reproducible environment.
- The curated sample can be reviewed without credentials or network access. The
  local saved-run UI requires the private database on this machine; it is excluded
  from Git and must not be represented as bundled with a fresh checkout.
- No new paid API call, checkpoint mutation, approval decision, or report regeneration
  was performed during documentation preparation.
- At documentation preparation time the folder had no `.git` metadata. Ignore patterns
  were tested independently; that preparation did not certify an existing Git index
  or repository history.
