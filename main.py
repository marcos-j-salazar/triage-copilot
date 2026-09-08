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
from retrain import pull_training_data, train_new_pipeline, evaluate_current_model, backup_current_model, save_new_model, upload_model_to_s3, download_model_from_s3
import time



load_dotenv()
db_engine = create_engine(os.environ["DATABASE_URL"])
MODEL_PATH = "models/model.joblib"
ml_model = {}
STAFF_API_KEY = os.environ["STAFF_API_KEY"]

# cooldown timer for /retrain
_last_retrain_time = [0.0]

def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != STAFF_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

@asynccontextmanager
async def lifespan(app: FastAPI):
    download_model_from_s3()
    ml_model["pipeline"] = joblib.load(MODEL_PATH)
    yield
    ml_model.clear()

app = FastAPI(title="Staff Triage Copilot", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory=".")


class UpdateDataRequest(BaseModel):
    text: str = Field(..., min_length=1)
    correct_category: str = Field(..., min_length=1)
    source: str = Field(default="staff_corrected", min_length=1, description="Source of the correction")

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

    df = pull_training_data(db_engine)
    new_pipeline, new_train_acc, new_test_acc, X_test, y_test = train_new_pipeline(df)
    current_test_acc = evaluate_current_model(ml_model["pipeline"], X_test, y_test)

    if new_test_acc < current_test_acc:
        return {
            "swapped": False,
            "reason": "New model did not outperform current model",
            "current_accuracy": round(current_test_acc, 3),
            "new_accuracy": round(new_test_acc, 3)
        }

    backup_path = backup_current_model()
    save_new_model(new_pipeline)
    ml_model["pipeline"] = new_pipeline
    s3_upload_success = upload_model_to_s3()

    return {
        "swapped": True,
        "backup_saved_to": backup_path,
        "s3_backup_success": s3_upload_success,
        "previous_accuracy": round(current_test_acc, 3),
        "new_accuracy": round(new_test_acc, 3)
    }

@app.get("/admin")
def admin(request: Request):
    return templates.TemplateResponse(request, "admin.html", {"api_key": STAFF_API_KEY})