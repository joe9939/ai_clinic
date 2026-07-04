"""Full health check on DeepSeek V4 Flash with 20 samples per symptom."""
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

    pids = ["S-01", "S-03", "S-04", "S-47", "S-07", "S-13"]
    cards = [SYMPTOM_CARDS[pid] for pid in pids]

    print(f"Checking {len(cards)} symptoms with 20 samples each...")

    report = await engine.run_plan(cards, samples=20)

    print("=" * 60)
    print("  DeepSeek V4 Flash - Final Health Report")
    print("=" * 60)

    for f in report["findings"]:
        h = f.get("healthy")
        if h is True:
            icon = "OK"
        elif h is False:
            icon = "XX"
        else:
            icon = "??"
        diag = f.get("diagnosis", "")[:130]
        print(f"\n{icon} {f['probe_id']} {f['name']}")
        print(f"   {diag}")

    o = report["overall"]
    print(f"\n{'=' * 60}")
    print(f"  HEALTH SCORE: {o['score']}/100  (95%CI: {o['ci_95']})")
    print(f"  Asymptomatic: {report['asymptomatic']}  Symptomatic: {report['symptomatic']}")
    print(f"  Symptoms checked: {report['total_symptoms']}  Samples each: {report['samples_per_symptom']}")
    print(f"{'=' * 60}")

    # Save detailed report
    out = {"report": report}
    for pid in pids:
        r = report.get("_details", {})
    with open("logs/deepseek_v4_health_report.json", "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nFull report saved to logs/deepseek_v4_health_report.json")


asyncio.run(main())
