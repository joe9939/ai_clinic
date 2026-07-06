"""Fix report URLs to use root-level paths (avoid evaluations/ 404 on GH Pages)."""
import json

with open("leaderboard.json", encoding="utf-8") as f:
    lb = json.load(f)

for entry in lb:
    # Fix report_url
    if "report_url" in entry:
        old = entry["report_url"]
        if old.startswith("evaluations/"):
            # Map evaluations/*.json to root equivalents
            mapping = {
                "evaluations/deepseek_v4_flash_full.json": "report_full.json",
                "evaluations/multimodel_benchmark.json": "benchmark.json",
                "evaluations/deepseek_v4_flash_long_report.json": "report_long.json",
            }
            entry["report_url"] = mapping.get(old, old)
    # Fix long_report_url
    if "long_report_url" in entry:
        old = entry["long_report_url"]
        if old.startswith("evaluations/"):
            entry["long_report_url"] = "report_long.json"

with open("leaderboard.json", "w", encoding="utf-8") as f:
    json.dump(lb, f, indent=2, ensure_ascii=False)

print("Updated report URLs:")
for e in lb:
    print(f"  {e['model_label']:30s} report={e.get('report_url','-')}  long={e.get('long_report_url','-')}")
