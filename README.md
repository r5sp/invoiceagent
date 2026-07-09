# Invoice Agent

A web application that reviews consultant invoices against their contract, builds the running
billing sheet, and drafts the revision-request email — built for Fifth Space's project management
team to automate the invoice-audit workflow Joe Worley runs by hand today.

## What it does

1. **Upload a contract** (PDF/DOCX) — parses the Exhibit B fee schedule into a task list: task
   number, cost code, description, fee type (lump sum vs. time & materials), unit rate, and
   contracted value. Handles addenda that supersede earlier tasks (e.g. "No further billing after
   Addendum 3 — bill to Task 22").
2. **Upload monthly invoices** one at a time — each becomes a new row in the running billing sheet
   (mirroring the "one tab per invoice" workflow). Two invoice shapes are handled:
   - **Billing-sheet format** — the consultant already submits a schedule-of-values table
     (cost code, task description, previously billed, billed this period, total billed to date).
     Parsed directly and trusted, then cross-checked (see rules below).
   - **T&M receipt format** — an unsorted list of dated line items (the "restaurant receipt" case,
     e.g. CTS-style invoices). Line items are correlated to contract tasks by cost code, fuzzy
     description matching, and — when an OpenAI key is configured — an LLM correlation pass for
     anything still unmatched.
3. **Review against the contract**, automatically, per Joe's procedures:
   - Task isn't overbilled vs. its contract value, and gets flagged once it crosses 75% billed.
   - Unit rates billed match the contract's rate schedule.
   - Line items map to a task actually in the contract (flags anything that doesn't).
   - Billed-to-date = prior billed + this period; an invoice's stated "prior billed" matches what
     the system has on file from earlier invoices.
   - T&M line-item math (quantity × rate = amount) and invoice/task subtotal math are correct.
   - No one person is billed more than 8 hrs/day or 40 hrs/week without an overtime note.
   - Invoiced inspection dates match an uploaded daily/monthly field report, when one exists.
   - Cost codes match the contract's Exhibit B cost codes.
   - Flags the highest single-period amount billed to date for a task.
   - Reimbursable markup matches the contract's specified rate.
4. **Download the billing sheet** as Excel — a Summary tab (schedule of values with conditional
   formatting at 75%/100% billed) plus one tab per invoice, each showing its line items and flags.
5. **Draft a revision-request email** — a ready-to-send email summarizing every flagged issue on
   an invoice, grouped by severity, so you can send it straight to the consultant.
6. **Ask questions** — a chat panel scoped to the project (contract + every invoice + every flag
   raised), so you don't have to re-explain context on follow-up questions.

## Architecture

```
invoiceagent/
├── backend/          FastAPI + SQLAlchemy + pdfplumber + openpyxl + OpenAI
│   ├── app/
│   │   ├── main.py               App entry point
│   │   ├── models.py             Database models (Project, Contract, ContractTask, Invoice, ...)
│   │   ├── schemas.py            Pydantic schemas (API + LLM extraction contracts)
│   │   ├── routers/              API routes
│   │   └── services/
│   │       ├── file_parser.py            PDF/DOCX text + table extraction
│   │       ├── contract_extraction.py    Exhibit B -> ContractTask rows (LLM + heuristic fallback)
│   │       ├── invoice_extraction.py     Invoice -> line items (billing-sheet heuristic + LLM)
│   │       ├── correlation.py            Match line items to contract tasks
│   │       ├── review_engine.py          The 12 audit rules + billing summary
│   │       ├── billing_sheet.py          Excel workbook generation
│   │       ├── email_draft.py            Revision-request email drafting
│   │       ├── inspection_extraction.py  Field-report date extraction
│   │       └── chat.py                   Project-scoped chat
│   └── tests/
├── frontend/          React + Vite, Fifth Space branding
│   └── src/
│       ├── App.jsx
│       └── components/
└── .env               OpenAI key + auth config (not committed)
```

A **project** in this app is one consultant engagement tracked over time (e.g. "PPS — Albion
Partners"). You upload the contract once (re-upload when an addendum arrives — it fully replaces
the fee schedule), then upload each new invoice as it comes in. Chat memory, billing history, and
review flags are all scoped to the project, so it accumulates context the way Joe's own manual
billing sheets do today.

## Prerequisites

- Python 3.11+ (3.14 currently breaks `pydantic-core`'s build — use 3.11–3.13)
- Node.js 18+
- An OpenAI API key (strongly recommended — see below)

## Setup

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set `OPENAI_API_KEY`. See [.env.example](.env.example) for all options.

### 2. Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API at `http://localhost:8000`, interactive docs at `http://localhost:8000/docs`.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Sign up with any `@fifthspace.com` email — access is restricted to
that domain (configurable via `ALLOWED_EMAIL_DOMAIN`).

## Usage

1. Create a project (e.g. "PPS — Albion Partners").
2. Upload the contract — review the parsed fee schedule in the billing sheet.
3. Upload each monthly invoice as it arrives — review the flags, download the updated Excel
   billing sheet, and use the drafted email to request revisions from the consultant.
4. Optionally upload daily/monthly field reports so invoiced inspection dates get cross-checked.
5. Use the chat panel for anything else — "how close is task 22 to its cap?", "summarize this
   invoice's issues", etc.

## On the OpenAI API key

Contract and invoice parsing use a **heuristic table parser as a fallback** so the app is usable
without a key, but an LLM is genuinely required for full functionality:

- **Contract parsing**: the heuristic handles the common "Task | Location | Cost Code |
  Description | Fee" table layout reasonably well, but an LLM handles arbitrary consultant contract
  formats far more reliably (this matters a lot once you're onboarding a second or third
  consultant with a differently-formatted contract).
- **Billing-sheet-format invoices** (the consultant already fills in a schedule-of-values table):
  parse fine without a key.
- **T&M receipt-format invoices** (unsorted line items, e.g. CTS-style) and **project chat**
  require an OpenAI key — there's no reasonable heuristic for free-form invoice parsing.

Set `OPENAI_API_KEY` before relying on this for anything beyond the billing-sheet-format case.

## API reference

| Method | Endpoint | Description |
|--------|----------|--------------|
| POST | `/api/auth/register` / `/login` / `/logout` | Auth (email/password, domain-restricted) |
| GET/POST | `/api/projects` | List / create projects |
| GET/DELETE | `/api/projects/{id}` | Project detail (contracts, invoices, reports) |
| POST | `/api/projects/{id}/contracts` | Upload + parse a contract |
| GET/POST/DELETE | `/api/projects/{id}/invoices` | Upload + parse + review an invoice |
| POST | `/api/projects/{id}/inspection-reports` | Upload a field report |
| GET | `/api/projects/{id}/billing-summary` | JSON schedule-of-values summary |
| GET | `/api/projects/{id}/billing-sheet.xlsx` | Download the Excel billing sheet |
| GET | `/api/projects/{id}/invoices/{invoice_id}/email-draft` | Drafted revision-request email |
| GET/POST | `/api/projects/{id}/chat` | Project-scoped chat history / send message |

## Running tests

```bash
cd backend
source venv/bin/activate
pytest -v
```

Tests cover currency/date/period parsing, and the review engine's rules (overbilling, threshold
warnings, rate mismatches, prior-billed continuity/cold-start seeding, T&M math, hours limits,
markup checks, and billing summary totals).

## Design principles

- **Numbers are computed deterministically, never by the LLM.** The review engine's math (overbill
  checks, continuity, hour limits) runs in plain Python against parsed structured data — the LLM is
  only used for *extracting* structure from free-form text, never for arithmetic or the final
  pass/fail judgment on a flag.
- **Cold-start aware.** Most contracts are already in progress when they're first uploaded here.
  The first invoice tracked for a task seeds its "prior billed" baseline instead of assuming
  billing starts at zero — continuity is only checked from the second tracked invoice onward.
- **Conservative flagging.** An unmatched line item is flagged for review rather than silently
  guessed at — a false positive costs a human a few seconds of review; a false negative costs money.

## License

MIT
