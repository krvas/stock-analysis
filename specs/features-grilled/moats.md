# Spec: Moats

- **Status:** ready for agent, not built
- **Depends on:** none of the other grilled specs. Moats reads no adjusted figures and feeds no other page.
- **Related docs:** `CONTEXT.md` (Moat, Moat Verdict and the six moat terms), `specs/vision.md` ("Moats"; "Risks & Moat Widening duty" under Further Scope), `specs/STATE.md` (hard rules; stale on the AI task layer, so trust the code), the One-line Answers page (prior art, end to end).

## Problem Statement

The Business Quality › Moats sub-page exists in the wizard nav but renders "not implemented". The investor wants to know which of the six Moats the company has and how strong each one is, without reading five years of 10-Ks by hand. Judging moats is qualitative and nothing downstream consumes it, so a careful AI reading of the filings that shows its reasoning and sources is enough. One moat type, Legal / Patent, is easy to overrate: patents and licences can be infringed and they expire. The page has to say so whenever the AI grades it Strong.

## Solution

The Moats sub-page asks the AI, through the same task pipeline and cache as One-line Answers, to grade each of the six Moats (Low Cost, Legal / Patent, Brand, Complexity, Risk, Attention to Detail) for the company with a Moat Verdict of None, Weak or Strong. Each moat comes back with a justification of a few sentences and a list of sources, each citing a fiscal year and 10-K Item.

The page lists the six moats in a fixed order. Each shows its name, its definition (the same text the AI uses as its rubric) and its Moat Verdict. The summary/standard/detailed view switch from One-line Answers controls detail: the detailed view adds the justification and the list of sources. When Legal / Patent is graded Strong, the page shows a warning under it that such moats can be illegally replicated and are not permanent. While the AI is still working, the page shows the shared "being generated, refresh later" notice. On the quarterly period the page shows an "annual only" notice.

The investor enters nothing. Nothing is stored except the AI cache.

## User Stories

1. As the investor, I want the Moats sub-page under Business Quality to render real content instead of "not implemented", so that I can judge business quality inside the wizard.
2. As the investor, I want the six Moats always listed in the same order (Low Cost, Legal / Patent, Brand, Complexity, Risk, Attention to Detail), so that I can compare companies at a glance.
3. As the investor, I want each moat to show a Moat Verdict of None, Weak or Strong, so that I get a clear grade rather than a vague narrative.
4. As the investor, I want each moat's definition shown next to its name, so that I know exactly what is being graded.
5. As the investor, I want the definition I read on the page to be the same rubric the AI was given, so that the grade and the guidance cannot drift apart.
6. As the investor, I want Low Cost defined as structurally lower cost from any source (scale, labour, location, process), so that a labour-cost edge like Balkrishna Tyres' counts even though it is not scale economics shared.
7. As the investor, I want Legal / Patent defined as protection by law (patents, licences, regulation) that is usually not a good moat, so that the AI does not overrate it.
8. As the investor, I want the AI to be allowed to grade Legal / Patent Strong when the filings support it, so that real legal protection is not hidden.
9. As the investor, I want a warning shown whenever Legal / Patent is graded Strong, saying that such moats can be illegally replicated and are not permanent, so that I discount it properly.
10. As the investor, I want that warning shown in every view (summary, standard, detailed), so that I cannot miss it by choosing the compact view.
11. As the investor, I want no warning when Legal / Patent is None or Weak, so that the page is not cluttered with irrelevant caveats.
12. As the investor, I want Brand defined with the note that it works best for frequent, low-value purchases, so that the AI weighs brand strength by purchase type.
13. As the investor, I want Complexity to cover both a product or process that is hard to copy and an integration that is costly for the customer to replace, so that both kinds of hard-to-replicate business are graded under one moat.
14. As the investor, I want the moat formerly called "Safety" to be called Risk, defined as the risk a customer takes by buying from an unbranded new entrant instead of the incumbent, so that it covers reliability and failure cost, not only physical safety.
15. As the investor, I want Attention to Detail defined as many small operating advantages that add up, so that the AI can recognise execution-based moats.
16. As the investor, I want each moat's justification to be longer than a One-line Answers justification (a short paragraph), so that I can follow the AI's reasoning.
17. As the investor, I want each moat to list several sources instead of one, so that I can check the verdict against more than one passage.
18. As the investor, I want each source to name the fiscal year and the 10-K Item, so that I can find the passage in the filing.
19. As the investor, I want each source to carry a short quote from the filing, so that I can see the evidence without opening the 10-K.
20. As the investor, I want a summary view that shows only names, definitions, verdicts and the Legal / Patent warning, so that I can scan quickly.
21. As the investor, I want the detailed view to add each moat's justification and sources, so that I can audit a verdict when I care.
22. As the investor, I want the view switch to work exactly like One-line Answers (same control, same `view` query parameter, unknown values fall back to standard), so that the wizard behaves the same everywhere.
23. As the investor, I want the AI to read all the cached 10-K years, not only the latest, so that a verdict reflects durability over time.
24. As the investor, I want the AI answer cached against the latest 10-K accessions, so that reloading the page is instant and costs nothing.
25. As the investor, I want the cache invalidated automatically when a new 10-K is filed, so that verdicts follow the latest filings.
26. As the investor, I want a "being generated, refresh later" notice while the AI is working, so that I know the page is not broken.
27. As the investor using the Claude Code backend, I want the Moats request to show up in the pending-requests listing like any other AI task, so that a Claude Code session can answer it.
28. As the investor using the OpenRouter backend, I want Moats to use the default model unless I configure a per-task model, so that I control cost the same way as for other tasks.
29. As the investor, I want an AI answer that does not match the schema (bad verdict, missing moat, malformed sources) to be thrown away and asked for again, so that the page never shows half-valid data.
30. As the investor, I want an "annual only" notice when I open Moats on the quarterly period, so that I understand why there is no quarterly content.
31. As the investor, I want Moats to need no inputs from me, so that the page costs me only reading time.
32. As the investor, I want Moats to need no database setup, so that it works on a fresh database without a reset.
33. As the investor, I want no moat trend or "widening" judgement on this page, so that I am not shown a feature that has not been designed yet.
34. As a future maintainer, I want the six moat definitions kept in one place (the task's result model), so that renaming or rewording a moat is a one-place change.
35. As a future maintainer, I want the Legal / Patent warning rule decided in the context builder rather than only in markup, so that it can be tested without rendering HTML.
36. As a future maintainer, I want the Moats context builder in its own Business Quality sub-page module, so that later Business Quality sub-pages (e.g. ROCE) live next to it and shared files stay generic.

## Implementation Decisions

### AI task: Moats

- A new AI task module in the AI tasks package defines a `MOATS_TASK` constant (an `AiTask`, name `moats`). The name keys the cache entry, the Claude Code request file and the OpenRouter per-task model lookup (default model unless configured). No change to the runner, backends, workspace or pending listing.
- Result model (Pydantic), one field per moat in fixed order. Each field's description holds that moat's definition. That text is both the AI's rubric (it goes into the JSON schema the agent sees) and the page's guidance text, the same pattern One-line Answers uses for questions as labels.
  - `low_cost`, `legal_patent`, `brand`, `complexity`, `risk`, `attention_to_detail`: each a `MoatAssessment`.
  - `MoatAssessment`:
    - `verdict`: a `Literal` of the strings `"None"`, `"Weak"`, `"Strong"` (the Moat Verdict; the string `"None"` is not Python `None`).
    - `justification`: a short paragraph (roughly 3–6 sentences) grounded in the filings.
    - `sources`: a list of `MoatSource`, at least one item; the instructions ask for every passage relied on, normally several.
  - `MoatSource`: `fiscal_year` (text such as "FY2025"), `item` (10-K Item with its name, e.g. "Item 1 (Business)"), `quote` (a short verbatim excerpt, one or two sentences).
- Definitions (the field descriptions, in display order):
  1. **Low Cost**: the company can produce or deliver at a structurally lower cost than rivals, from any source: scale, labour, location or process. Scale economics shared is one form of it, not the definition (e.g. Balkrishna Tyres' labour-cost advantage is Low Cost but not scale economics shared).
  2. **Legal / Patent**: protection granted by law (patents, licences, regulation). Usually not a good moat: it can be infringed and it expires, so it is never permanent even when Strong.
  3. **Brand**: customers prefer the name itself. It works better for frequent, low-value purchases than for rare, high-value ones.
  4. **Complexity**: anything that makes the business hard to replicate. That covers a product or process that is hard to copy, and an integration that is costly for the customer to replace.
  5. **Risk**: the risk a customer takes by buying from an unbranded new entrant instead of the incumbent (safety, reliability, failure cost), which keeps customers with the incumbent.
  6. **Attention to Detail**: many small operating advantages that add up to something rivals cannot match by copying any single one.
- Task instructions tell the AI to:
  - grade each moat in the schema using its field description as the rubric;
  - read every year in the workspace and prefer moats that persist across years;
  - give None when the filings show no evidence;
  - use Strong for Legal / Patent only when the protection is clearly material and still in force;
  - write a justification of a short paragraph;
  - cite each source with fiscal year, Item and a short verbatim quote.

### Context builder

- A new Business Quality sub-page module in the wizard pages package holds `moats_context(ticker, period)`. That keeps the shared files free of moat-specific logic.
- Behaviour:
  - `period == "quarterly"`: return the annual-only flag. Do not call `run_task`.
  - Otherwise call `run_task(MOATS_TASK, ticker)`. When pending, return `{"ai_pending": True}`. That is the same key One-line Answers uses, so the shared pending partial renders.
  - When ready, return `moats`: a list in field order. Each entry holds the moat name, its definition (the field description), the verdict, the justification, the sources (list of fiscal year / item / quote) and a `warning`: the Legal / Patent warning text when that moat is `legal_patent` and its verdict is `"Strong"`, otherwise `None`.
- The display name per moat (e.g. "Legal / Patent", "Attention to Detail") comes from the result model, as each field's title, so names and definitions live in one place.
- **Legal / Patent warning rule (exact):** show the warning if and only if the moat is Legal / Patent and its Moat Verdict is Strong. Text: "Legal and patent moats are subject to illegal replication and are not permanent." The rule and the text are domain constants of this sub-page and live in the Business Quality module.

### Registry and template

- Registry: the existing Moats `SubPage` entry (Business Quality, order 1) gets `context_builder` pointing to `moats_context`. No `post_handler`, because nothing is saved. Identity only; no other registry change.
- New sub-page template for Business Quality › Moats extending the wizard base sub-page:
  - Annual-only flag → the annual-only notice.
  - `ai_pending` → the shared AI pending partial.
  - Otherwise → the shared view-select partial (same three options, same fallback to standard), then one block per moat: name, definition, verdict, and the warning if present (all views). In the detailed view, the block adds the justification and a list of sources, each rendered as "FY · Item — "quote"".
- Styling reuses the existing answers / detail / notice classes in the wizard stylesheet where they fit. A small verdict badge and a warning style may be added to that stylesheet, with no JS.

### Not touched

- No new database table and no change to the wizard schema or `valuation_inputs`.
- No `fetch()`, no Table payload (nothing tabular), no adjustment type, no metrics-module function.

## Testing Decisions

- Good tests check external behaviour: the context dict the builder returns and the HTML a GET returns. Nothing calls an LLM or EDGAR. `run_task` is stubbed exactly as in the One-line Answers tests.
- Prior art: the One-line Answers tests (builder with `run_task` monkeypatched to return a ready or pending `AiResult`; GET via `TestClient` for each view) and the AI tools tests (`AiTask.parse`, runner caching with a fake backend).

### Proposed seams (pending user confirmation)

1. **Primary (one seam): the Moats context builder with `run_task` stubbed**, plus GET of the Moats sub-page through `TestClient` for rendering. Covers:
   - ready: six moats in fixed order, each with name, definition equal to the field description, verdict, justification and sources;
   - Legal / Patent Strong → warning present, and present in the summary-view HTML; Legal / Patent Weak or None → no warning; another moat Strong → no warning;
   - pending → `{"ai_pending": True}` and the pending notice in HTML;
   - quarterly → annual-only notice, and `run_task` is not called;
   - views: summary hides justification and quotes; detailed shows them, with fiscal year and Item; a bogus view falls back to standard;
   - every moat field has a non-empty description and title.
2. **Secondary, only if the user wants schema-level coverage: `MOATS_TASK.parse`** on a JSON answer (fenced and unfenced). A valid answer parses. A verdict outside None / Weak / Strong, a missing moat, or an empty sources list raises a validation error. This reuses the existing `AiTask.parse` seam; runner, cache and backends are already covered and are not re-tested.

## Out of Scope

- **Human input of any kind** (overriding a verdict, editing a justification, adding a moat). It would force a DB design; explicit future scope.
- **Moat trend / Moat Widening** (whether a moat is getting wider or narrower over time, and the paired risks sub-pages in `specs/vision.md`). Future scope.
- **Quarterly** content (the page shows an annual-only notice). Future scope, as for all pages.
- Moats beyond the fixed six, or a configurable moat list.
- Using Moat Verdicts on any other page (ROCE, Growth Estimation, Neff Ratio do not read them).
- A numeric moat score or an overall moat grade.
- Changes to the AI runner, backends, workspace (which 10-K Items are extracted), cache layout or model selection.

## Further Notes

- AI mistakes are acceptable here because nothing downstream consumes Moats. That is why there is no human review step.
- The cache is the existing per-ticker, per-task JSON keyed on the latest 10-K accessions. A new 10-K invalidates it. Cache-enabled and backend settings are unchanged.
- The Claude Code backend discards a response that does not validate and leaves the request open, so a schema the AI keeps failing would leave the page pending. That is why `sources` requires only one item rather than "several".

### Assumptions

- Each source carries a short verbatim `quote` besides fiscal year and Item, reading "multiple sources quoted" as quoting the passage. Veto → drop the field.
- `sources` must hold at least one item (the instructions ask for several). Requiring two or more would risk a permanently pending page.
- Fiscal year is free text ("FY2025") rather than an integer, to match the One-line Answers citation style.
- Moat display names and definitions are the result model's field titles and descriptions. There is no separate constants table.
- Definitions show in all views. Justification and sources show only in the detailed view. Summary and standard views are identical, as on One-line Answers.
- The Legal / Patent warning shows in every view, and its wording is the line given above.
- The warning rule is decided in the context builder (a `warning` value per moat), not only in the template, so it can be tested at the builder seam.
- The context builder lives in a new Business Quality sub-page module rather than in the Business Understanding module.
- On `period=quarterly` the builder returns an annual-only flag without calling the AI. The notice is a shared wizard partial (like the AI pending partial), added by whichever of the grilled specs lands first. Its exact flag name and text are set there.
- Task name `moats`, using the default OpenRouter model (no new entry in the models file).
- The verdict is stored as the strings "None" / "Weak" / "Strong" to match the glossary exactly.
