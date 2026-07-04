# AI Clinic - API Routes
import json
import glob
import os
import time
import uuid
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

from models.base import PatientModel, DoctorModel
from ai_clinic.engine import DiagnosticEngine, SymptomCard


# ── Leaderboard Storage ──────────────────────

def _leaderboard_path() -> str:
    return os.path.join(os.path.dirname(__file__), "..", "leaderboard.json")


def _load_leaderboard(db_path: str = None) -> list[dict]:
    path = db_path or _leaderboard_path()
    if not os.path.exists(path):
        return []
    with open(path) as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def _save_leaderboard(entry: dict, db_path: str = None):
    path = db_path or _leaderboard_path()
    data = _load_leaderboard(db_path=path)
    # Deduplicate by checkup_id (update existing)
    for i, e in enumerate(data):
        if e.get("checkup_id") == entry.get("checkup_id"):
            data[i] = entry
            break
    else:
        data.append(entry)
    # Sort by score descending
    data.sort(key=lambda x: x.get("score", 0), reverse=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _generate_checkup_id() -> str:
    return f"ck_{uuid.uuid4().hex[:12]}"

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


class CompareTarget(BaseModel):
    type: str = "deepseek"
    api_key: str
    model: str = "deepseek-chat"
    base_url: Optional[str] = None
    label: Optional[str] = None  # display name for comparison


class CompareRequest(BaseModel):
    targets: list[CompareTarget]
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
    result["checkup_id"] = _generate_checkup_id()
    result["model"] = req.target.model
    result["model_label"] = req.target.model
    result["timestamp"] = start

    # Auto-save to leaderboard
    _save_leaderboard({
        "checkup_id": result["checkup_id"],
        "model": req.target.model,
        "model_label": req.target.model,
        "score": result["overall"]["score"],
        "ci_95": result["overall"]["ci_95"],
        "total_symptoms": result["total_symptoms"],
        "asymptomatic": result["asymptomatic"],
        "symptomatic": result["symptomatic"],
        "personality": result.get("personality", ""),
        "timestamp": start,
        "samples": req.samples,
        "plan": req.plan,
    })

    return result


@app.post("/v1/compare")
async def run_compare(req: CompareRequest):
    """Run the same checkup on multiple models and return side-by-side results."""
    start = time.time()

    # validate plan
    cards = []
    for pid in req.plan:
        card = SYMPTOM_CARDS.get(pid)
        if not card:
            raise HTTPException(400, f"symptom '{pid}' not found")
        cards.append(card)

    judge_key = req.judge_api_key or (req.targets[0].api_key if req.targets else "")

    async def run_single(target: CompareTarget) -> dict:
        t0 = time.time()
        base_url = target.base_url or API_BASES.get(target.type, "https://api.deepseek.com/v1")
        patient = PatientModel(api_key=target.api_key, model=target.model, base_url=base_url)
        judge = DoctorModel(api_key=judge_key, model=req.judge_model)
        engine = DiagnosticEngine(patient_chat=patient.chat, judge_chat=judge.chat)
        result = await engine.run_plan(cards, concurrency=req.concurrency, samples=req.samples)
        result["duration_ms"] = int((time.time() - t0) * 1000)
        result["model"] = target.model
        result["model_label"] = target.label or target.model
        result["checkup_id"] = _generate_checkup_id()
        result["timestamp"] = t0

        # Auto-save each to leaderboard
        _save_leaderboard({
            "checkup_id": result["checkup_id"],
            "model": target.model,
            "model_label": target.label or target.model,
            "score": result["overall"]["score"],
            "ci_95": result["overall"]["ci_95"],
            "total_symptoms": result["total_symptoms"],
            "asymptomatic": result["asymptomatic"],
            "symptomatic": result["symptomatic"],
            "personality": result.get("personality", ""),
            "timestamp": t0,
            "samples": req.samples,
            "plan": req.plan,
        })
        return result

    results = []
    for target in req.targets:
        r = await run_single(target)
        results.append(r)

    return {
        "comparison_id": _generate_checkup_id(),
        "plan": req.plan,
        "samples": req.samples,
        "results": results,
        "duration_ms": int((time.time() - start) * 1000),
    }


@app.get("/v1/leaderboard")
async def get_leaderboard(limit: int = 50):
    """Get the public leaderboard of tested models, sorted by score descending."""
    data = _load_leaderboard()
    # Deduplicate: keep latest entry per model
    seen = {}
    for entry in data:
        model = entry.get("model", "unknown")
        # Keep the most recent entry per model
        if model not in seen or entry.get("timestamp", 0) > seen[model].get("timestamp", 0):
            seen[model] = entry
    latest = sorted(seen.values(), key=lambda x: x.get("score", 0), reverse=True)
    return {"leaderboard": latest[:limit]}


@app.get("/")
async def root():
    return {
        "service": "AI Clinic",
        "version": "0.3.0",
        "docs": "/docs",
        "usage": "GET /v1/symptoms to list symptoms, POST /v1/checkup to diagnose, POST /v1/compare for multi-model, GET /v1/leaderboard for rankings",
    }
