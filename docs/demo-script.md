# Five-minute saved-evidence demonstration

Goal: demonstrate the implemented multi-agent workflow and its limitations without
waiting for paid research calls. The timed script totals **5:00**. Do not pretend
the completed run is executing live.

## Before the timer

- Start Streamlit with the existing `.venv`:

  ```powershell
  .\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8501
  ```

- Open http://localhost:8501. Retain the local `.marketintel` database. Load run
  `0e9d10d0-f20f-4d7a-8f8c-8ad29d5c8f45` through **Saved research run ID** and
  **Load Saved Run**, or its existing `?run=...` URL.
- Have [the architecture diagram](architecture.md), [evaluation record](evaluation.md)
  and [static sample](../examples/notion-competitor-briefing.md) available.
- Do not click **Run Full Research**, **Discover Competitors**, **Generate Research
  Profiles**, **Continue Saved Run** or **Request Revision**. These can execute
  provider calls. No credentials should appear on screen.
- If the local database is unavailable, use the static sample throughout and say
  clearly that checkpoint/UI behavior is being explained, not executed.

## 0:00–0:30 — Problem and outcome (30 seconds)

Show the project title and saved Notion target.

Say: “MarketIntel AI turns competitor discovery into a source-linked briefing.
This is a completed saved run, not a new live search. It researched Airtable,
Slite and MeisterTask and records uncertainty instead of inventing missing facts.”

## 0:30–1:05 — Actual orchestration (35 seconds)

Show the Mermaid diagram in `architecture.md`.

Point to discovery, web research, extraction and verification; then the targeted
repair loop and human-review interrupt. Explain that existing competitors skip
discovery and unresolved gaps stop looping after two automatic repairs. Do not
claim a supervisor, adaptive graph edge, or agent absent from the diagram.

## 1:05–1:45 — Durable saved state (40 seconds)

Show the run ID, approved status and counters in Streamlit.

Say: “The run UUID is the LangGraph thread ID. SQLite keeps evidence, profiles,
verification findings and approval state. Loading this run reads saved state;
it does not repeat a search. Two automatic repairs and zero human revisions are
recorded here. Checkpoints commit at nodes, so an unfinished node can repeat work
after a process crash.”

## 1:45–2:30 — Evidence quality and failures (45 seconds)

Show one verification summary and the warnings/gaps panel. Do not open external
source URLs during this offline demo; the report already preserves them.

Say: “The saved statuses are 64 internally verified, 32 unsupported and four
inferred claims. These are not external accuracy scores. There are two extraction
warnings, for Airtable and MeisterTask; available evidence was retained. The code
tests exact decimal matching, so ten dollars does not validate against ten ninety-nine.”

Point out a missing/unsupported price or news item rather than hiding it.

## 2:30–3:10 — Human review, honestly demonstrated (40 seconds)

Show the saved **approved** status. The completed run intentionally does not show
pending approval buttons.

Say: “Before reporting, `interrupt()` paused the review node. Approve, Request
Revision and Reject resume with `Command` and the same thread ID. This run is already
approved, so I am not repeating approval or requesting new research. Offline tests
exercise all decisions, stale tokens and revision limits. Approval cannot turn an
unsupported claim into a fact.”

Do not change the approved record to manufacture an interrupt demonstration.

## 3:10–4:10 — Report and product-management value (60 seconds)

Show the executive highlights, competitor comparison, pricing and recent-news sections.

Explain the documented emphases: Airtable's app/data workflows, Slite's knowledge
base, and MeisterTask's work-management evidence, citing the wording in the sample
rather than asserting exclusive capabilities. Show the hypotheses/recommended next
steps and the disclaimer that no Notion feature gap has been established.

Show that custom pricing is not zero and missing numeric prices say **Not verified**.
News requires a verified publication date within the report's 90-day window;
the sample reports **No verified recent news found** rather than reusing stale funding.

## 4:10–4:40 — Safe regeneration and download (30 seconds)

Show **Regenerate Briefing from Saved Evidence**, the Markdown download, and
**Preserved original report**. To keep the checkpoint untouched during this
submission walkthrough, point to regeneration without clicking it; download the
existing report or open the curated sample.

Say: “Regeneration is an explicit approved-only action. It formats the existing
verified evidence without Tavily, Fireworks, or another approval. It preserves the
original and prior reports. Identical regeneration is idempotent.”

## 4:40–5:00 — Evaluation and limits (20 seconds)

Show the fresh test result in `evaluation.md` and distinguish it from the historical
71-test milestone.

Say: “Tests cover control flow and failure cases with mocks, not research accuracy.
This submission includes one observed research run and a static sample. Latency,
cost and external factual precision are not measured. The main next evaluation
step is independent review across more companies.”
