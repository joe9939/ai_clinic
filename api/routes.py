# AI Clinic - API Routes
import json
import glob
import os
import time
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

from models.base import PatientModel, DoctorModel
from engine import DiagnosticEngine, SymptomCard

app = FastAPI(title="AI Clinic", version="0.3.0",
              description="Diagnose your LLM's health. Not how smart it is, how sick it is.")

# Serve static frontend
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/dashboard")
async def dashboard():
    index = os.path.join(static_dir, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"error": "frontend not built"}

API_BASES = {
    "deepseek": "https://api.deepseek.com/v1",
    "openai": "https://api.openai.com/v1",
    "ollama": "http://localhost:11434/v1",
    "vllm": "http://localhost:8000/v1",
}


class TargetConfig(BaseModel):
    type: str = "deepseek"
    api_key: str
    model: str = "deepseek-chat"
    base_url: Optional[str] = None


class CheckupRequest(BaseModel):
    target: TargetConfig
    plan: list[str]
    judge_api_key: Optional[str] = None
    judge_model: str = "deepseek-chat"
    concurrency: int = 3
    samples: int = 20


def load_symptom_cards() -> dict[str, SymptomCard]:
    cards = {}
    for fpath in glob.glob(os.path.join(os.path.dirname(__file__), "..", "probes", "*.json")):
        try:
            card = SymptomCard.from_json(fpath)
            cards[card.probe_id] = card
        except Exception as e:
            print(f"  [skip] {fpath}: {e}")
    print(f"  loaded {len(cards)} symptom cards")
    return cards


SYMPTOM_CARDS = load_symptom_cards()


@app.get("/v1/symptoms")
async def list_symptoms():
    return {"symptoms": {k: v.to_dict() for k, v in SYMPTOM_CARDS.items()}}


@app.post("/v1/checkup")
async def run_checkup(req: CheckupRequest):
    start = time.time()

    # resolve target model
    base_url = req.target.base_url or API_BASES.get(req.target.type, "https://api.deepseek.com/v1")
    patient = PatientModel(api_key=req.target.api_key, model=req.target.model, base_url=base_url)

    # resolve judge
    judge_key = req.judge_api_key or req.target.api_key
    judge = DoctorModel(api_key=judge_key, model=req.judge_model)

    # resolve symptom cards
    cards = []
    for pid in req.plan:
        card = SYMPTOM_CARDS.get(pid)
        if not card:
            raise HTTPException(400, f"symptom '{pid}' not found")
        cards.append(card)

    # run diagnosis
    engine = DiagnosticEngine(patient_chat=patient.chat, judge_chat=judge.chat)
    result = await engine.run_plan(cards, concurrency=req.concurrency, samples=req.samples)

    result["duration_ms"] = int((time.time() - start) * 1000)
    result["checkup_id"] = f"ck_{int(start)}"
    result["model"] = req.target.model
    return result


@app.get("/")
async def root():
    return {
        "service": "AI Clinic",
        "version": "0.2.0",
        "docs": "/docs",
        "usage": "GET /v1/symptoms to list symptoms, POST /v1/checkup to diagnose",
    }
