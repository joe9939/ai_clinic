"""Clean up leaderboard: merge duplicate models, ensure featured card logic."""
import json, uuid, time

with open("leaderboard.json", encoding="utf-8") as f:
    data = json.load(f)

# Merge: 'deepseek-chat' and 'deepseek-v4-flash' are the SAME model
# Keep the entry with better data (more symptoms tested)
merge_rules = {
    "deepseek-chat": "deepseek-v4-flash",   # old name → new name
}

for old_name, new_name in merge_rules.items():
    old_entries = [e for e in data if e.get("model") == old_name]
    new_entries = [e for e in data if e.get("model") == new_name]
    
    if old_entries and new_entries:
        # Merge: keep the one with more symptoms tested
        old = old_entries[0]
        new = new_entries[0]
        old_symptoms = old.get("total_symptoms", 0)
        new_symptoms = new.get("total_symptoms", 0)
        
        if old_symptoms > new_symptoms:
            # Keep old stats but use new model name
            merged = dict(old)
            merged["model"] = new_name
            merged["model_label"] = "DeepSeek V4 Flash"
            # Remove both and add merged
            data = [e for e in data if e.get("model") not in (old_name, new_name)]
            data.append(merged)
            print(f"Merged {old_name} ({old_symptoms} sym) → {new_name}: combined result")
        else:
            # New entry is better, just remove old
            data = [e for e in data if e.get("model") != old_name]
            # Update label
            for e in data:
                if e.get("model") == new_name:
                    e["model_label"] = "DeepSeek V4 Flash"
            print(f"Removed duplicate {old_name}, kept {new_name} ({new_symptoms} sym)")

# Sort by score descending (first entry = featured card)
data.sort(key=lambda x: x.get("score", 0), reverse=True)

with open("leaderboard.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"\nLeaderboard cleaned: {len(data)} entries")
for e in data:
    print(f"  {e['model']:30s} {e['score']:5.1f}/100  ({e['total_symptoms']} symptoms)")
