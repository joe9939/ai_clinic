"""Update leaderboard with fresh full checkup result."""
import json, uuid, time

with open("evaluations/deepseek_v4_flash_full.json", encoding="utf-8") as f:
    full_report = json.load(f)

with open("evaluations/multimodel_benchmark.json", encoding="utf-8") as f:
    benchmark = json.load(f)

def make_entry(model, label, score, ci, total, sym_count, personality, plan, samples, ts=None, extra=None):
    entry = {
        "checkup_id": f"ck_{uuid.uuid4().hex[:12]}",
        "model": model,
        "model_label": label,
        "score": score,
        "ci_95": ci,
        "total_symptoms": total,
        "asymptomatic": total - sym_count,
        "symptomatic": sym_count,
        "personality": personality or "",
        "timestamp": ts or time.time(),
        "samples": samples,
        "plan": plan
    }
    if extra:
        entry.update(extra)
    return entry

# 1. deepseek-v4-pro focused
pro = benchmark["models"]["deepseek-v4-pro"]
e1 = make_entry("deepseek-v4-pro", "DeepSeek V4 Pro",
    pro["overall"]["score"], pro["overall"]["ci_95"],
    len(benchmark["plan"]), len(pro.get("findings", [])),
    pro.get("personality", ""), benchmark["plan"], 3)

# 2. deepseek-v4-flash focused
flash = benchmark["models"]["deepseek-v4-flash"]
e2 = make_entry("deepseek-v4-flash", "DeepSeek V4 Flash",
    flash["overall"]["score"], flash["overall"]["ci_95"],
    len(benchmark["plan"]), len(flash.get("findings", [])),
    flash.get("personality", ""), benchmark["plan"], 3)

# 3. deepseek-v4-flash FULL (fresh result)
score = full_report["overall"]["score"]
ci = full_report["overall"]["ci_95"]
findings = full_report.get("findings", [])
personality = full_report.get("personality", "")
plan = full_report.get("plan", [])  # Will be all 116 sorted
e3 = make_entry("deepseek-v4-flash", "DeepSeek V4 Flash (Full)",
    score, ci, 116, len(findings),
    personality, plan, 3,
    extra={"text_score": score, "agent_info": "116 symptoms"})

leaderboard = [e1, e2, e3]
leaderboard.sort(key=lambda x: x.get("score", 0), reverse=True)

with open("leaderboard.json", "w", encoding="utf-8") as f:
    json.dump(leaderboard, f, indent=2, ensure_ascii=False)

print("Leaderboard updated:")
for e in leaderboard:
    print(f"  {e['model_label']:30s} {e['score']:5.1f}/100  ({e['total_symptoms']} sym, {e['symptomatic']} findings)")
