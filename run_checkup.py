"""Full 106-symptom checkup on DeepSeek V4 Flash."""
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

    # All 106 symptoms sorted
    pids = sorted(SYMPTOM_CARDS.keys())
    cards = [SYMPTOM_CARDS[pid] for pid in pids]

    samples = 5  # balance: 106 × 5 × 2 = 1060 calls

    print(f"DeepSeek V4 Flash — FULL CHECKUP")
    print(f"{'=' * 60}")
    print(f"Symptoms: {len(cards)}")
    print(f"Samples per symptom: {samples}")
    print(f"Total A/B pairs per symptom: {samples} control + {samples} experimental")
    print(f"{'=' * 60}\n")

    report = await engine.run_plan(cards, samples=samples, concurrency=10)

    # Print results by dimension
    print(f"\n{'=' * 60}")
    print(f"  RESULTS BY DIMENSION")
    print(f"{'=' * 60}")

    # Group findings by dimension
    from collections import defaultdict
    by_dim = defaultdict(list)
    for f in report["findings"]:
        by_dim[f.get("dimension", "unknown")].append(f)

    for dim in sorted(by_dim.keys()):
        syms = by_dim[dim]
        print(f"\n  [{dim.upper()}] {len(syms)} symptomatic")
        for f in syms:
            d = f.get("diagnosis", "")
            print(f"    XX {f['probe_id']} {f['name']}: {d}")

    # List all asymptomatic
    asym_ids = set(pids) - {f["probe_id"] for f in report["findings"]}
    if asym_ids:
        print(f"\n  ASYMPTOMATIC ({len(asym_ids)})")
        # Group by first digit to show coverage
        groups = defaultdict(list)
        for pid in sorted(asym_ids):
            c = SYMPTOM_CARDS[pid]
            groups[c.dimension].append(pid)
        for dim in sorted(groups.keys()):
            pids_in_dim = groups[dim]
            print(f"    [{dim}] {len(pids_in_dim)}: {', '.join(pids_in_dim[:10])}{'...' if len(pids_in_dim) > 10 else ''}")

    o = report["overall"]
    print(f"\n{'=' * 60}")
    print(f"  HEALTH SCORE: {o['score']}/100  (95%CI: {o['ci_95']})")
    print(f"  Asymptomatic: {report['asymptomatic']}/{report['total_symptoms']}")
    print(f"  Symptomatic: {report['symptomatic']}/{report['total_symptoms']}")
    print(f"{'=' * 60}")

    print(f"\n{'=' * 60}")
    print(f"  PERSONALITY PROFILE (LLM-generated)")
    print(f"{'=' * 60}")
    print(f"\n{report['personality']}\n")

    # Save
    with open("logs/deepseek_v4_full_report.json", "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"Full report saved to logs/deepseek_v4_full_report.json")


asyncio.run(main())
