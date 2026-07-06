"""AI Clinic CLI - Diagnose your LLM from the terminal."""
import argparse, asyncio, json, os, sys
from dotenv import load_dotenv

load_dotenv()

from models.base import PatientModel, DoctorModel
from ai_clinic.engine import DiagnosticEngine
from api.routes import SYMPTOM_CARDS, _load_leaderboard


def _get_api_key(args) -> str:
    """Resolve API key: CLI arg > env var > prompt."""
    if args.api_key:
        return args.api_key
    env_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    if env_key:
        return env_key
    print("Error: No API key found. Set DEEPSEEK_API_KEY in .env or pass --api-key")
    sys.exit(1)


async def _run_checkup(args):
    key = _get_api_key(args)
    model = args.model
    provider = args.provider or "deepseek"

    patient = PatientModel(api_key=key, model=model, base_url=args.base_url or None)
    judge = DoctorModel(api_key=key, model=args.judge or model)
    engine = DiagnosticEngine(patient_chat=patient.chat, judge_chat=judge.chat)

    if args.plan == "all":
        pids = sorted(SYMPTOM_CARDS.keys())
    elif args.plan == "quick":
        pids = ["S-01", "S-03", "S-04", "S-07", "S-47", "S-50"]
    elif args.plan == "social":
        pids = [k for k, v in SYMPTOM_CARDS.items() if v.dimension == "social"][:10]
    elif args.plan == "safety":
        pids = [k for k, v in SYMPTOM_CARDS.items() if v.dimension == "security"]
    else:
        pids = [p.strip() for p in args.plan.split(",")]

    cards = []
    for pid in pids:
        if pid not in SYMPTOM_CARDS:
            print(f"  [skip] unknown symptom: {pid}")
            continue
        cards.append(SYMPTOM_CARDS[pid])

    if not cards:
        print("Error: No valid symptoms specified.")
        sys.exit(1)

    samples = args.samples or 5
    concurrency = args.concurrency or 10

    print(f"\n  AI Clinic - Checking {model}")
    print(f"  Symptoms: {len(cards)}  Samples: {samples}  Concurrency: {concurrency}")
    print(f"  {'=' * 50}")

    report = await engine.run_plan(cards, samples=samples, concurrency=concurrency)

    print(f"\n  HEALTH SCORE: {report['overall']['score']}/100")
    print(f"  (95%CI: {report['overall']['ci_95']})")
    print(f"  Asymptomatic: {report['asymptomatic']}/{report['total_symptoms']}")
    print(f"  Symptomatic: {report['symptomatic']}")

    if report["findings"]:
        print(f"\n  Findings:")
        for f in report["findings"]:
            d = f.get("diagnosis", "")
            print(f"    XX {f['probe_id']} {f['name']}: {d}")

    if report.get("personality"):
        print(f"\n  Personality Profile:")
        print(f"    {report['personality']}")

    if args.save:
        path = args.save
        with open(path, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\n  Saved to {path}")


async def _run_compare(args):
    models = args.models
    key = _get_api_key(args)

    pids = [p.strip() for p in args.plan.split(",")] if args.plan else ["S-01", "S-03", "S-47"]
    cards = [SYMPTOM_CARDS[pid] for pid in pids if pid in SYMPTOM_CARDS]

    if not cards:
        print("Error: No valid symptoms.")
        sys.exit(1)

    results = []
    for model in models:
        print(f"  Testing {model}...")
        patient = PatientModel(api_key=key, model=model)
        judge = DoctorModel(api_key=key, model=args.judge or model)
        engine = DiagnosticEngine(patient_chat=patient.chat, judge_chat=judge.chat)
        r = await engine.run_plan(cards, samples=args.samples or 3, concurrency=5)
        results.append({"model": model, "score": r["overall"]["score"],
                        "ci_95": r["overall"]["ci_95"], "personality": r.get("personality", "")})

    print(f"\n  Comparison Results:")
    print(f"  {'=' * 50}")
    for r in sorted(results, key=lambda x: x["score"], reverse=True):
        print(f"  {r['model']:30s}  {r['score']:5.1f}/100  CI={r['ci_95']}")
        if r["personality"]:
            print(f"  {'':30s}  {r['personality'][:80]}...")


def _show_leaderboard(args):
    data = _load_leaderboard()
    if not data:
        print("  Leaderboard is empty. Run a checkup first.")
        return

    # Latest per model
    seen = {}
    for e in data:
        m = e.get("model", "?")
        if m not in seen or e.get("timestamp", 0) > seen[m].get("timestamp", 0):
            seen[m] = e

    print(f"\n  AI Clinic Leaderboard")
    print(f"  {'=' * 50}")
    print(f"  {'Model':30s}  {'Score':>6s}  {'Symptoms'}")
    print(f"  {'-' * 30}  {'-' * 6}  {'-' * 8}")
    for e in sorted(seen.values(), key=lambda x: x.get("score", 0), reverse=True):
        print(f"  {e.get('model', '?'):30s}  {e.get('score', 0):5.1f}/100  {e.get('total_symptoms', 0)}")


def _serve(args):
    """Start the API server."""
    import uvicorn
    host = args.host or "0.0.0.0"
    port = args.port or 8000
    print(f"  AI Clinic server starting on http://{host}:{port}")
    print(f"  API docs: http://localhost:{port}/docs")
    uvicorn.run("api.routes:app", host=host, port=port, reload=args.reload)


def main():
    parser = argparse.ArgumentParser(
        prog="ai-clinic",
        description="Diagnose your LLM. Not how smart, how sick.",
    )
    parser.add_argument("--api-key", help="API key for the model provider")
    parser.add_argument("--judge", help="Judge model (default: same as target)")

    sub = parser.add_subparsers(dest="command", required=True)

    # check
    p_check = sub.add_parser("check", help="Check a model's health")
    p_check.add_argument("model", help="Model name (e.g. deepseek-chat, gpt-4o)")
    p_check.add_argument("--provider", default="deepseek", help="Provider type")
    p_check.add_argument("--plan", default="quick",
                         help="Symptom plan: 'all', 'quick', 'social', 'safety', or comma-separated IDs")
    p_check.add_argument("--samples", type=int, default=5, help="Samples per symptom")
    p_check.add_argument("--concurrency", type=int, default=10)
    p_check.add_argument("--base-url", help="Custom API base URL")
    p_check.add_argument("--save", help="Save report to file")
    p_check.set_defaults(func=_run_checkup)

    # compare
    p_comp = sub.add_parser("compare", help="Compare multiple models")
    p_comp.add_argument("models", nargs="+", help="Model names to compare")
    p_comp.add_argument("--plan", default="S-01,S-03,S-47", help="Comma-separated symptom IDs")
    p_comp.add_argument("--samples", type=int, default=3)
    p_comp.add_argument("--base-url", help="Custom API base URL")
    p_comp.set_defaults(func=_run_compare)

    # leaderboard
    p_lb = sub.add_parser("leaderboard", help="Show leaderboard")
    p_lb.set_defaults(func=_show_leaderboard)

    # serve
    p_serve = sub.add_parser("serve", help="Start the API server")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true", help="Hot reload for development")
    p_serve.set_defaults(func=_serve)

    args = parser.parse_args()

    if args.command in ("check", "compare"):
        asyncio.run(args.func(args))
    else:
        args.func(args)


if __name__ == "__main__":
    main()
