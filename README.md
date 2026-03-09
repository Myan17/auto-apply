# auto-apply

Fully automated job application tool powered by **GPT-4o Vision**. Give it a Google Sheet with job URLs, your resume, and your info — it opens a browser, reads every page like a human, and fills out the application form autonomously.

**Supports:** Workday, Greenhouse, Lever, Ashby, and any generic portal.

---

## How it works

1. Reads pending job URLs from your Google Sheet
2. Scrapes each job description
3. Uses GPT-4o to tailor your resume and write a cover letter
4. Opens a real Chromium browser, takes a screenshot each step
5. Sends the screenshot + live DOM elements to GPT-4o Vision
6. GPT-4o decides the next action (click, fill, select, upload…)
7. Repeats until the application is submitted
8. Writes the result back to your Google Sheet

---

## Prerequisites

- Python 3.9+ **or** Docker
- An [OpenAI API key](https://platform.openai.com/api-keys) (GPT-4o access required)
- A Google Cloud service account with Sheets API enabled
- Your resume as a PDF

---

## Quick Start (Local)

### 1. Clone and install

```bash
git clone https://github.com/Myan17/auto-apply.git
cd auto-apply

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install --upgrade pip        # required — old pip can't handle pyproject.toml
pip install -e .
playwright install chromium
```

### 2. Set up your `.env`

```bash
cp .env.example .env
# then edit .env with your values (see sections below)
```

### 3. Run

```bash
auto-apply run --limit 5
```

---

## Quick Start (Docker)

```bash
git clone https://github.com/Myan17/auto-apply.git
cd auto-apply

cp .env.example .env
# edit .env, place credentials.json in the project root

docker compose build
docker compose run auto-apply run --limit 5
```

> **Headless mode:** For Docker, open `config/settings.yaml` and set `headless: true` under `browser:`.

---

## Configuration

### `.env` file

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | Your OpenAI API key |
| `GOOGLE_CREDENTIALS_PATH` | Path to your service account JSON (e.g. `./credentials.json`) |
| `GOOGLE_SHEET_ID` | ID from your Google Sheet URL |
| `APPLICANT_NAME` | Your full name |
| `APPLICANT_EMAIL` | Your email address |
| `APPLICANT_PHONE` | Your phone number |
| `APPLICANT_ADDRESS` | Street address |
| `APPLICANT_CITY` | City |
| `APPLICANT_STATE` | State abbreviation (e.g. `MN`) |
| `APPLICANT_ZIP` | ZIP code |
| `RESUME_PATH` | Absolute path to your base resume PDF |
| `WORKDAY_PASSWORD` | Password to use when creating Workday accounts (optional) |

### `config/settings.yaml`

Controls AI models, browser behavior, sheet column layout, and your standard application answers (EEO questions, work authorization, etc.).

---

## Getting `GOOGLE_CREDENTIALS_PATH`

You need a **Google Cloud service account** that has access to the Sheets API. Takes ~5 minutes:

### Step 1 — Create a Google Cloud project

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Click the project dropdown at the top → **New Project**
3. Give it any name (e.g. `auto-apply`) → **Create**

### Step 2 — Enable the Google Sheets API

1. In your new project, go to **APIs & Services → Library**
2. Search for **Google Sheets API** → click it → **Enable**
3. Also enable **Google Drive API** (same steps)

### Step 3 — Create a service account

1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → Service Account**
3. Name it (e.g. `auto-apply-bot`) → **Create and Continue** → **Done**

### Step 4 — Download the JSON key

1. On the Credentials page, click your new service account
2. Go to the **Keys** tab → **Add Key → Create new key → JSON**
3. A `.json` file downloads — this is your `credentials.json`
4. Move it to the project root: `mv ~/Downloads/*.json ./credentials.json`
5. Set `GOOGLE_CREDENTIALS_PATH=./credentials.json` in your `.env`

### Step 5 — Share your Google Sheet with the service account

1. Open your service account on Google Cloud → copy the **email** (looks like `name@project.iam.gserviceaccount.com`)
2. Open your Google Sheet
3. Click **Share** (top right)
4. Paste the service account email → set role to **Editor** → **Send**

Done. The tool can now read and write to your sheet.

---

## Setting up your Google Sheet

Create a sheet with these columns (in this order):

| A | B | C | D | E | F | G |
|---|---|---|---|---|---|---|
| URL | Company | Role | Status | Date Applied | Method | Notes |

Paste job URLs into column A. Leave B–G empty — the tool fills them in.

Example URLs that work:
- `https://job-boards.greenhouse.io/company/jobs/123`
- `https://jobs.ashbyhq.com/company/job-id`
- `https://company.wd1.myworkdayjobs.com/careers/job/...`
- `https://jobs.lever.co/company/job-id`
- Any job listing URL (generic scraper as fallback)

The tool will set **Status** to `Applied` or `Failed` after each attempt.

---

## CLI Commands

```bash
# Check your config is valid
auto-apply config

# Show stats from local DB
auto-apply status

# Run the full pipeline (scrape → tailor → apply)
auto-apply run --limit 10

# Just scrape job descriptions (no applying)
auto-apply scrape --limit 5

# Just tailor docs for already-scraped jobs
auto-apply tailor --limit 5
```

---

## Standard application answers

Edit the `profile:` section in `config/settings.yaml` to set your answers to common application questions:

```yaml
profile:
  based_in_us: true
  requires_sponsorship: true
  open_to_relocation: true
  willing_to_work_onsite: true
  country_of_residence: "United States"
  heard_about_us: "LinkedIn"
  previously_employed_here: false
  at_least_18: true
  available_start_date: "Immediately"
  hispanic_or_latino: false
  ethnicity: "Asian"
  veteran_status: "I am not a protected veteran"
  self_id_language: "English"
```

The vision agent reads these and selects the matching option on each form automatically.

---

## Troubleshooting

**`OPENAI_API_KEY` not working** — Make sure you have GPT-4o access. Check [platform.openai.com/usage](https://platform.openai.com/usage).

**Google Sheets 403 error** — The sheet wasn't shared with the service account email. Repeat Step 5 above.

**`credentials.json` not found** — Check `GOOGLE_CREDENTIALS_PATH` in `.env` is the correct path.

**Browser not opening** — Run `playwright install chromium` to install the browser.

**Rate limit errors (429)** — The tool automatically falls back from GPT-4o to GPT-4o-mini for text tasks. If it still hits limits, reduce `--limit` or wait a minute between runs.

---

## Project structure

```
auto-apply/
├── src/
│   ├── ai/              # Resume tailoring + cover letter (GPT-4o-mini)
│   ├── applicator/      # Browser automation
│   │   └── browser/
│   │       └── vision_agent.py   # GPT-4o Vision loop
│   ├── scraper/         # Job description scrapers per portal
│   ├── sheets/          # Google Sheets reader/writer
│   ├── documents/       # PDF generation
│   ├── config.py        # Configuration models
│   ├── models.py        # Data models
│   ├── db.py            # SQLite tracking
│   └── cli.py           # CLI entrypoint
├── config/
│   └── settings.yaml    # All app settings
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── pyproject.toml
```
