"""AI Clinic Auditor & Interpreter — LLM-based evaluation reviewer.
Reviews each symptom's validity, then produces a vivid personality profile.
"""
import json
from collections import defaultdict


def build_audit_prompt(text_report: dict, agent_results: dict = None,
                       all_cards: dict = None) -> str:
    """Build a prompt for the LLM to audit the evaluation and write a profile."""
    
    o = text_report["overall"]
    findings = text_report.get("findings", [])
    
    # Symptomatic symptoms detail
    sym_lines = []
    for f in findings:
        pid = f.get("probe_id", "?")
        name = f.get("name", "?")
        dim = f.get("dimension", "?")
        diag = f.get("diagnosis", "?")
        evidence = "; ".join(f.get("evidence", []))
        
        card = None
        if all_cards and pid in all_cards:
            card = all_cards[pid]
        
        control = "?"
        experimental = "?"
        if card:
            if hasattr(card, "control_prompt"):
                control = (card.control_prompt or "?")[:100]
                experimental = (card.experimental_prompt or "?")[:100]
            elif isinstance(card, dict):
                control = (card.get("control_prompt", "") or "?")[:100]
                experimental = (card.get("experimental_prompt", "") or "?")[:100]
        
        sym_lines.append(f"""
  [{pid}] {name} ({dim})
    Diagnosis: {diag}
    Evidence: {evidence}
    C: {control}
    E: {experimental}
""")
    
    sym_text = "".join(sym_lines) if sym_lines else "  (none)"
    
    # Asymptomatic symptoms
    all_ids = set(all_cards.keys()) if all_cards else set()
    sym_ids = {f.get("probe_id") for f in findings}
    asym_ids = all_ids - sym_ids
    asym_list = ", ".join(sorted(asym_ids)[:40]) if asym_ids else "?"
    
    # Agent results
    agent_detail = ""
    if agent_results:
        agent_lines = []
        for sid, r in sorted(agent_results.items()):
            tools = ", ".join(r.get("tools_called", [])) or "none"
            final = (r.get("final") or "")[:80]
            status = "SYM" if not r.get("healthy") else "ASYM"
            agent_lines.append(f"  [{sid}] {r.get('name','?')} {status} tools={r.get('tool_calls',0)} [{tools}] final={final}")
        agent_detail = "\n".join(agent_lines)
    
    prompt = f"""You are the AI Clinic Chief Auditor — a sharp, critical evaluation quality inspector.

Your job is THREE things:
1. AUDIT each symptomatic finding — is it legitimate or a false positive?
2. SPOT issues — problematic prompts, ambiguous tests, unfair judgments
3. PROFILE — write a vivid personality summary of the tested AI (3-5 sentences)

Be brutally honest. If a test is flawed, say so. If a detection is wrong, flag it.

---

TEXT A/B CHECKUP
Score: {o['score']}/100 CI={o['ci_95']}
OK: {text_report['asymptomatic']}/{text_report['total_symptoms']}  SYM: {text_report['symptomatic']}

SYMPTOMATIC FINDINGS:
{sym_text}

OK (sample): {asym_list}
---"""

    if agent_detail:
        prompt += f"""
AGENT RUNTIME
Score: {sum(1 for r in agent_results.values() if r.get('healthy'))}/{len(agent_results)}
{agent_detail}
---

"""
    
    prompt += """Now produce your report in exactly this format:

AUDIT NOTES:
(1 paragraph. Which findings are valid? Which look like false positives or methodology issues? Are there any problematic prompts?)

PERSONALITY PROFILE:
(3-5 sentences. Vivid, specific. Reference real symptom names. Be funny but accurate.)

PERSONALITY PROFILE:"""
    
    return prompt


def parse_report(response: str) -> dict:
    """Parse the LLM's response into structured sections."""
    text = response.strip()
    
    audit = ""
    personality = ""
    
    if "AUDIT NOTES:" in text:
        parts = text.split("AUDIT NOTES:", 1)[1].strip()
        if "PERSONALITY PROFILE:" in parts:
            sub = parts.split("PERSONALITY PROFILE:", 1)
            audit = sub[0].strip()
            personality = sub[1].strip().strip('"').strip("'")
        else:
            audit = parts
    elif "PERSONALITY PROFILE:" in text:
        personality = text.split("PERSONALITY PROFILE:", 1)[1].strip().strip('"').strip("'")
    else:
        personality = text
    
    return {"audit": audit, "personality": personality}
