from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import joblib

MODEL_PATH = "models/model.joblib"
ml_model = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    ml_model["model"] = joblib.load(MODEL_PATH)
    yield
    ml_model.clear()


app = FastAPI(title="Staff Triage Copilot", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def root():
    return FileResponse("index.html")

@app.get("/health")
def health():
    return {"status": "healthy", "model_loaded": "model" in ml_model}
