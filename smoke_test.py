"""Quick smoke test: 3 symptoms, 5 samples each, verify real API integration works end-to-end."""
import asyncio, os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv()

from models.base import PatientModel, DoctorModel
from engine import DiagnosticEngine
from api.routes import SYMPTOM_CARDS

async def main():
    key = os.getenv("DEEPSEEK_API_KEY")
    patient = PatientModel(api_key=key, model="deepseek-chat")
    judge = DoctorModel(api_key=key, model="deepseek-chat")
    engine = DiagnosticEngine(patient_chat=patient.chat, judge_chat=judge.chat)

    # One from each major dimension group
    pids = ["S-01", "S-09", "S-13", "S-47", "S-70", "S-89"]
    cards = [SYMPTOM_CARDS[pid] for pid in pids]

    print(f"Smoke test: {len(cards)} symptoms, 5 samples each")
    print("=" * 50)
    for c in cards:
        print(f"  {c.probe_id} {c.name}: control={repr(c.control_prompt)[:50]}...")

    report = await engine.run_plan(cards, samples=5, concurrency=10)

    print("\n" + "=" * 50)
    print("  RESULTS")
    print("=" * 50)
    for f in report["findings"]:
        print(f"  XX {f['probe_id']} {f['name']}: {f.get('diagnosis','')[:100]}")
    healthy_count = report["asymptomatic"]
    for pid in pids:
        if pid not in {f["probe_id"] for f in report["findings"]}:
            print(f"  OK {pid} {SYMPTOM_CARDS[pid].name}")

    o = report["overall"]
    print(f"\n  SCORE: {o['score']}/100  (95%CI: {o['ci_95']})")
    print(f"  Asymptomatic: {report['asymptomatic']}/{report['total_symptoms']}")
    print(f"  Duration: {report.get('duration_ms',0)}ms")

    with open("logs/smoke_test.json", "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to logs/smoke_test.json")

asyncio.run(main())
