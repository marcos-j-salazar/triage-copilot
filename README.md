# Staff Triage Copilot

A machine learning service that routes student inquiries to the correct
front desk department at a community college. Trained primarily on English
text; the original seed data included limited Spanish coverage, but this
hasn't been systematically expanded. Staff paste what a student says, and the
API returns a predicted category with a confidence score. Corrections made by
staff are written back to a database to feed the next round of model training
(an active learning feedback loop).

## How it works

```
Student request (text)
        │
        ▼
  FastAPI  /predict  ──►  scikit-learn pipeline  ──►  { category, confidence, timestamp }
        │                 (TF-IDF + LogisticRegression, model.joblib)
        │
  FastAPI  /update-data  ──►  PostgreSQL (training_phrases)  ──►  future retraining
```

The classifier is a `Pipeline` of:

- `TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)`, word + bigram features
- `LogisticRegression(class_weight="balanced", max_iter=1000)`

It is trained offline in `ml/Staff_Triage_ML_Pipeline.ipynb` and exported to
`models/model.joblib`, which the API loads once at startup via the FastAPI
lifespan handler.

### Categories

| Category |
| --- |
| Admissions / Enrollment |
| Advising |
| Appointment |
| ESL Advising |
| New Accepted Student / Navigate |
| Student Financial Services |

Test accuracy is roughly **0.87** (see the notebook's conclusion for the full
train/eval history). Subcategory prediction is out of scope for the current model
and is expected to be handled as a lookup.

## Design decisions

**Logistic Regression over LinearSVC.** Both perform similarly on this data, but
LogisticRegression gives calibrated `predict_proba()` output. That matters here:
low confidence predictions can be flagged for staff review instead of being
auto routed to a department.

**Splitting before augmentation.** An early version of the pipeline augmented the
data before the train/test split, which leaked near duplicate phrases across both
sides and reported a false 100% accuracy. Splitting first revealed the true
baseline (~0.87) and shaped the rest of the data strategy, where to add phrases,
which categories were actually confusable, and when more data stopped helping.

**Category only prediction; subcategory as a lookup.** There isn't enough training
data per subcategory to model it well, so the model predicts category only.
Subcategory resolution is deterministic and handled as a lookup, it isn't
something worth introducing model uncertainty into.

**RDS security group allows all inbound IPs (`0.0.0.0/0`).** Render's free tier
has no fixed outbound IP, so there is no stable CIDR to allowlist. Access is still
protected by password plus SSL (`sslmode=require`). This is a deliberate,
documented tradeoff for a portfolio deployment, not an oversight, a production
setup would put the database behind a VPC or a fixed IP egress.

## Requirements

- Python 3.13
- A PostgreSQL database (the project uses AWS RDS in deployment)

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require
```

Create the database table:

```bash
psql "$DATABASE_URL" -f ml/schema.sql
```

Optionally seed it with the reference training data:

```bash
python ml/import_seed_data.py
```

## Running

```bash
uvicorn main:app --reload
```

The service listens on `http://127.0.0.1:8000`. A minimal web page is served at `/`.

### Docker

```bash
docker build -t triage-copilot .
docker run -p 8000:8000 --env-file .env triage-copilot
```

## API

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

Records a staff correction into the `training_phrases` table with `source = 'manual'`.

Request:

```json
{ "text": "I finished my ESL placement exam", "correct_category": "ESL Advising" }
```

Response:

```json
{ "status": "Recorded" }
```

Both fields are required and must be non empty (`422` otherwise).

## Testing

```bash
pytest
```

`test_main.py` covers `/health`, `/predict`, and `/update-data`, including input
validation. The `/update-data` tests write to whatever database `DATABASE_URL`
points at, so run them against a disposable database.

`test.py` is a small interactive CLI for manually probing the model (prints the
top 3 categories with probabilities):

```bash
python test.py
```

## Project layout

```
main.py                 FastAPI app: /, /health, /predict, /update-data
test_main.py            pytest suite for the API
test.py                 interactive CLI benchmark for the model
models/model.joblib     trained scikit-learn pipeline (loaded at startup)
index.html, static/     minimal front-end
Dockerfile              container image (python:3.13-slim + uvicorn)
requirements.txt        pinned dependencies

ml/
  Staff_Triage_ML_Pipeline.ipynb   training + evaluation notebook
  schema.sql                       training_phrases table definition
  import_seed_data.py              load seed_training_data.csv into the DB
  seed_training_data.csv           reference training dataset
  *_contrastive_phrases.csv        LLM-generated / curated training phrases
  llm_generated_phrases.csv        raw LLM generation output
```

## CI/CD

`.github/workflows/tests.yml`:

1. On every push and pull request to `main`, install dependencies and run `pytest`
   (needs a `DATABASE_URL` repository secret).
2. On push to `main` only, if tests pass, trigger a Render deploy via the
   `RENDER_DEPLOY_HOOK` secret.

## Security note

`.env` is git-ignored. Do not commit real credentials. If a `DATABASE_URL` with a
live password has ever been committed or shared, rotate that password.
