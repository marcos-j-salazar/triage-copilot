from fastapi import FastAPI, HTTPException, Header, Depends
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
from retrain import pull_training_data, train_new_pipeline, evaluate_current_model, backup_current_model, save_new_model, upload_model_to_s3, download_model_from_s3, load_holdout_set, run_retrain_cycle
import time
from apscheduler.schedulers.background import BackgroundScheduler


load_dotenv()
db_engine = create_engine(os.environ["DATABASE_URL"])
MODEL_PATH = "models/model.joblib"
ml_model = {}
STAFF_API_KEY = os.environ["STAFF_API_KEY"]
scheduler = BackgroundScheduler()


# cooldown timer for /retrain
_last_retrain_time = [0.0]

def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != STAFF_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

def scheduled_retrain_job():
    result, updated_pipeline = run_retrain_cycle(db_engine, ml_model["pipeline"], log_engine=db_engine)
    ml_model["pipeline"] = updated_pipeline
    print(f"Scheduled retrain ran: {result}")

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


@app.get("/")
def root(request: Request):
    return templates.TemplateResponse(request, "index.html", {"api_key": STAFF_API_KEY})

@app.get("/health")
def health():
    return {"status": "healthy", "model_loaded": "pipeline" in ml_model}

@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest):
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
def update_data(request: UpdateDataRequest, _: None = Depends(verify_api_key)):
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

@app.post("/retrain", dependencies=[Depends(verify_api_key)])
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
    return templates.TemplateResponse(request, "admin.html", {"api_key": STAFF_API_KEY})