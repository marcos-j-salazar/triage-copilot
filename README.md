# Staff Triage Copilot

A machine learning service that routes student inquiries to the correcfront desk department at a community college. Staff paste what a student says,
and the API returns a predicted category with a confidence score. Corrections
and confirmations made by staff are written back to a PostgreSQL database, and a
staff-triggered `/retrain` endpoint uses that accumulated data to train a fresh
model, keeping it only if it beats the current one on a fixed holdout set (an
active learning feedback loop).

The model is trained almost entirely on English text. The seed dataset carries a
few Spanish phrases, but there is no real bilingual support today — proper
Spanish/bilingual coverage is on the roadmap, not implemented.

## How it works

```
Student request (text)
        │
        ▼
  FastAPI  /predict      ──►  scikit-learn pipeline  ──►  { category, confidence, timestamp }
        │                     (TF-IDF + LogisticRegression, models/model.joblib)
        │
  FastAPI  /update-data  ──►  PostgreSQL (training_phrases)   staff corrections + confirmations
        │
  FastAPI  /retrain      ──►  pull training_phrases ──► train new pipeline
        │                     ──► score new vs. current on ml/holdout_test_set.csv
        │                     ──► if new ≥ current: back up old model (local + S3), swap live model
        ▼
  Amazon S3  (model.joblib)   canonical copy, downloaded on startup
```

The classifier is a `Pipeline` of:

- `TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, lowercase=True)`, word + bigram features
- `LogisticRegression(class_weight="balanced", max_iter=1000)`

It was first trained offline in `ml/Staff_Triage_ML_Pipeline.ipynb` and exported to
`models/model.joblib`. In deployment the canonical model lives in an S3 bucket:
the API downloads it to `models/model.joblib` at startup (via the FastAPI lifespan
handler) and falls back to whatever local file is already there if the download
fails. From then on the model can be replaced in place by `/retrain` (see below).

### Categories

| Category |
| --- |
| Admissions / Enrollment |
| Advising |
| Appointment |
| ESL Advising |
| New Accepted Student / Navigate |
| Student Financial Services |

Holdout accuracy is roughly **0.87** (see the notebook's conclusion for the full
train/eval history — final offline result was 0.874). The model predicts the
category only. The `training_phrases` table has a `subcategory` column, but
nothing reads or predicts it yet; subcategory prediction is on the roadmap.

## Design decisions

**Logistic Regression over LinearSVC.** Both perform similarly on this data, but
LogisticRegression gives calibrated `predict_proba()` output. That matters here:
low confidence predictions can be flagged for staff review instead of being
auto routed to a department.

**Splitting before augmentation.** An early version of the pipeline augmented the
data before the train/test split, which leaked near duplicate phrases across both
sides and reported a false 100% accuracy. Splitting first revealed the true
baseline (~0.40) and shaped the rest of the data strategy, where to add phrases,
which categories were actually confusable, and when more data stopped helping.

**A fixed holdout set for the retrain decision.** `/retrain` does not trust the
internal train/test split of a freshly trained pipeline to decide whether to
promote it. Instead it scores both the new pipeline and the current live pipeline
against `ml/holdout_test_set.csv`, a fixed 660-row set of `text,category` pairs
that is never used for training. The new model is promoted only if its holdout
accuracy is greater than or equal to the current model's. This keeps the
promote/reject decision comparable across retrains as the training table grows.

**Category only prediction for now.** There isn't enough training data per
subcategory to model it well, so the current model predicts category only.
Subcategory resolution is expected to be deterministic (a lookup) rather than
another source of model uncertainty, but neither the lookup nor subcategory
prediction is built yet.

**RDS security group allows all inbound IPs (`0.0.0.0/0`).** Render's free tier
has no fixed outbound IP, so there is no stable CIDR to allowlist. Access is still
protected by password plus SSL (`sslmode=require`). This is a deliberate,
documented tradeoff for a portfolio deployment, not an oversight, a production
setup would put the database behind a VPC or a fixed IP egress.

## Authentication

`/update-data` and `/retrain` require an `X-API-Key` header matching the
`STAFF_API_KEY` environment variable. A missing header returns `422`; a wrong key
returns `401`.

The `/` and `/admin` pages are served without authentication, and `main.py`
injects `STAFF_API_KEY` directly into the rendered HTML (through `base.html`), so
the browser can call the protected endpoints. This means the staff key is visible
in page source to anyone who can load either page, access control is effectively
"can you reach the site," not per-user. A real login/permissions system is on the
roadmap.

## Requirements

- Python 3.13
- A PostgreSQL database (the project uses AWS RDS in deployment)
- An Amazon S3 bucket for model storage, plus an IAM key pair with read/write access to it

Key dependencies (see `requirements.txt` for the pinned set): `fastapi`,
`uvicorn`, `scikit-learn`, `pandas`, `numpy`, `joblib`, `SQLAlchemy`,
`psycopg2-binary`, `boto3`, `Jinja2`, `python-dotenv`, `pytest`.

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
```

All five are read at import time (`retrain.py` builds the S3 client on import), so
the app and the test suite will not start without them. The model object is
stored in the bucket at key `model.joblib`.

Create the database table:

```bash
psql "$DATABASE_URL" -f ml/schema.sql
```

`training_phrases` has columns `id`, `text`, `category`, `subcategory` (nullable,
unused today), `created_at`, and `source` (defaults to `'seed'`).

Optionally seed it with the reference training data:

```bash
python ml/import_seed_data.py
```

## Running

```bash
uvicorn main:app --reload
```

The service listens on `http://127.0.0.1:8000`. On startup it pulls
`model.joblib` from S3 into `models/`. The prediction UI is served at `/` and the
retrain UI at `/admin`.

### Docker

```bash
docker build -t triage-copilot .
docker run -p 8000:8000 --env-file .env triage-copilot
```

## API

### `GET /`

Serves the staff prediction page (`index.html`).

### `GET /admin`

Serves the retrain page (`admin.html`), a single "Retrain Model" button that
POSTs to `/retrain`.

### `GET /health`

```json
{ "status": "healthy", "model_loaded": true }
```

### `POST /predict`

Request:

```json
{ "text": "I need a copy of my transcript" }
```

Response:

```json
{
  "category": "Admissions / Enrollment",
  "confidence": 0.912,
  "timestamp": "2026-09-02T00:00:00+00:00"
}
```

`text` must be non-empty (`422` otherwise). Inference errors return `500`.

### `POST /update-data`

Requires the `X-API-Key` header. Records a staff correction or confirmation into
the `training_phrases` table.

Request:

```json
{
  "text": "I finished my ESL placement exam",
  "correct_category": "ESL Advising",
  "source": "staff_corrected"
}
```

`text` and `correct_category` are required and must be non-empty (`422`
otherwise). `source` is optional and defaults to `"staff_corrected"`. The
frontend sends `source: "confirmed"` when staff confirm a prediction and
`source: "staff_corrected"` when they override it.

Response:

```json
{ "status": "Recorded" }
```

### `POST /retrain`

Requires the `X-API-Key` header. Runs the full retrain cycle synchronously
(roughly one to two minutes):

1. Rate limit: if `/retrain` succeeded in acquiring the lock within the last 300
   seconds, returns `429` without retraining.
2. Pull every row from `training_phrases` and train a new pipeline.
3. Score the new pipeline and the current live pipeline against
   `ml/holdout_test_set.csv`.
4. If the new accuracy is lower than the current accuracy, return without
   swapping:

   ```json
   {
     "swapped": false,
     "reason": "New model did not outperform current model",
     "current_accuracy": 0.871,
     "new_accuracy": 0.864
   }
   ```

5. Otherwise, copy the current `models/model.joblib` to a timestamped
   `models/model_backup_<UTC timestamp>.joblib`, write the new model to
   `models/model.joblib`, swap it into the running process, and upload it to S3:

   ```json
   {
     "swapped": true,
     "backup_saved_to": "models/model_backup_20260909_035331.joblib",
     "s3_backup_success": true,
     "previous_accuracy": 0.868,
     "new_accuracy": 0.879
   }
   ```

   `s3_backup_success` is `false` if the S3 upload failed; the local swap still
   happened.

## Testing

```bash
pytest
```

`test_main.py` covers `/health`, `/predict`, `/update-data` (including input
validation and API-key handling), and that `/` loads. It needs all five
environment variables set, and the `/update-data` test writes to whatever
database `DATABASE_URL` points at, so run it against a disposable database.

`test.py` is a small interactive CLI for manually probing the model (prints the
top 3 categories with probabilities):

```bash
python test.py
```

## Project layout

```
main.py                 FastAPI app: /, /admin, /health, /predict, /update-data, /retrain
retrain.py              training-data pull, pipeline training, holdout eval, local + S3 model backup
test_main.py            pytest suite for the API
test.py                 interactive CLI benchmark for the model
models/model.joblib     live scikit-learn pipeline (downloaded from S3 at startup)
models/model_backup_*.joblib   timestamped backups written by /retrain before a swap
base.html               shared Jinja layout (header, sidebar, injects STAFF_API_KEY)
index.html              prediction page (served at /)
admin.html              retrain page (served at /admin)
static/                 app.js, admin.js, nav.js, style.css
Dockerfile              container image (python:3.13-slim + uvicorn)
requirements.txt        pinned dependencies

ml/
  Staff_Triage_ML_Pipeline.ipynb   original training + evaluation notebook
  schema.sql                       training_phrases table definition
  import_seed_data.py              load seed_training_data.csv into the DB
  seed_training_data.csv           reference training dataset
  holdout_test_set.csv             fixed 660-row eval set used by /retrain
  *_contrastive_phrases.csv        LLM-generated / curated training phrases
  llm_generated_phrases.csv        raw LLM generation output
```

## Roadmap

Planned, not yet implemented:

- **Scheduled / automatic retraining**, today `/retrain` is manual (a button on
  `/admin` or a direct API call).
- **Real Spanish / bilingual support**, beyond the handful of Spanish phrases in
  the seed data.
- **Batch CSV retraining**, uploading a CSV of labeled phrases as a training
  input, rather than only the `training_phrases` table.
- **Subcategory prediction**, the schema has the column; nothing predicts it.
- **A full login / permissions system**, replacing the single shared
  `STAFF_API_KEY` that is currently embedded in every served page.
- **A review dashboard for corrections**, so staff corrections can be vetted
  before they feed the next retrain, instead of going straight into the training
  pool.

## CI/CD

`.github/workflows/tests.yml` (`Run Tests`):

1. On every push and pull request to `main`, install dependencies and run
   `pytest`. Needs repository secrets `DATABASE_URL`, `STAFF_API_KEY`,
   `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_S3_BUCKET`.
2. On push to `main` only, if tests pass, trigger a Render deploy via the
   `RENDER_DEPLOY_HOOK` secret.

## Security note

`.env` is git-ignored. Do not commit real credentials. This project's `.env`
holds a database password, an AWS access key pair, and the `STAFF_API_KEY`; if
any of those has ever been committed or shared, rotate it, rotate the RDS
password, deactivate and reissue the AWS key pair, and regenerate the
`STAFF_API_KEY`. Note also that `STAFF_API_KEY` is served inside the `/` and
`/admin` HTML by design, so it is not a secret from anyone who can load the site.

   `RENDER_DEPLOY_HOOK` secret.

## Security note

`.env` is git-ignored. Do not commit real credentials. If a `DATABASE_URL` with a
live password has ever been committed or shared, rotate that password.
