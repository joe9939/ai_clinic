"""Embed symptom details into leaderboard so frontend doesn't need separate JSON files."""
import json

with open("leaderboard.json", encoding="utf-8") as f:
    lb = json.load(f)

for entry in lb:
    total = entry["total_symptoms"]
    model_key = entry.get("report_key", [None, None])[1] if entry.get("report_key") else None
    
    # Find the right data source
    if total >= 116:
        # Full checkup
        with open("evaluations/deepseek_v4_flash_full.json", encoding="utf-8") as f:
            data = json.load(f)
    else:
        # Multi-model benchmark
        with open("evaluations/multimodel_benchmark.json", encoding="utf-8") as f:
            data = json.load(f)
        if model_key:
            data = data.get("models", {}).get(model_key, {})
    
    # Extract symptom details
    findings = data.get("findings", [])
    symptoms_detail = []
    for f in findings[:50]:  # Limit to 50
        symptoms_detail.append({
            "probe_id": f.get("probe_id", ""),
            "name": f.get("name", ""),
            "dimension": f.get("dimension", ""),
            "diagnosis": f.get("diagnosis", ""),
            "evidence": f.get("evidence", []),
        })
    
    entry["symptoms_detail"] = symptoms_detail
    # Also copy the plan
    plan = data.get("plan", [])
    if plan:
        entry["plan"] = plan
    
    # Add long report URL (root-level for GH Pages)
    if total >= 116:
        entry["long_report_url"] = "report_long.json"
    
    print(f"{entry['model_label']:30s}  {len(symptoms_detail)} symptoms embedded")

with open("leaderboard.json", "w", encoding="utf-8") as f:
    json.dump(lb, f, indent=2, ensure_ascii=False)

print("\nLeaderboard updated with inline symptom data.")
