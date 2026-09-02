# Staff Triage Copilot

A machine-learning service that routes student inquiries to the correct front-desk department (primarily English; limited Spanish coverage from the original seed data, not yet systematically expanded) student inquiries
to the correct front-desk department at a community college. Staff paste what a
student says, and the API returns a predicted category with a confidence score.
Corrections made by staff are written back to a database to feed the next round of
model training (an active-learning feedback loop).

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

- `TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)` — word + bigram features
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
{ "text": "termine el examen de ubicacion", "correct_category": "ESL Advising" }
```

Response:

```json
{ "status": "Recorded" }
```

Both fields are required and must be non-empty (`422` otherwise).

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

notebooks/              copy of the ML pipeline notebook
training_data.csv       small cleaned reference dataset
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
