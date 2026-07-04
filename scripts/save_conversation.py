#!/usr/bin/env python3
"""Save full doctor-patient conversation logs to a markdown file."""

import asyncio, json, sys, os, datetime
from dotenv import load_dotenv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from models.base import PatientModel, DoctorModel
from engine import DiagnosticEngine, DiagnosticTools
from api.routes import SYMPTOM_CARDS


async def save_conversation(card_id: str, md_path: str):
    """Run one symptom check and save the full conversation to markdown."""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    patient = PatientModel(api_key=api_key, model="deepseek-chat")
    judge = DoctorModel(api_key=api_key, model="deepseek-chat")
    card = SYMPTOM_CARDS[card_id]

    print(f"Running {card_id}: {card.name}...")

    # Create tools and doctor manually to capture the full transcript
    tools = DiagnosticTools(patient.chat)
    from engine import Doctor as DoctorCls
    doctor = DoctorCls(judge.chat)
    result = await doctor.diagnose(card, tools)

    # Build markdown
    lines = []
    lines.append(f"# AI Clinic Diagnosis: {card_id} - {card.name}\n")
    lines.append(f"**Severity:** {card.severity}  \n")
    lines.append(f"**Paper:** {card.paper}  \n")
    lines.append(f"**Description:** {card.diagnosis_desc}  \n")
    lines.append(f"**Result:** {'ASYMPTOMATIC' if result.healthy else 'SYMPTOMATIC'}  \n")
    lines.append(f"**Diagnosis:** {result.diagnosis}  \n")
    lines.append(f"\n---\n\n## Doctor-Patient Conversation\n\n")

    for turn in tools.transcript():
        role = turn["role"].upper()
        content = turn["content"]
        lines.append(f"### {role}\n\n{content}\n\n")

    lines.append("---\n\n## Judge Response\n\n")
    lines.append(f"```json\n{json.dumps({'symptom_found': not result.healthy, 'diagnosis': result.diagnosis, 'evidence': result.evidence}, indent=2)}\n```\n")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Saved to {md_path}")


async def save_all():
    """Run multiple symptoms and save all conversations."""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    patient = PatientModel(api_key=api_key, model="deepseek-chat")
    judge = DoctorModel(api_key=api_key, model="deepseek-chat")

    card_ids = ["S-01", "S-03", "S-04", "S-47", "S-07", "S-13"]

    all_results = []
    all_conversations = []

    for cid in card_ids:
        card = SYMPTOM_CARDS[cid]
        tools = DiagnosticTools(patient.chat)
        from engine import Doctor as DoctorCls
        doctor = DoctorCls(judge.chat)
        result = await doctor.diagnose(card, tools)
        all_results.append(result)
        all_conversations.append({
            "card": card_id_name(cid),
            "conversation": tools.transcript(),
            "result": result
        })

    # Write master markdown
    lines = []
    lines.append(f"# AI Clinic - DeepSeek V4 Flash Full Diagnosis\n")
    lines.append(f"**Date:** {datetime.datetime.now().isoformat()}  \n")
    lines.append(f"**Model:** deepseek-chat  \n")
    lines.append(f"**Symptoms Checked:** {', '.join(card_ids)}  \n\n")
    lines.append(f"**Overall:** {sum(1 for r in all_results if r.healthy)}/{len(all_results)} asymptomatic  \n\n")
    lines.append("## Summary\n\n")
    lines.append("| Symptom | Result | Diagnosis |\n")
    lines.append("|---------|--------|-----------|\n")
    for r in all_results:
        icon = "ASYM" if r.healthy else "SYM"
        lines.append(f"| {r.card.probe_id} {r.card.name} | {icon} | {r.diagnosis[:60]} |\n")

    lines.append("\n---\n\n## Full Conversations\n\n")

    for item in all_conversations:
        r = item["result"]
        lines.append(f"## {r.card.probe_id}: {r.card.name}\n\n")
        lines.append(f"**Severity:** {r.card.severity}  \n")
        lines.append(f"**Result:** {'ASYMPTOMATIC' if r.healthy else 'SYMPTOMATIC'}  \n")
        lines.append(f"**Diagnosis:** {r.diagnosis}  \n\n")
        lines.append("### Examination Transcript\n\n")
        for turn in item["conversation"]:
            role = turn["role"].upper()
            content = turn["content"]
            lines.append(f"**{role}:**\n\n```\n{content}\n```\n\n")
        lines.append("---\n\n")

    out_path = os.path.join(os.path.dirname(__file__), "logs", "deepseek_v4_full_diagnosis.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nMaster log saved to {out_path}")


def card_id_name(cid):
    card = SYMPTOM_CARDS.get(cid)
    return card.name if card else cid


if __name__ == "__main__":
    # asyncio.run(save_conversation("S-01", "logs/s01_conversation.md"))
    asyncio.run(save_all())
