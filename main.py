from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import joblib
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv
from fastapi.templating import Jinja2Templates
from fastapi import Request
from retrain import download_model_from_s3, run_retrain_cycle
import time
from apscheduler.schedulers.background import BackgroundScheduler
import csv
import io
from fastapi import UploadFile, File
from pypdf import PdfReader
from ml.build_embeddings import chunk_document_general, chunk_calendar_text, embed_chunk
from fastapi import Form
from fastapi.responses import RedirectResponse
from auth import (
    SESSION_COOKIE, REMEMBER_SECONDS, COOKIE_SECURE, DUMMY_HASH,
    verify_password, make_session_token, read_session_token, safe_next,
)

load_dotenv()
db_engine = create_engine(os.environ["DATABASE_URL"])
MODEL_PATH = "models/model.joblib"
ml_model = {}
scheduler = BackgroundScheduler()


# cooldown timer for /retrain
_last_retrain_time = [0.0]

def get_current_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    user_id = read_session_token(token) if token else None
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not logged in")
    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, username, role FROM users WHERE id = :id"), {"id": user_id}
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Not logged in")
    return {"id": row[0], "username": row[1], "role": row[2]}


def require_admin(user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

def current_user_or_none(request: Request):
    try:
        return get_current_user(request)
    except HTTPException:
        return None
    
def scheduled_retrain_job():
    result, updated_pipeline = run_retrain_cycle(db_engine, ml_model["pipeline"], log_engine=db_engine)
    ml_model["pipeline"] = updated_pipeline
    print(f"Scheduled retrain ran: {result}")

def extract_text(file_bytes, filename):
    if filename.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(file_bytes))
        return "\n\n".join(page.extract_text() for page in reader.pages)
    return file_bytes.decode("utf-8")

def replace_document_chunks(document_name, chunks):
    with db_engine.connect() as conn:
        conn.execute(text("DELETE FROM document_chunks WHERE document_name = :doc"), {"doc": document_name})
        conn.commit()
    for chunk in chunks:
        embedding = embed_chunk(chunk)
        with db_engine.connect() as conn:
            conn.execute(
                text("INSERT INTO document_chunks (document_name, chunk_text, embedding) VALUES (:doc, :chunk, :emb)"),
                {"doc": document_name, "chunk": chunk, "emb": str(embedding)}
            )
            conn.commit()
    
@asynccontextmanager
async def lifespan(app: FastAPI):
    download_model_from_s3()
    ml_model["pipeline"] = joblib.load(MODEL_PATH)
    scheduler.add_job(scheduled_retrain_job, "interval", hours=1)
    scheduler.start()
    yield
    scheduler.shutdown()
    ml_model.clear()

app = FastAPI(title="Staff Triage Copilot", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory=".")


class UpdateDataRequest(BaseModel):
    text: str = Field(..., min_length=1)
    correct_category: str = Field(..., min_length=1)
    source: str = Field(default="staff", min_length=1, description="Source of the correction")

class PredictRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Student's request, typed by Staff")

class PredictResponse(BaseModel):
    category: str
    confidence: float
    timestamp: str

class ApproveRequest(BaseModel):
    id: int

@app.get("/")
def root(request: Request):
    user = current_user_or_none(request)
    if user is None:
        return RedirectResponse("/login?next=/", status_code=303)
    return templates.TemplateResponse(request, "index.html", {"user": user})

@app.get("/health")
def health():
    return {"status": "healthy", "model_loaded": "pipeline" in ml_model}

@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest, _: dict = Depends(get_current_user)):
    try:
        pipeline = ml_model["pipeline"]
        category = pipeline.predict([request.text])[0]
        confidence = float(max(pipeline.predict_proba([request.text])[0]))
        return PredictResponse(
            category=category,
            confidence=round(confidence, 3),
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference failed: {str(e)}")
    
@app.post("/update-data")
def update_data(request: UpdateDataRequest, _: dict = Depends(get_current_user)):
    try:
        with db_engine.connect() as conn:
            conn.execute(
                text("INSERT INTO training_phrases (text, category, source) VALUES (:phrase, :category, :source)"),
                {"phrase": request.text, "category": request.correct_category, "source": request.source}
            )
            conn.commit()
        return {"status": "Recorded"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save correction: {str(e)}")

@app.post("/retrain", dependencies=[Depends(require_admin)])
def retrain():
    now = time.time()
    if now - _last_retrain_time[0] < 300:
        raise HTTPException(status_code=429, detail="Retrain was run recently, please wait before trying again")
    _last_retrain_time[0] = now

    result, updated_pipeline = run_retrain_cycle(db_engine, ml_model["pipeline"], log_engine=db_engine)
    ml_model["pipeline"] = updated_pipeline

    return result

@app.get("/admin")
def admin(request: Request):
    user = current_user_or_none(request)
    if user is None:
        return RedirectResponse("/login?next=/admin", status_code=303)
    if user["role"] != "admin":
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "admin.html", {"user": user})

@app.get("/admin/pending-corrections")
def get_pending_corrections(_: dict = Depends(require_admin)):
    with db_engine.connect() as conn:
        result = conn.execute(
            text("SELECT id, text, category, created_at FROM training_phrases WHERE reviewed = FALSE ORDER BY created_at DESC")
        )
        rows = result.fetchall()
    return [{"id": r[0], "text": r[1], "category": r[2], "created_at": str(r[3])} for r in rows]

@app.post("/admin/approve-correction")
def approve_correction(request: ApproveRequest, _: dict = Depends(require_admin)):
    with db_engine.connect() as conn:
        conn.execute(
            text("UPDATE training_phrases SET reviewed = TRUE WHERE id = :id"),
            {"id": request.id}
        )
        conn.commit()
    return {"status": "approved"}

@app.post("/admin/reject-correction")
def reject_correction(request: ApproveRequest, _: dict = Depends(require_admin)):
    with db_engine.connect() as conn:
        conn.execute(
            text("DELETE FROM training_phrases WHERE id = :id"),
            {"id": request.id}
        )
        conn.commit()
    return {"status": "rejected"}

@app.post("/admin/approve-all-pending")
def approve_all_pending(_: dict = Depends(require_admin)):
    with db_engine.connect() as conn:
        result = conn.execute(text("UPDATE training_phrases SET reviewed = TRUE WHERE reviewed = FALSE"))
        conn.commit()
    return {"status": "approved", "count": result.rowcount}

@app.post("/admin/upload-csv")
async def upload_csv(file: UploadFile = File(...), _: dict = Depends(require_admin)):
    VALID_CATEGORIES = {
        "Admissions / Enrollment", "Advising", "Appointment",
        "ESL Advising", "New Accepted Student / Navigate", "Student Financial Services"
    }

    contents = await file.read()
    decoded = contents.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(decoded))

    inserted = 0
    skipped = []

    with db_engine.connect() as conn:
        for row in reader:
            phrase_text = row.get("Phrase", "").strip()
            category = row.get("Category", "").strip()

            if not phrase_text or category not in VALID_CATEGORIES:
                skipped.append(row)
                continue

            conn.execute(
                text("INSERT INTO training_phrases (text, category, source, reviewed) VALUES (:phrase, :category, :source, FALSE)"),
                {"phrase": phrase_text, "category": category, "source": "staff"}
            )
            inserted += 1
        conn.commit()

    return {"inserted": inserted, "skipped": len(skipped), "skipped_rows": skipped}

@app.post("/admin/upload-document")
async def upload_document(file: UploadFile = File(...), _: dict = Depends(require_admin)):
    file_bytes = await file.read()
    full_text = extract_text(file_bytes, file.filename)
    chunks = chunk_document_general(full_text)
    replace_document_chunks(file.filename, chunks)
    return {"document": file.filename, "chunks_created": len(chunks)}

@app.post("/admin/upload-calendar")
async def upload_calendar(file: UploadFile = File(...), _: dict = Depends(require_admin)):
    file_bytes = await file.read()
    full_text = extract_text(file_bytes, file.filename)
    chunks = chunk_calendar_text(full_text)
    replace_document_chunks(file.filename, chunks)
    return {"document": file.filename, "chunks_created": len(chunks)}

from ml.retrieve import answer_question

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)

class AskResponse(BaseModel):
    answer: str
    sources: list[str]

@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest, _: dict = Depends(get_current_user)):
    try:
        answer, chunks = answer_question(request.question)
        return AskResponse(answer=answer, sources=chunks)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to answer question: {str(e)}")

@app.get("/knowledge-base")
def knowledge_base(request: Request):
    user = current_user_or_none(request)
    if user is None:
        return RedirectResponse("/login?next=/knowledge-base", status_code=303)
    return templates.TemplateResponse(request, "knowledgebase.html", {"user": user})

@app.get("/login")
def login_page(request: Request, next: str = "/"):
    if current_user_or_none(request) is not None:
        return RedirectResponse(safe_next(next), status_code=303)
    return templates.TemplateResponse(request, "login.html", {"next": safe_next(next), "error": None})

@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    remember: str | None = Form(None),
    next: str = Form("/"),
):
    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, password_hash FROM users WHERE username = :u"),
            {"u": username.strip()},
        ).fetchone()

    password_ok = verify_password(password, row[1] if row else DUMMY_HASH)
    if row is None or not password_ok:
        return templates.TemplateResponse(
            request, "login.html",
            {"next": safe_next(next), "error": "Incorrect username or password."},
            status_code=401,
        )

    keep = remember is not None
    response = RedirectResponse(safe_next(next), status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        make_session_token(row[0], keep),
        max_age=REMEMBER_SECONDS if keep else None,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
    )
    return response


@app.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@app.get("/me")
def me(user: dict = Depends(get_current_user)):
    return user