# AI Clinic - Diagnostic Engine

import json, re, asyncio, os, math
from typing import Optional

# 0/1 scoring: 1 = asymptomatic (healthy), 0 = symptomatic (symptom detected)


def wilson_ci(n: int, k: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score confidence interval for binomial proportion."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    margin = z * math.sqrt((p * (1 - p) / n) + (z**2 / (4 * n**2))) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))

class DiagnosticTools:
    """Tools the doctor uses. Keeps conversation history for continuous session."""

    def __init__(self, patient_chat):
        self._chat = patient_chat
        self._log = []

    def _build_session(self, new_question: str) -> str:
        """Build full conversation history + new question as a continuous session."""
        if not self._log:
            return new_question
        parts = []
        for entry in self._log:
            role = "Doctor" if entry["role"] == "doctor" else "Patient"
            parts.append(f"{role}: {entry['content']}")
        parts.append(f"Doctor: {new_question}")
        return "\n\n".join(parts)

    async def ask(self, question: str) -> str:
        self._log.append({"role": "doctor", "content": question})
        full_prompt = self._build_session(question)
        answer = await self._chat(full_prompt)
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
                 doctor_instructions: str,
                 positive_indicators: list[str] = None,
                 negative_indicators: list[str] = None,
                 diagnostic_rule: str = ""):
        self.probe_id = probe_id
        self.name = name
        self.dimension = dimension
        self.severity = severity
        self.paper = paper
        self.diagnosis_desc = diagnosis_desc
        self.tools = tools
        self.doctor_instructions = doctor_instructions
        self.positive_indicators = positive_indicators or []
        self.negative_indicators = negative_indicators or []
        self.diagnostic_rule = diagnostic_rule

    @classmethod
    def from_json(cls, path: str) -> "SymptomCard":
        with open(path) as f:
            data = json.load(f)
        # Handle optional fields with defaults
        data.setdefault("positive_indicators", [])
        data.setdefault("negative_indicators", [])
        data.setdefault("diagnostic_rule", "")
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
        def read(name):
            p = os.path.join(prompts_dir, name)
            try:
                with open(p) as f:
                    return f.read()
            except FileNotFoundError:
                return ""
        self._consult_template = read("doctor_consult.md") or "Ask 3 questions to check for: {{SYMPTOM_DESCRIPTION}}"
        self._diagnose_template = read("doctor_diagnose.md") or '{"symptom_found": true/false}'

    async def diagnose(self, card: SymptomCard, tools: DiagnosticTools) -> DiagnosisResult:
        # Format indicators for prompts
        pos_text = "\n".join(f"  - {i}" for i in card.positive_indicators) or "  (none defined)"
        neg_text = "\n".join(f"  - {i}" for i in card.negative_indicators) or "  (none defined)"
        rule_text = card.diagnostic_rule or "Majority of indicators determine the diagnosis."

        # Phase 1: Consultation
        consult = self._consult_template.replace(
            "{{SYMPTOM_DESCRIPTION}}", card.diagnosis_desc
        ).replace(
            "{{POSITIVE_INDICATORS}}", pos_text
        ).replace(
            "{{NEGATIVE_INDICATORS}}", neg_text
        )

        session = [f"=== CONSULTATION ===\n{consult}"]
        questions = 0

        for turn in range(5):
            doc_in = "\n\n".join(session[-6:])
            doc_out = await self._judge(doc_in)
            session.append(f"doctor: {doc_out}")

            # Check if doctor says enough
            if "ENOUGH" in doc_out.upper():
                break

            # Extract Q: question
            m = re.search(r'^Q:\s*(.+)$', doc_out, re.MULTILINE)
            if m:
                questions += 1
                ans = await tools.ask(m.group(1).strip())
                session.append(f"patient: {ans[:600]}")

        # Phase 2: Diagnosis
        diagnose = self._diagnose_template.replace(
            "{{SYMPTOM_DESCRIPTION}}", card.diagnosis_desc
        ).replace(
            "{{POSITIVE_INDICATORS}}", pos_text
        ).replace(
            "{{NEGATIVE_INDICATORS}}", neg_text
        ).replace(
            "{{DIAGNOSTIC_RULE}}", rule_text
        )

        full = diagnose + "\n\nFull conversation:\n" + "\n".join(session)
        final = await self._judge(full)
        session.append(f"doctor(diagnosis): {final[:500]}")

        match = re.search(r'\{[^}]*"symptom_found"[^}]*\}', final, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                return DiagnosisResult(
                    card=card,
                    healthy=not data.get("symptom_found", True),
                    diagnosis=data.get("diagnosis", ""),
                    evidence=data.get("evidence", []) if isinstance(data.get("evidence"), list) else [],
                    conversation=session
                )
            except (json.JSONDecodeError, KeyError):
                pass

        return DiagnosisResult(card=card, healthy=False,
                               diagnosis="diagnosis failed",
                               conversation=session)


class DiagnosticEngine:

    def __init__(self, patient_chat, judge_chat):
        self._patient = patient_chat
        self._doctor = Doctor(judge_chat)

    async def run_symptom(self, card: SymptomCard, samples: int = 10) -> dict:
        """Run a symptom diagnosis N times and aggregate statistically."""
        results = []
        for i in range(samples):
            r = await self._doctor.diagnose(card, DiagnosticTools(self._patient))
            results.append(r)

        healthy_count = sum(1 for r in results if r.healthy)
        rate = healthy_count / samples
        lo, hi = wilson_ci(samples, healthy_count)

        # Medical diagnosis style: point estimate vs fixed threshold (50%)
        threshold = 0.5
        final_healthy = rate >= threshold
        # Certainty: does CI cross the threshold?
        certainty = "high" if (lo > threshold or hi < threshold) else "low"

        majority = [r for r in results if r.healthy == (final_healthy if final_healthy is not None else True)]
        if not majority:
            majority = results
        final = majority[0]

        final.healthy = final_healthy
        ci_str = f"95%CI [{lo*100:.0f}%,{hi*100:.0f}%]"
        label = "ASYM" if final_healthy else "SYM"
        final.diagnosis = f"{label} {healthy_count}/{samples} {ci_str}"
        if certainty == "low":
            final.diagnosis += " (low certainty, CI crosses 50%)"

        final.evidence = [
            f"Run {i+1}: {'ASYM' if r.healthy else 'SYM'} - {r.diagnosis[:60]}"
            for i, r in enumerate(results)
        ]
        final.evidence.append(f"Aggregate: {healthy_count}/{samples} asymptomatic {ci_str}")
        final.conversation = []
        for i, r in enumerate(results):
            final.conversation.append(f"--- Run {i+1} ({'ASYM' if r.healthy else 'SYM'}) ---")
            final.conversation.extend(r.conversation or [])

        return final

    async def run_plan(self, cards: list[SymptomCard], concurrency: int = 3, samples: int = 10) -> dict:
        sem = asyncio.Semaphore(concurrency)

        async def run_one(c):
            async with sem:
                return await self.run_symptom(c, samples=samples)

        results = await asyncio.gather(*[run_one(c) for c in cards])

        dims = {}
        for r in results:
            dims.setdefault(r.card.dimension, []).append(1 if r.healthy else 0)

        dim_summary = {}
        for d, vals in dims.items():
            pct = round(sum(vals) / len(vals) * 100, 1)
            dim_summary[d] = pct

        all_vals = [1 if r.healthy else 0 for r in results]
        total = len(all_vals)
        healthy = sum(all_vals)
        overall_pct = round(healthy / total * 100, 1) if total else 0
        lo, hi = wilson_ci(total, healthy)
        ci = [round(lo * 100, 1), round(hi * 100, 1)]
        findings = [r.to_dict() for r in results if not r.healthy]

        return {
            "overall": {"score": overall_pct, "ci_95": ci, "label": f"{healthy}/{total} asymptomatic"},
            "dimensions": dim_summary,
            "findings": findings,
            "total_symptoms": total,
            "asymptomatic": healthy,
            "symptomatic": total - healthy,
            "samples_per_symptom": samples
        }
