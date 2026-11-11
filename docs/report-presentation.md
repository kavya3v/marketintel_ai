# Saved-evidence briefing presentation

Report formatting is deterministic. It makes no Fireworks or Tavily calls and
does not alter verification classifications. The existing LangGraph briefing node
uses this formatter after human approval; the approval interrupt is unchanged.

## Regenerate the approved Notion run

1. Restart or refresh Streamlit after the code update:

   ```powershell
   .\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8501
   ```

2. Load saved run `0e9d10d0-f20f-4d7a-8f8c-8ad29d5c8f45` using its existing URL or
   **Saved research run ID** and **Load Saved Run**. Do not start new research.
3. Scroll to **Approved competitor briefing** and click
   **Regenerate Briefing from Saved Evidence**.
4. Download the improved Markdown report. **Preserved original report** provides
   the original Markdown download. Prior versions remain in `report_history` in
   the same SQLite thread; `original_report` preserves the first replaced report.

Regeneration requires an approved run with no pending graph execution or interrupt.
It calls the formatter and checkpoints only the terminal briefing update with
`graph.update_state(..., as_node='briefing')`. It never invokes or resumes a graph,
reruns a research agent, or repeats approval. The existing per-run lock protects
concurrent clicks. Identical content/evidence/formatter metadata returns the saved
state without creating another checkpoint or archive entry. Report fingerprints
cover the formatting inputs, and the formatter version is persisted.

## Presentation rules

- Executive highlights describe competitor-specific documented emphases with PM
  implications labeled as hypotheses. They do not establish missing Notion features.
- Comparison uses up to three verified capability excerpts per competitor; detailed
  profiles use up to five. Complete verified context is retained, including plan,
  role and eligibility restrictions. Context that cannot safely fit is omitted rather
  than paraphrased or truncated mid-claim. Coverage can be below these limits when
  verified evidence is insufficient.
- Duplicate excerpts are removed per field, whitespace and extraction artifacts
  normalized, and Markdown control characters escaped. Global numbered source
  references avoid repeating long URLs in every paragraph.
- Pricing parses only saved verified pricing context. Exact amount strings preserve
  decimals and currency symbols. No currency code is inferred from a dollar sign.
  Plan, currency and billing terms appear only when explicit in that excerpt.
  Free, subscription, custom enterprise and unknown models are distinguished.
  Custom never means zero; missing numeric rates remain **Not verified**.
  Multiple rates or distinct plans in one excerpt have ambiguous associations and
  are withheld, including a Free plan followed by a paid plan's single rate.
- News requires a saved verified publication date in the inclusive 90-calendar-day
  window ending at the research date. Future, undated and stale items are omitted.
  Old ISO-dated funding events are excluded even if their directory entry has a
  newer publication date. Empty coverage says **No verified recent news found.**
- Strategic actions use verified capabilities as observations. Implications and
  proposed next steps are hypotheses to test, not customer-demand or superiority
  claims. Three to five insights are generated when evidence supports that many;
  the formatter does not fabricate observations to fill a quota.
- Quality counts show saved statuses before presentation deduplication. Gaps,
  extraction failures, missing numeric prices and missing dated news are disclosed.

## Limits

The formatter trusts saved verification decisions and does not reverify historical
claims. It cannot repair missing evidence or establish independent accuracy of
vendor marketing. Regex-based pricing parsing deliberately omits ambiguous tables,
unrecognized plan names, and unavailable terms. Dates are based on saved metadata,
not article fetching. No live requests were made to implement or preview this change.
The existing Notion checkpoint/report was inspected read-only and was not regenerated
automatically; the new UI action is required to persist an improved version.
