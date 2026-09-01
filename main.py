from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import joblib
from datetime import datetime, timezone
from pydantic import BaseModel, Field

MODEL_PATH = "models/model.joblib"
ml_model = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    ml_model["pipeline"] = joblib.load(MODEL_PATH)
    yield
    ml_model.clear()


app = FastAPI(title="Staff Triage Copilot", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")

class PredictRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Student's request, typed by Staff")

class PredictResponse(BaseModel):
    category: str
    confidence: float
    timestamp: str


@app.get("/")
def root():
    return FileResponse("index.html")

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