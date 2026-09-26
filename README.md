# Staff Triage Copilot

A staff-facing tool for the front desk of a community college's Student Success
Center. It does two jobs:

1. **Routing.** Staff paste what a student said, and a scikit-learn classifier
   predicts which of six departments should handle it, with a confidence score.
   Staff confirm or correct the prediction. After an admin approves them, those
   corrections feed an hourly retraining loop that replaces the live model only
   if the new one scores better on a fixed holdout set.
2. **Knowledge base.** Admins upload institutional documents, such as the
   academic calendar and policy PDFs. Staff ask questions in plain English and
   get answers generated only from those documents (retrieval-augmented
   generation over pgvector).

The classifier is trained almost entirely on English text. The seed dataset
carries a few Spanish phrases, but there is no real bilingual support today.

## How it works

```
                       ┌──────────────── Routing ────────────────┐
Student request text
        │
        ▼
  POST /predict        ──►  TF-IDF + LogisticRegression  ──►  { category, confidence, timestamp }
        │
  POST /update-data    ──►  training_phrases  (reviewed = FALSE, i.e. pending)
  POST /admin/upload-csv ─┘
        │
  Admin review (/admin#review) ──► approve → reviewed = TRUE   |   reject → row deleted
        │
  Retrain (hourly scheduler, or POST /retrain)
        ├─► pull reviewed rows (minus holdout phrases) ──► train new pipeline
        ├─► score new vs. live model on ml/holdout_test_set.csv
        ├─► if new ≥ live: back up old model locally, save new model, upload to S3, hot-swap
        └─► write a row to retrain_log (swapped or not)

                       ┌──────────── Knowledge base ─────────────┐
  POST /admin/upload-calendar  ──►  extract text ──► header-aware chunks    ─┐
  POST /admin/upload-document  ──►  extract text ──► paragraph chunks       ─┤
                                                                             ▼
                              OpenAI text-embedding-3-small ──► document_chunks (pgvector)
                                                                             │
  POST /ask  ──► embed question ──► 3 nearest chunks ──► gpt-4o-mini ──► { answer, sources }
```

## Features

### Triage classification

The classifier is a scikit-learn `Pipeline`:

- `TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, lowercase=True)`
- `LogisticRegression(class_weight="balanced", max_iter=1000)`

It was first trained offline in `ml/Staff_Triage_ML_Pipeline.ipynb`, where it
reached a final holdout accuracy of **0.874**. In deployment the canonical model
is stored in S3. On startup the FastAPI lifespan handler downloads it to
`models/model.joblib`, and falls back to the local file if the download fails.

It predicts one of six categories:

| Category |
| --- |
| Admissions / Enrollment |
| Advising |
| Appointment |
| ESL Advising |
| New Accepted Student / Navigate |
| Student Financial Services |

The model predicts category only. `training_phrases` has a `subcategory` column,
but nothing reads it yet.

On the **Route a request** page (`/`), the result card shows the predicted
department and a confidence bar in one of three tiers: ≥ 50% "High
confidence", ≥ 30% "Worth a second look", below that "Low confidence, please
verify". Staff then click **Yes, correct** or **No, correct it**. Correcting
opens a department picker. Either way, the phrase and the final category are
POSTed to `/update-data` with `source: "staff"` and land in the review queue.

### Review dashboard

New rows from `/update-data` and CSV uploads come in with `reviewed = FALSE`.
Retraining only reads rows with `reviewed = TRUE`, so nothing staff submit
affects the model until an admin approves it.

In the admin **Pending corrections** section (`/admin#review`), admins can:

- **Approve** a single row (sets `reviewed = TRUE`)
- **Reject** a single row (deletes it from `training_phrases`)
- **Approve all** pending rows at once

The list is paginated eight per page. A badge on the sidebar link shows the
pending count.

### Retraining

A retrain cycle (`run_retrain_cycle` in `retrain.py`) works like this:

1. Pull every row where `reviewed = TRUE`, excluding any text that appears in the
   holdout set.
2. Train a new pipeline.
3. Score both the new pipeline and the live pipeline on
   `ml/holdout_test_set.csv`, a fixed set of 660 phrases that is never used for
   training.
4. If the new model scores lower, keep the live model. Otherwise (ties
   included), copy the current `models/model.joblib` to
   `models/model_backup_<UTC timestamp>.joblib`, write the new model, upload it
   to S3 as `model.joblib`, and swap it into the running process.
5. Insert a row into `retrain_log` (`ran_at`, `swapped`, `previous_accuracy`,
   `new_accuracy`), whether or not the model was swapped.

The cycle runs in two ways:

- **Scheduled:** an APScheduler `BackgroundScheduler` runs it every hour
  in-process, starting at app startup.
- **Manual:** the **Retrain Model** button at `/admin#retrain`, or a direct
  `POST /retrain`. This path has a 300-second cooldown. The scheduled job does
  not share that cooldown.

About backups:

- The local backups are copies of the *previous* model. On Render the local
  filesystem is ephemeral, so these files don't survive a redeploy.
- S3 holds only the *current* model under one key, and each swap overwrites
  it. Unless versioning is enabled on the bucket, S3 has no history of older
  models.
- `retrain_log` is only in the database. No endpoint or UI page shows it yet.

### Batch CSV upload

`/admin#upload` accepts a CSV with a header row containing at least `Phrase` and
`Category`. The UI text also mentions `Subcategory` and `Language` columns, which
are accepted but ignored. A UTF-8 BOM is handled. The upload skips rows with an
empty phrase or a category outside the six valid ones and reports how many rows
it skipped. Valid rows are inserted as pending (`reviewed = FALSE`,
`source = "staff"`), so they go through the same review step as individual
corrections. `test.csv` is a three-row sample that includes one deliberately
invalid row.

### Knowledge base (RAG)

Documents are chunked, embedded with OpenAI `text-embedding-3-small` (1536
dimensions), and stored in the `document_chunks` table in a pgvector
`vector(1536)` column.

There are two chunking strategies (`ml/build_embeddings.py`):

- **Header-aware (academic calendar):** splits on a fixed list of known
  section headers (term names such as `FALL 2026`, course-length blocks such as
  `1st 7-WEEK COURSES (ACCELERATED)`, and the holidays/deadlines block). This
  keeps each block of dates together. The header list is hardcoded for the
  2026–27 calendar, so a future calendar with different term names needs the
  list updated.
- **General (policy documents):** splits on blank-line paragraph breaks,
  packs paragraphs into chunks of about 800 characters, and carries the last
  100 characters of each chunk into the next as overlap.

Text extraction: `.pdf` files go through `pypdf` (pages joined with blank
lines). Any other file is decoded as UTF-8 text.

`POST /ask` embeds the question and retrieves the three nearest chunks by L2
distance across all documents. It sends them to `gpt-4o-mini` with a prompt
that tells the model to answer only from that context and to say so if the
answer isn't there. The response includes the answer and the full text of the
retrieved chunks as `sources`. The **Knowledge base** page (`/knowledge-base`) is
a chat-style UI that shows the answer plus an 80-character preview of the top
source chunk. Sources are chunk text, not document names.

Tested manually with the real NSCC Fall 2026–Summer 2027 academic calendar
and an SAP Appeals policy PDF loaded in the same table. Questions about each
document were answered from the correct document, including course-length and
semester questions that were ambiguous before the calendar labels were
clarified. There are no automated tests for retrieval or answer quality.

### Document upload

In `/admin#documents` there are two upload cards:

- `POST /admin/upload-calendar`: header-aware chunking
- `POST /admin/upload-document`: general chunking

Both are **replace-by-name**. Before inserting, they delete every existing chunk
whose `document_name` matches the uploaded filename, so re-uploading a file
updates its content instead of duplicating it. Both return
`{ "document": <filename>, "chunks_created": <n> }`.

## UI

The app uses one shared layout (`base.html`) with a left sidebar, which becomes
a slide-out menu on narrow screens:

- **Front desk:** *Route a request* (`/`) and *Knowledge base* (`/knowledge-base`)
- **Admin:** *Model retraining*, *Pending corrections*, *Batch CSV upload*,
  *Documents*

All four admin views are sections of one page (`/admin`), shown with URL
hashes: `#retrain`, `#review`, `#upload`, `#documents`. Each view is a card.
Because they share one page, the pending-corrections badge stays accurate
whichever section is open.

## Tech stack

- **API:** FastAPI + Uvicorn, Jinja2 templates, vanilla JS frontend
- **ML:** scikit-learn (TF-IDF + Logistic Regression), pandas, joblib
- **Scheduling:** APScheduler (in-process)
- **Database:** PostgreSQL with the pgvector extension, on AWS RDS
  (SQLAlchemy + psycopg2)
- **Model storage:** Amazon S3 (boto3)
- **LLM / embeddings:** OpenAI API (`text-embedding-3-small`, `gpt-4o-mini`)
- **PDF extraction:** pypdf
- **Packaging / deploy:** Dockerfile included; deployed on Render; CI/CD on
  GitHub Actions

## Design decisions

**Logistic Regression over LinearSVC.** Both perform similarly on this data, but
LogisticRegression gives calibrated `predict_proba()` output. That matters here
because low-confidence predictions can be flagged for staff review instead of
being routed automatically.

**Splitting before augmentation.** An early version of the pipeline augmented the
data before the train/test split. That leaked near-duplicate phrases across both
sides and reported a false 100% accuracy. Splitting first revealed the true
baseline (~0.40) and shaped the rest of the data strategy: where to add phrases,
which categories were actually confusable, and when more data stopped helping.

**A fixed holdout set for the swap decision.** Retraining doesn't use a freshly
trained pipeline's own random train/test split to decide whether to promote it.
Both models are scored on the same fixed holdout set, so the decision stays
comparable across retrains as the training table grows. Holdout phrases are also
excluded from the training pull, so the holdout can't leak into training
through the database.

**Human review before retraining.** An automatic loop that retrains on whatever
staff click would let one bad correction, or one careless "Yes, correct", affect
the live model within the hour. The `reviewed` flag, together with the holdout
gate, means a change needs both a human approval and a measurable improvement
before it reaches the live model.

**Two chunkers instead of one.** The academic calendar is a dense list of dates
under repeated sub-headings. Splitting it on whitespace either fragmented a
block of dates or merged neighbouring sections together. Splitting on known
headers keeps each block intact. Policy documents are prose, so
paragraph-based chunks with overlap suit them better.

**RDS security group allows all inbound IPs (`0.0.0.0/0`).** Render's free tier
has no fixed outbound IP, so there is no stable CIDR to allowlist. Access is
still protected by password plus SSL (`sslmode=require`). This is a deliberate,
documented tradeoff for a portfolio deployment. A production setup would put the
database behind a VPC or a fixed-IP egress.

## Lessons learned: bugs found and fixed

- **Data leakage in the original notebook:** augmenting before the split
  inflated accuracy to a false 100% (see above).
- **Holdout overlap:** the retrain data pull originally included phrases that
  were also in the holdout set, which inflated the new model's score. Fixed by
  excluding holdout texts in the query.
- **Shifting test splits:** comparing models on each run's own random test split
  made retrain comparisons unreliable. Fixed by switching to the fixed holdout
  set.
- **Real vocabulary gaps found by hand testing:** "MAFSA/MASFA", guest
  registration, and student account setup were misrouted. The basic phrasing "I
  want to apply" had never been in the training data at all. Adding targeted
  phrases for "apply" then collided with the MAFSA signal, which needed a
  second round of phrases to separate them. Unverified "continuing ed"
  terminology was removed from the training data rather than guessed at.
- **Calendar chunking:** whitespace-based chunking produced bare-header chunks
  and fragmented or merged sections. Replaced with header-based splitting.
- **Ambiguous source labels:** some calendar section labels were ambiguous about
  dates, so retrieval answered course-length and semester questions wrongly.
  Clarifying the labels in the source document fixed it.
- **Missing dependencies / functions:** `run_retrain_cycle` and `apscheduler`
  were referenced before they existed, and `pypdf` and `openai` were missing
  from `requirements.txt`, which broke CI until they were added (plus
  `OPENAI_API_KEY` in the CI environment).
- **Stale HTML after the redesign:** a leftover pre-redesign form block on the
  Knowledge Base page stopped the Ask button from working.

## Known limitations

- **Retraining discards 20% of the approved data.** `train_new_pipeline` still
  makes an 80/20 split and fits only on the 80%. The 20% test split isn't used
  for the swap decision, so those rows are simply left out of training.
- **Automated tests cover only the core endpoints** (`/health`, `/predict`,
  `/update-data`, `/`, and `/retrain` auth). The review endpoints, CSV upload,
  document upload, `/ask`, and the scheduler have been tested manually only.
- **Document replace is not atomic.** Old chunks are deleted and committed
  first, then new chunks are embedded and inserted one at a time. If an OpenAI
  call fails partway through, the document is left partially loaded until it is
  re-uploaded.
- **Replace-by-name uses the exact filename.** `ml/build_embeddings.py` run as
  a script stores the calendar as `ml/nscc_academic_calendar.txt` (with the
  path), so uploading the same file through the UI creates a second copy instead
  of replacing it.
- **The scheduler runs inside the web process.** With multiple Uvicorn workers,
  each worker would run its own hourly retrain.
- **The `.pdf` check is case-sensitive.** A file named `X.PDF` is decoded as
  UTF-8 text instead of going through pypdf.

## Authentication

Every write/admin endpoint requires an `X-API-Key` header matching
`STAFF_API_KEY`: `/update-data`, `/retrain`, and all `/admin/*` API routes. A
missing header returns `422`, a wrong key returns `401`.

`/predict`, `/ask`, `/health`, and the HTML pages (`/`, `/knowledge-base`,
`/admin`) require no authentication. `main.py` also injects `STAFF_API_KEY` into
every rendered page through `base.html` so the browser can call the protected
endpoints. As a result, anyone who can load the site can read the key from the
page source. Access control is effectively "can you reach the site", not
per-user. A real login/permissions system is on the roadmap.

## Requirements

- Python 3.13
- PostgreSQL with the `vector` (pgvector) extension available (AWS RDS in
  deployment)
- An S3 bucket plus an IAM key pair with read/write access to it
- An OpenAI API key

See `requirements.txt` for the pinned dependency set.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require
STAFF_API_KEY=some-long-random-string
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_S3_BUCKET=your-model-bucket
OPENAI_API_KEY=...
```

All six are read at import time (`retrain.py`, `ml/build_embeddings.py`, and
`ml/retrieve.py` build their clients on import). Neither the app nor the test
suite will start without them.

### Database

```bash
psql "$DATABASE_URL" -f ml/schema.sql              # training_phrases
psql "$DATABASE_URL" -f ml/retrain_log_schema.sql  # retrain_log
psql "$DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS vector;"
python ml/create_chunks_table.py                   # document_chunks (runs ml/document_chunks_schema.sql)
```

`ml/schema.sql` does **not** yet include the `reviewed` column that the review
flow and retraining depend on. The code expects a boolean `reviewed` column on
`training_phrases`, where rows inserted without it default to `FALSE` and seed
data is `TRUE` (otherwise nothing is trained on). For example:

```sql
ALTER TABLE training_phrases ADD COLUMN reviewed BOOLEAN DEFAULT FALSE;
UPDATE training_phrases SET reviewed = TRUE WHERE source = 'seed';
```

Optionally seed the training data:

```bash
python ml/import_seed_data.py
```

To load the bundled academic calendar from the command line instead of the
admin UI:

```bash
python ml/build_embeddings.py
```

## Running

```bash
uvicorn main:app --reload
```

The app listens on `http://127.0.0.1:8000`. On startup it pulls `model.joblib`
from S3 and starts the hourly retrain scheduler.

### Docker

```bash
docker build -t triage-copilot .
docker run -p 8000:8000 --env-file .env triage-copilot
```

## API

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/` | none | Route-a-request page |
| GET | `/knowledge-base` | none | Knowledge base chat page |
| GET | `/admin` | none | Admin page (sections by `#hash`) |
| GET | `/health` | none | `{ "status": "healthy", "model_loaded": true }` |
| POST | `/predict` | none | Classify a student request |
| POST | `/update-data` | key | Record a confirmation/correction (pending) |
| POST | `/retrain` | key | Run a retrain cycle now (300 s cooldown) |
| GET | `/admin/pending-corrections` | key | List rows with `reviewed = FALSE` |
| POST | `/admin/approve-correction` | key | `{ "id": n }` → set reviewed |
| POST | `/admin/reject-correction` | key | `{ "id": n }` → delete row |
| POST | `/admin/approve-all-pending` | key | Approve every pending row; returns `count` |
| POST | `/admin/upload-csv` | key | Multipart `file`; batch-insert pending rows |
| POST | `/admin/upload-calendar` | key | Multipart `file`; header-aware chunk + embed |
| POST | `/admin/upload-document` | key | Multipart `file`; paragraph chunk + embed |
| POST | `/ask` | none | Answer a question from uploaded documents |

### `POST /predict`

```json
{ "text": "I need a copy of my transcript" }
```

```json
{
  "category": "Admissions / Enrollment",
  "confidence": 0.912,
  "timestamp": "2026-09-02T00:00:00+00:00"
}
```

`text` must be non-empty (`422` otherwise). Inference errors return `500`.

### `POST /update-data`

```json
{ "text": "I finished my ESL placement exam", "correct_category": "ESL Advising" }
```

`text` and `correct_category` are required and non-empty. `source` is optional
and defaults to `"staff"`, which is also what the frontend sends for both
confirmations and corrections. Returns `{ "status": "Recorded" }`.

### `POST /retrain`

Runs synchronously (roughly one to two minutes). Returns `429` if a manual
retrain was started in the last 300 seconds. The cooldown starts when the
request is accepted, so it applies even if that retrain fails. Accuracies are
returned as 3-decimal strings.

No swap:

```json
{
  "swapped": false,
  "reason": "New model did not outperform current model",
  "current_accuracy": "0.871",
  "new_accuracy": "0.864"
}
```

Swap:

```json
{
  "swapped": true,
  "backup_saved_to": "models/model_backup_20260909_035331.joblib",
  "s3_backup_success": true,
  "previous_accuracy": "0.868",
  "new_accuracy": "0.879"
}
```

`s3_backup_success` is `false` if the S3 upload failed. The local swap still
happened.

### `POST /admin/upload-csv`

```json
{ "inserted": 2, "skipped": 1, "skipped_rows": [ { "Category": "Not A Real Category", "...": "..." } ] }
```

### `POST /ask`

```json
{ "question": "When is the deadline to withdraw from a 1st 6-week course in Fall 2026?" }
```

```json
{
  "answer": "…",
  "sources": ["1st 6-WEEK COURSES (ACCELERATED), Sep 16-Oct 27, 2026\n…", "…", "…"]
}
```

## Testing

```bash
pytest
```

`test_main.py` covers `/health`, `/predict`, `/update-data` (input validation
and API-key handling), `/` loading, and `/retrain` rejecting a missing key. It
needs all six environment variables. Starting the app also downloads the model
from S3. The `/update-data` test writes a real row to whatever database
`DATABASE_URL` points at, so run it against a disposable database.

`test.py` is an interactive CLI for probing the model by hand. It prints the top
three categories with probabilities:

```bash
python test.py
```

## CI/CD

`.github/workflows/tests.yml` (`Run Tests`):

1. On every push and pull request to `main`, install dependencies and run
   `pytest`. This needs repository secrets `DATABASE_URL`, `STAFF_API_KEY`,
   `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_BUCKET`, and
   `OPENAI_API_KEY`.
2. On push to `main` only, and only if the test job passes, trigger a Render
   deploy through the `RENDER_DEPLOY_HOOK` secret. A failing test blocks the
   deploy.

## Project layout

```
main.py                 FastAPI app: pages, /predict, /update-data, /retrain, /admin/*, /ask, scheduler
retrain.py              training-data pull, pipeline training, holdout eval, local + S3 model storage, retrain_log
test_main.py            pytest suite for the API
test.py                 interactive CLI for probing the model
test.csv                sample batch-upload CSV (includes one invalid row)
build_train_holdout_split.py   one-off script that produced ml/holdout_test_set.csv
base.html               shared Jinja layout (sidebar, injects STAFF_API_KEY)
index.html              Route a request (/)
knowledgebase.html      Knowledge base chat (/knowledge-base)
admin.html              Admin sections: #retrain, #review, #upload, #documents
static/                 app.js, admin.js, ask.js, nav.js, style.css
models/model.joblib     live pipeline (pulled from S3 at startup)
models/model_backup_*.joblib   local backups written before a swap (git-ignored)
Dockerfile              python:3.13-slim + uvicorn
requirements.txt        pinned dependencies

ml/
  Staff_Triage_ML_Pipeline.ipynb   original training + evaluation notebook
  schema.sql                       training_phrases table (see note on `reviewed`)
  retrain_log_schema.sql           retrain_log table
  document_chunks_schema.sql       document_chunks table (pgvector)
  create_chunks_table.py           applies document_chunks_schema.sql
  build_embeddings.py              chunkers, embedding, CLI loader for the calendar
  retrieve.py                      query embedding, nearest-chunk search, answer generation
  nscc_academic_calendar.txt       academic calendar source text
  import_seed_data.py              load seed_training_data.csv into the DB
  seed_training_data.csv           reference training dataset
  train_only_data.csv              seed data minus the holdout split
  holdout_test_set.csv             fixed 660-row eval set used by retraining
  *_fix_phrases.csv, *_contrastive_phrases.csv   targeted phrase sets from gap fixes
  llm_generated_phrases.csv        raw LLM generation output
```

## Roadmap

Planned, not yet implemented:

- **Real Spanish / bilingual support**, beyond the handful of Spanish phrases in
  the seed data.
- **Subcategory prediction.** The schema has the column, but nothing predicts it.
- **A full login / permissions system**, replacing the single shared
  `STAFF_API_KEY` that is currently embedded in every served page.

## Security note

`.env` is git-ignored. Do not commit real credentials. This project's `.env`
holds a database password, an AWS access key pair, an OpenAI API key, and the
`STAFF_API_KEY`. If any of those has ever been committed or shared, rotate it.
`STAFF_API_KEY` is served inside every HTML page by design, so it is not a
secret from anyone who can load the site.
