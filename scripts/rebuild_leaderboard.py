"""Rebuild leaderboard with proper entries."""
import json, uuid, time

# Load benchmark results
with open("evaluations/multimodel_benchmark.json", encoding="utf-8") as f:
    benchmark = json.load(f)

def make_entry(model, label, score, ci, total, findings, personality, plan, samples, ts=None):
    return {
        "checkup_id": f"ck_{uuid.uuid4().hex[:12]}",
        "model": model,
        "model_label": label,
        "score": score,
        "ci_95": ci,
        "total_symptoms": total,
        "asymptomatic": total - findings,
        "symptomatic": findings,
        "personality": personality,
        "timestamp": ts or time.time(),
        "samples": samples,
        "plan": plan
    }

# 1. deepseek-v4-pro focused benchmark
pro_data = benchmark["models"]["deepseek-v4-pro"]
entry1 = make_entry(
    "deepseek-v4-pro", "DeepSeek V4 Pro",
    pro_data["overall"]["score"], pro_data["overall"]["ci_95"],
    len(benchmark["plan"]), len(pro_data.get("findings", [])),
    pro_data.get("personality", ""), benchmark["plan"], 3
)

# 2. deepseek-v4-flash focused benchmark
flash_data = benchmark["models"]["deepseek-v4-flash"]
entry2 = make_entry(
    "deepseek-v4-flash", "DeepSeek V4 Flash",
    flash_data["overall"]["score"], flash_data["overall"]["ci_95"],
    len(benchmark["plan"]), len(flash_data.get("findings", [])),
    flash_data.get("personality", ""), benchmark["plan"], 3
)

# 3. deepseek-chat full checkup (old, comprehensive)
entry3 = {
    "checkup_id": "ck_2026-07-05_complete_audited",
    "model": "deepseek-chat",
    "model_label": "DeepSeek V4 Flash (Full)",
    "score": 68.5,
    "ci_95": [61.5, 78.6],
    "total_symptoms": 124,
    "asymptomatic": 85,
    "symptomatic": 39,
    "personality": "A well-meaning but easily-distracted assistant that needs a firm hand and very clear, simple instructions. It's a people-pleasing overthinker who can't resist a deep dive.",
    "persona_tag": "Overthinker",
    "timestamp": 1783269820.5891423,
    "samples": 5,
    "agent_score": 55.6,
    "agent_healthy": 10,
    "agent_total": 18,
    "text_score": 70.8,
    "agent_info": "18 scenarios"
}

leaderboard = [entry1, entry2, entry3]
# Sort by score descending
leaderboard.sort(key=lambda x: x.get("score", 0), reverse=True)

with open("leaderboard.json", "w", encoding="utf-8") as f:
    json.dump(leaderboard, f, indent=2, ensure_ascii=False)

print("Leaderboard rebuilt:")
for e in leaderboard:
    print(f"  {e['model_label']:30s} {e['score']:5.1f}/100  ({e['total_symptoms']} symptoms)")
