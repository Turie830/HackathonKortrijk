# Knowledge Within: SD Worx hackathon prototype

> **Find it. Understand it. Trust it.**
> An answer is only useful if you know *why* you can rely on it.

**Team:** Arthur Pintelon, Lamine Dene, Mauro Devolder, Nathaniel Lala. Hackathon Kortrijk, SD Worx challenge *"Unlock the Knowledge Within"*.

---

## The problem, in one story

A payroll consultant takes over a client and has to answer a simple question: *"What's the deadline for submitting changes for this month's payroll run?"*

They find an official procedure that says **Tuesday 12:00**. They also find a recent Teams message where a colleague says it is **Wednesday 15:00** now. A typical AI assistant would pick one of them, or blend them into one smooth, confident answer. The consultant still doesn't know what to do.

Finding information is not the hard part. **Knowing whether you can act on it is.**

## What this app does

Knowledge Within is a knowledge assistant that **shows its reasoning instead of hiding it**. For every question, it:

1. **Finds** relevant passages in a small knowledge base of procedures, client agreements, Teams notes and loose notes.
2. **Filters by context.** It only uses sources that apply to the chosen **country**, **client** and **date**.
3. **Checks every source** in plain, visible terms. Is it valid on that date? Has it been replaced by a newer version? Is it formally approved? Does it have an owner?
4. **Detects contradictions** between sources that are active in the same scope.
5. **Answers honestly** with one of four outcomes. It never invents an answer or a citation.
6. **Routes you to a person.** It suggests the owner of the source and lets you log a request for expert review.

It doesn't pretend to be certain. When the evidence isn't good enough, the app says so and tells you who to ask.

## The four outcomes

The interface is in Dutch; the labels are translated below.

| Status | UI label | When | What the user sees |
|---|---|---|---|
| ✅ `supported` | *Broncontroles in orde* | At least one relevant source passes all checks, and no active sources contradict each other | An answer built **word for word** from the source passages, with citations such as `[BE-CORRECTION-2026:1]` |
| ≠ `conflict` | *Tegenstrijdige bronnen* | Active sources in the same scope disagree on the same fact | **No answer.** The conflicting values are shown side by side, with a prompt to ask the owner |
| ⚠️ `review` | *Bevestiging nodig* | Sources were found, but none pass every check (for example: no owner, not approved) | The sources and their warnings, plus a request to have a human confirm |
| ∅ `missing` | *Kennis ontbreekt* | Nothing relevant exists for this question and context | An explicit "we don't know". This is a knowledge gap, not a guess |

### Source checks

Each source passage is checked separately. Any warning means the passage can't be used for a supported answer.

| Check | Warning in UI | Meaning |
|---|---|---|
| Validity period | *Niet geldig op de gekozen datum* | The chosen date falls outside `valid_from` to `valid_until` |
| Replaced | *Vervangen door …* | A newer, approved, applicable source lists this one in `supersedes` |
| Approval | *Niet formeel goedgekeurd* | Nobody formally approved it (typical for Teams chats and loose notes) |
| Ownership | *Eigenaar ontbreekt* | Nobody is responsible for keeping it correct |

The "last updated" date is **shown but deliberately not treated as proof**. A recently edited file isn't necessarily correct.

## Try it: the demo script

Start the app (see below), open http://127.0.0.1:8000 and try these. The three scenario buttons on the left fill in the first three for you.

| # | Question (Dutch, as typed in the app) | Context | Expected result | What it shows |
|---|---|---|---|---|
| 1 | *Hoe draag ik een klantdossier over aan een nieuwe consultant?* | BE, general | ✅ Supported, cites `BE-HANDOVER-2026` | The happy path: a clean, cited answer |
| 2 | Same question | BE, **Demo Acme** | ✅ Supported, also cites `ACME-HANDOVER` | Client-specific extras are added, and not mistaken for a contradiction |
| 3 | *Wie moet een looncorrectie controleren en goedkeuren?* | BE, 2026-09-30 | ✅ Supported by the **2026** version; the 2025 version is flagged "replaced" | Outdated knowledge is recognised and set aside |
| 4 | Same question | BE, date **2025-06-01** | ✅ Supported by the **2025** version | Time travel: what was valid *then* |
| 5 | *Wat is de deadline voor de maandelijkse verwerking?* | BE | ≠ Conflict: *dinsdag 12:00* (procedure) vs *woensdag 15:00* (Teams note) | Contradictions are surfaced instead of blended |
| 6 | Same question | **NL** | ✅ Supported, *donderdag 10:00* | Country scope: Belgian rules never leak into a Dutch answer |
| 7 | *Hoe archiveren we dossiers?* | BE | ⚠️ Review: no owner, not approved | Orphaned knowledge is flagged |
| 8 | *Hoe werkt quantumcomputing?* | any | ∅ Missing | An honest "no source" instead of a hallucination |

After any answer, click **Expertbeoordeling aanvragen** to log a review request for the suggested owner. It then appears in the **Expertbeoordelingen** tab. The **Kennisbank** tab lists every source in the knowledge base.

## Getting started

You need **Python 3.10+** with SQLite FTS5 support (standard in the official Python builds).

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

On Windows, use `.venv\Scripts\python` instead of `.venv/bin/python`.

- App: http://127.0.0.1:8000
- Interactive API docs (Swagger): http://127.0.0.1:8000/docs

On first start, the app creates `data/knowledge.sqlite3` and fills it from `data/sources.json`. Git ignores this file.

### Run the tests

```sh
.venv/bin/python -m unittest discover -s tests -v
```

The tests cover each behaviour in the demo script: replaced and historical sources, conflicts, country and client scope, ownerless sources, missing knowledge, FTS query-injection safety, persistence of review requests, and the model fallbacks.

## How it works

```
 Browser (static/)                    FastAPI (app.py)                  knowledge.py + SQLite
┌──────────────────┐  POST /api/ask  ┌──────────────────┐   search()   ┌──────────────────────────┐
│ question         │ ──────────────▶ │ validate input   │ ───────────▶ │ FTS5 full-text search    │
│ country (BE/NL)  │                 │ same-origin check│              │ + country/client filter  │
│ client (Acme)    │                 └────────┬─────────┘              │   inside the SQL query   │
│ as-of date       │                          │                        ├──────────────────────────┤
└──────────────────┘                          │                        │ per-source checks:       │
         ▲                                    │                        │ valid · replaced ·       │
         │                                    │                        │ approved · owner         │
         │                                    │                        ├──────────────────────────┤
         │                                    │                        │ conflicts(): compare     │
         │                                    │                        │ structured claims        │
         │                                    │                        ├──────────────────────────┤
         │                                    │ ◀───────────────────── │ status + extractive      │
         │                                    ▼                        │ answer + citations       │
         │                           model.py (optional)               └──────────────────────────┘
         │  answer, status, sources, │ rephrase with an LLM, only if
         └── conflicts, expert  ◀─── │ "supported"; citations checked;
                                     │ falls back to the original passages
```

### 1. Retrieval (`knowledge.search`)
- The question is split into words, and Dutch/English stopwords are removed.
- A small synonym list expands key topics. For example, *overdracht* also matches *klantdossier*, *draag* and *handover*. If a specific topic is recognised, only that topic's words are used for the search, so a question about corrections doesn't pull in unrelated notes that happen to mention "approval".
- It searches with SQLite **FTS5** (BM25 ranking). **Country and client filters are part of the SQL query**, so out-of-scope sources are never even retrieved. Every search term is quoted, so a user can't inject FTS operators to get around the filter.

### 2. Trust checks
Each retrieved passage gets the checks from the table above. A passage without warnings is marked `usable`. A passage that's valid on the chosen date and hasn't been replaced is marked `active`.

### 3. Conflict detection (`knowledge.conflicts`)
Each source in `data/sources.json` has hand-curated **structured claims** per section, for example `{"maandelijkse_deadline": "dinsdag 12:00"}`. Two **active** passages conflict when they give a different value for the same claim **in the same country and client scope**. That's why:
- a Belgian deadline and a Dutch deadline don't conflict (different country);
- the 2025 and 2026 correction procedures don't conflict (only one is active on a given date);
- the Acme handover extra doesn't conflict with the general procedure (different claim, different client scope).

### 4. Answering (`knowledge.answer_question`)
The status is decided in this order: *missing*, then *conflict*, then *review*, then *supported*. A supported answer is **extractive**: the text of the three best usable passages, verbatim, each with its citation. The suggested expert is the owner of the first retrieved source that has one, or "Knowledge Operations" if none do.

### 5. Optional AI wording (`model.py`)
If you set `LLM_ENDPOINT` (the full URL of any OpenAI-compatible `chat/completions` endpoint), `LLM_MODEL` and optionally `LLM_API_KEY` in your shell, the app asks the model to rephrase **supported** answers only. See `.env.example`; the file is **not** loaded automatically.

Guardrails:
- The model only gets the question, the context and the already-approved passages. Source text is marked as data, not instructions.
- It must return JSON claims, and **each claim must cite at least one passage ID that was actually provided**.
- Invalid JSON, invented citations, timeouts and API errors all fall back to the original verbatim passages. The UI says which mode was used.
- Checking citations proves that the model referred to real sources, **not** that the sources say what the model claims. The UI states this.

### 6. Expert review requests
`POST /api/reviews` stores the question, context, source IDs, reason (the status) and suggested expert in the `reviews` table. **No messages are sent**; this is a local inbox for the demo.

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | The web interface |
| `POST` | `/api/ask` | Ask a question. Body: `{"question": str, "country": "BE" \| "NL", "client_id": "demo-acme" \| null, "as_of": "YYYY-MM-DD"}` |
| `GET` | `/api/sources` | All sources in the knowledge base |
| `POST` | `/api/reviews` | Log an expert review request (same body as `/api/ask`) |
| `GET` | `/api/reviews` | All logged review requests, newest first |

Example:

```sh
curl -s http://127.0.0.1:8000/api/ask \
  -H 'Content-Type: application/json' \
  -d '{"question": "Wat is de deadline voor de maandelijkse verwerking?", "country": "BE", "as_of": "2026-09-30"}'
```

## Project structure

```
app.py                 FastAPI app: routes, input validation, same-origin check, security headers
knowledge.py           Core logic: database setup, search, trust checks, conflict detection, answers, reviews
model.py               Optional LLM rephrasing with citation validation and a safe fallback
data/sources.json      The fictional knowledge base (seed data)
data/knowledge.sqlite3 Generated on first run (git-ignored): sources, FTS index, review requests
static/index.html      Single-page interface (Dutch)
static/app.js          Frontend logic: ask, render results, tabs, review requests
static/style.css       Styling
tests/                 Unit tests (unittest)
.env.example           Optional LLM settings to export in your shell
```

## Adding or changing knowledge

Edit `data/sources.json`. Each source looks like this:

```json
{
  "id": "BE-CORRECTION-2026",
  "title": "Looncorrecties · huidige versie",
  "kind": "Procedure",
  "country": "BE",
  "client_id": null,
  "owner": "Payroll Quality",
  "approved": true,
  "valid_from": "2026-01-01",
  "valid_until": null,
  "updated_at": "2026-08-15",
  "supersedes": ["BE-CORRECTION-2025"],
  "passages": [{"section": "1", "text": "…"}],
  "claims": {"1": {"looncorrectie_controle": "tweede consultant"}}
}
```

- `country` can be `"BE"`, `"NL"` or `"ALL"`. `client_id` is `null` for general sources.
- `claims` maps a passage `section` to key/value facts. Sources in the same scope that use the **same key** with a **different value** are reported as a conflict.
- New search topics may need an entry in `SYNONYMS` in `knowledge.py`.
- New countries or clients also have to be added to the `Question` model in `app.py` and to the dropdowns in `static/index.html`.

The JSON is only imported when the database is empty. To re-import it, stop the app, **back up** `data/knowledge.sqlite3` (it also holds the review requests), delete it and restart.

## Honest limitations

This is a hackathon prototype, and we'd rather be clear about what it doesn't do:

- **All content is fictional.** None of it is real SD Worx policy or payroll advice.
- **Search is keyword-based** (FTS5 plus a few synonyms), not semantic embeddings.
- **Conflict claims are curated by hand.** Free text isn't automatically turned into claims. If no conflict is found, that doesn't prove the sources agree.
- **Passing the checks doesn't guarantee the content is correct.** It only means the source is valid, current, approved and owned.
- **No authentication or authorisation.** Country and client filters are there for relevance, not security. Only bind to `127.0.0.1` and only use fictional data.
- **Review requests are stored locally.** Nobody is notified.

A production version would need identity and access control, permission checks both at retrieval and when showing sources, tenant isolation, an approved model provider, and connectors to the real sources (SharePoint, Teams, the procedure library).

## Where this could go next

- **Close the loop.** Let the expert resolve a review request in the app. Their confirmation becomes a new approved source that supersedes the conflicting ones, so the next person gets a ✅.
- **Knowledge health dashboard.** Show stale, orphaned, unapproved and conflicting sources across the whole knowledge base, grouped by owner.
- **Assisted claim extraction.** Let an LLM propose structured claims from free text, with a human approving them before they count.
- **Semantic search.** Use embeddings next to FTS5 for questions phrased in unexpected ways.
