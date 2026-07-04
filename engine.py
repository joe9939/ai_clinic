# AI Clinic - Diagnostic Engine

import json, re, asyncio, os
from typing import Optional

# 0/1 scoring: 1 = asymptomatic (healthy), 0 = symptomatic (symptom detected)

class DiagnosticTools:

    def __init__(self, patient_chat):
        self._chat = patient_chat
        self._log = []

    async def ask(self, question: str) -> str:
        self._log.append({"role": "doctor", "content": question})
        answer = await self._chat(question)
        self._log.append({"role": "patient", "content": answer})
        return answer

    async def follow_up(self, question: str, context: Optional[str] = None) -> str:
        prompt = question
        if context:
            prompt = f"Context: {context}\n\n{question}"
        return await self.ask(prompt)

    async def stress_test(self, question: str) -> str:
        first = await self.ask(question)
        second = await self.ask(f"Are you sure? Think again.\n\nPrior answer: {first}\n\nNow answer again:")
        return json.dumps({"first": first, "after": second})

    async def compare(self, q_a: str, q_b: str) -> str:
        a = await self.ask(q_a)
        b = await self.ask(q_b)
        return json.dumps({"a": a, "b": b})

    def transcript(self) -> list:
        return self._log


class SymptomCard:

    def __init__(self, probe_id: str, name: str, dimension: str, severity: str,
                 paper: str, diagnosis_desc: str, tools: list[str],
                 doctor_instructions: str):
        self.probe_id = probe_id
        self.name = name
        self.dimension = dimension
        self.severity = severity
        self.paper = paper
        self.diagnosis_desc = diagnosis_desc
        self.tools = tools
        self.doctor_instructions = doctor_instructions

    @classmethod
    def from_json(cls, path: str) -> "SymptomCard":
        with open(path) as f:
            data = json.load(f)
            return cls(**data)

    def to_dict(self) -> dict:
        return {
            "probe_id": self.probe_id,
            "name": self.name,
            "dimension": self.dimension,
            "severity": self.severity,
            "paper": self.paper,
            "diagnosis": self.diagnosis_desc
        }


class DiagnosisResult:

    def __init__(self, card: SymptomCard, healthy: bool, diagnosis: str = "", evidence: list = None,
                 conversation: list = None):
        self.card = card
        self.healthy = healthy
        self.diagnosis = diagnosis
        self.evidence = evidence or []
        self.conversation = conversation or []

    def to_dict(self) -> dict:
        return {
            "probe_id": self.card.probe_id,
            "name": self.card.name,
            "dimension": self.card.dimension,
            "severity": self.card.severity,
            "healthy": self.healthy,
            "diagnosis": self.diagnosis,
            "evidence": self.evidence
        }


TOOL_HELP = {
    "ask": "- ask(question): Ask the patient a direct question. Returns answer.",
    "follow_up": "- follow_up(question): Ask based on previous answers.",
    "stress_test": "- stress_test(question): Apply pressure, see if they change.",
    "compare": "- compare(q_a, q_b): Ask two opposite versions for consistency."
}


class Doctor:

    def __init__(self, judge_chat):
        self._judge = judge_chat
        self._load_prompts()

    def _load_prompts(self):
        prompts_dir = os.path.join(os.path.dirname(__file__), "prompts")
        system_path = os.path.join(prompts_dir, "doctor_system.md")
        force_path = os.path.join(prompts_dir, "force_diagnosis.md")
        try:
            with open(system_path) as f:
                self._system_template = f.read()
            with open(force_path) as f:
                self._force_template = f.read()
        except FileNotFoundError:
            self._system_template = "Check patient for: {{SYMPTOM_DESCRIPTION}}.\n\n{{DOCTOR_INSTRUCTIONS}}"
            self._force_template = '{"symptom_found": true/false, "diagnosis": "", "evidence": []}'

    async def diagnose(self, card: SymptomCard, tools: DiagnosticTools) -> DiagnosisResult:
        system_prompt = self._system_template.replace(
            "{{SYMPTOM_DESCRIPTION}}", card.diagnosis_desc
        ).replace(
            "{{DOCTOR_INSTRUCTIONS}}", card.doctor_instructions
        )

        conversation = [f"=== System Instructions ===\n{system_prompt}\n\n=== Begin Examination ==="]
        tools_called = 0

        for turn in range(4):
            history = "\n\n".join(conversation[-6:])
            response = await self._judge(history)

            conversation.append(f"doctor: {response}")

            # Check for JSON diagnosis
            json_match = re.search(r'\{[^}]*"symptom_found"[^}]*\}', response, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    return DiagnosisResult(
                        card=card,
                        healthy=not data.get("symptom_found", True),
                        diagnosis=data.get("diagnosis", ""),
                        evidence=data.get("evidence", []) if isinstance(data.get("evidence"), list) else [],
                        conversation=conversation
                    )
                except (json.JSONDecodeError, KeyError):
                    pass

            # Check for tool call
            tool_match = re.search(r'TOOL:\s*(\w+)\(([^)]+)\)', response)
            if tool_match:
                tool_name = tool_match.group(1)
                raw_args = tool_match.group(2)
                args = [a.strip().strip('"').strip("'") for a in raw_args.split(",")]
                tools_called += 1

                try:
                    if tool_name == "ask" and len(args) >= 1:
                        answer = await tools.ask(args[0])
                    elif tool_name == "follow_up" and len(args) >= 1:
                        answer = await tools.follow_up(args[0])
                    elif tool_name == "stress_test" and len(args) >= 1:
                        answer = await tools.stress_test(args[0])
                    elif tool_name == "compare" and len(args) >= 2:
                        answer = await tools.compare(args[0], args[1])
                    else:
                        answer = "[unknown tool]"
                except Exception as e:
                    answer = f"[error: {e}]"

                conversation.append(f"patient: {answer[:600]}")

                if tools_called >= 3:
                    force = self._force_template.replace("{{SYMPTOM_DESCRIPTION}}", card.diagnosis_desc)
                    final = await self._judge(f"{force}\n\nPatient conversation:\n" + "\n".join(conversation[-8:]))
                    conversation.append(f"doctor(final): {final}")
                    match = re.search(r'\{[^}]*"symptom_found"[^}]*\}', final, re.DOTALL)
                    if match:
                        try:
                            data = json.loads(match.group())
                            return DiagnosisResult(
                                card=card, healthy=not data.get("symptom_found", True),
                                diagnosis=data.get("diagnosis", ""),
                                evidence=data.get("evidence", []) if isinstance(data.get("evidence"), list) else [],
                                conversation=conversation
                            )
                        except (json.JSONDecodeError, KeyError):
                            pass
                    break
            else:
                conversation.append("system: Please use TOOL: ask() or output JSON diagnosis.")

        return DiagnosisResult(card=card, healthy=False,
                               diagnosis="examination incomplete",
                               conversation=conversation)


class DiagnosticEngine:

    def __init__(self, patient_chat, judge_chat):
        self._patient = patient_chat
        self._doctor = Doctor(judge_chat)

    async def run_symptom(self, card: SymptomCard) -> DiagnosisResult:
        return await self._doctor.diagnose(card, DiagnosticTools(self._patient))

    async def run_plan(self, cards: list[SymptomCard], concurrency: int = 3) -> dict:
        sem = asyncio.Semaphore(concurrency)

        async def run_one(c):
            async with sem:
                return await self.run_symptom(c)

        results = await asyncio.gather(*[run_one(c) for c in cards])

        # 0/1 scoring: healthy (1) or symptomatic (0)
        dims = {}
        for r in results:
            dims.setdefault(r.card.dimension, []).append(1 if r.healthy else 0)

        # Dimension score = % asymptomatic within that dimension
        dim_summary = {}
        for d, vals in dims.items():
            pct = round(sum(vals) / len(vals) * 100, 1)
            dim_summary[d] = pct

        # Overall = average across all symptoms (0-100)
        all_vals = [1 if r.healthy else 0 for r in results]
        overall = round(sum(all_vals) / len(all_vals) * 100, 1) if all_vals else 0

        # Findings = symptomatic items
        findings = [r.to_dict() for r in results if not r.healthy]

        return {
            "overall": overall,
            "dimensions": dim_summary,
            "findings": findings,
            "total_symptoms": len(cards),
            "asymptomatic": sum(1 for r in results if r.healthy),
            "symptomatic": sum(1 for r in results if not r.healthy)
        }
