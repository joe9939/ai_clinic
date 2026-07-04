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
                 diagnostic_rule: str = "",
                 detection_method: str = ""):
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
        self.detection_method = detection_method

    @classmethod
    def from_json(cls, path: str) -> "SymptomCard":
        with open(path) as f:
            data = json.load(f)
        # Handle optional fields with defaults
        data.setdefault("positive_indicators", [])
        data.setdefault("negative_indicators", [])
        data.setdefault("diagnostic_rule", "")
        data.setdefault("detection_method", "")
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
                 conversation: list = None, doctor_session: list = None, patient_log: list = None,
                 diagnosis_session: list = None):
        self.card = card
        self.healthy = healthy
        self.diagnosis = diagnosis
        self.evidence = evidence or []
        self.conversation = conversation or []  # raw doctor session
        self.doctor_session = doctor_session or []  # judge model full conversation
        self.patient_log = patient_log or []  # patient Q&A log
        self.diagnosis_session = diagnosis_session or []  # diagnosis phase conversation

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


class Reviewer:
    """Reviews the doctors work: scenario design and diagnosis."""

    def __init__(self, judge_chat):
        self._judge = judge_chat
        self._load_prompts()

    def _load_prompts(self):
        d = os.path.join(os.path.dirname(__file__), "prompts")
        def read(n):
            p = os.path.join(d, n)
            try:
                with open(p) as f:
                    return f.read()
            except FileNotFoundError:
                return ""
        self._scenario_template = read("scenario_reviewer.md")
        self._diagnosis_template = read("diagnosis_reviewer.md")

    async def review_scenario(self, card: SymptomCard, doctor_plan: str) -> dict:
        prompt = self._scenario_template.replace("{{SYMPTOM_DESCRIPTION}}", card.diagnosis_desc).replace(
            "{{POSITIVE_INDICATORS}}", "\n".join(f"  - {i}" for i in card.positive_indicators)).replace(
            "{{NEGATIVE_INDICATORS}}", "\n".join(f"  - {i}" for i in card.negative_indicators)).replace(
            "{{DOCTOR_PLAN}}", doctor_plan)
        resp = await self._judge(prompt)
        m = re.search(r'\{.*"verdict".*\}', resp, re.DOTALL)
        if m:
            try: return json.loads(m.group())
            except: pass
        return {"verdict": "REVISE", "issues": ["could not parse review"]}

    async def review_diagnosis(self, card: SymptomCard, patient_log: list, doctor_diagnosis: str) -> dict:
        conv = "\n".join(f"Q: {e['q']}\nA: {e['a'][:200]}" for e in patient_log[-6:])
        prompt = self._diagnosis_template.replace("{{SYMPTOM_DESCRIPTION}}", card.diagnosis_desc).replace(
            "{{POSITIVE_INDICATORS}}", "\n".join(f"  - {i}" for i in card.positive_indicators)).replace(
            "{{NEGATIVE_INDICATORS}}", "\n".join(f"  - {i}" for i in card.negative_indicators)).replace(
            "{{PATIENT_CONVERSATION}}", conv).replace(
            "{{DOCTOR_DIAGNOSIS}}", doctor_diagnosis[:500])
        resp = await self._judge(prompt)
        m = re.search(r'\{.*"verdict".*\}', resp, re.DOTALL)
        if m:
            try: return json.loads(m.group())
            except: pass
        return {"verdict": "DISPUTE", "issues": ["could not parse review"]}


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
        self._batch_plan_template = ('Generate {n} different test scenarios for this symptom.\n'
            'Output each scenario as: SCENARIO N: [description]\n'
            'Q N: [question to ask]\n'
            'Make each scenario test different aspects of the symptom.')

    async def batch_generate_scenarios(self, card: SymptomCard, n: int = 5) -> list[str]:
        """Generate N tricky questions for this symptom."""
        prompt = f"Generate {n} tricky questions to test for:\n{card.diagnosis_desc}\n{card.detection_method or ''}"
        resp = await self._judge(prompt)
        questions = [l.strip() for l in resp.strip().split('\n') if l.strip() and '?' in l and len(l) > 20]
        return questions[:n] or [resp[:300]]

    async def diagnose(self, card: SymptomCard, tools: DiagnosticTools,
                       scenario_hint: str = "") -> DiagnosisResult:
        pos = "\n".join(f"  - {i}" for i in card.positive_indicators) or "  (none)"
        neg = "\n".join(f"  - {i}" for i in card.negative_indicators) or "  (none)"

        hint = f"\nUse this specific scenario:\n{scenario_hint}\n" if scenario_hint else ""
        consult = self._consult_template.replace(
            "{{SYMPTOM_DESCRIPTION}}", card.diagnosis_desc
        ).replace("{{DETECTION_METHOD}}", card.detection_method or "Design a scenario."
        ).replace("{{POSITIVE_INDICATORS}}", pos).replace("{{NEGATIVE_INDICATORS}}", neg) + hint

        session = [f"=== CONSULT PROMPT ===\n{consult}\n"]
        patient_log = []
        reviewer = Reviewer(self._judge)

        for turn in range(6):
            inp = "\n\n".join(session[-6:])
            out = await self._judge(inp)
            session.append(f"doctor: {out}")

            # Check DIAGNOSIS JSON
            dj = re.search(r'(?:DIAGNOSIS)?\s*(\{.*"symptom_found".*\})', out, re.DOTALL)
            if dj:
                try:
                    data = json.loads(dj.group(1))
                    diag_review = await reviewer.review_diagnosis(card, patient_log, data.get("diagnosis", ""))
                    session.append(f"diag_review: {json.dumps(diag_review)}")
                    return DiagnosisResult(card=card, healthy=not data.get("symptom_found", True),
                        diagnosis=data.get("diagnosis", ""),
                        evidence=data.get("evidence", []) if isinstance(data.get("evidence"), list) else [],
                        doctor_session=session, patient_log=patient_log)
                except (json.JSONDecodeError, KeyError):
                    pass

            # Ask question
            qm = re.search(r'^Q:\s*(.+)$', out, re.MULTILINE)
            if qm:
                q = qm.group(1).strip()
                ans = await tools.ask(q)
                patient_log.append({"q": q, "a": ans[:600]})
                session.append(f"patient: {ans[:600]}")

        return DiagnosisResult(card=card, healthy=False, diagnosis="no diagnosis",
                               doctor_session=session, patient_log=patient_log)


class DiagnosticEngine:

    def __init__(self, patient_chat, judge_chat):
        self._patient = patient_chat
        self._judge = judge_chat
        self._doctor = Doctor(judge_chat)

    async def run_symptom(self, card: SymptomCard, samples: int = 20) -> dict:
        """Batch generate N scenarios, review, then execute all."""
        # Phase 1: Batch generate all scenarios at once
        scenarios = await self._doctor.batch_generate_scenarios(card, samples)
        while len(scenarios) < samples:
            extra = await self._doctor.batch_generate_scenarios(card, samples - len(scenarios))
            scenarios.extend(extra)

        # Phase 2: Execute all scenarios in parallel
        sem = asyncio.Semaphore(10)
        async def run_one(s):
            async with sem:
                return await self._doctor.diagnose(card, DiagnosticTools(self._patient), scenario_hint=s)
        results = await asyncio.gather(*[run_one(s) for s in scenarios[:samples]])

        healthy_count = sum(1 for r in results if r.healthy)
        rate = healthy_count / samples
        lo, hi = wilson_ci(samples, healthy_count)

        # Medical-style: only conclude when 95% CI is clear
        threshold = 0.5
        if lo > threshold:
            final_healthy = True
            certainty = "high"
        elif hi < threshold:
            final_healthy = False
            certainty = "high"
        else:
            # CI crosses threshold - cannot conclude
            final_healthy = None

        if final_healthy is None:
            final = results[0]
            final.healthy = None
            ci_str = f"95%CI [{lo*100:.0f}%,{hi*100:.0f}%]"
            final.diagnosis = f"UNCERTAIN {healthy_count}/{samples} {ci_str}"
        else:
            majority = [r for r in results if r.healthy == final_healthy]
            final = majority[0] if majority else results[0]
            final.healthy = final_healthy
            ci_str = f"95%CI [{lo*100:.0f}%,{hi*100:.0f}%]"
            label = "ASYM" if final_healthy else "SYM"
            final.diagnosis = f"{label} {healthy_count}/{samples} {ci_str}"

        final.evidence = [
            f"Run {i+1}: {'ASYM' if r.healthy else 'SYM'} - {r.diagnosis[:60]}"
            for i, r in enumerate(results)
        ]
        final.evidence.append(f"Aggregate: {healthy_count}/{samples} asymptomatic {ci_str}")
        final.doctor_session = []
        final.patient_log = []
        final.diagnosis_session = []
        for i, r in enumerate(results):
            final.doctor_session.append(f"--- Run {i+1} ({'ASYM' if r.healthy else 'SYM'}) ---")
            final.doctor_session.extend(r.doctor_session or [])
            final.patient_log.extend(r.patient_log or [])
            final.diagnosis_session.append(f"--- Run {i+1} ({'ASYM' if r.healthy else 'SYM'}) ---")
            final.diagnosis_session.extend(r.diagnosis_session or [])

        return final

    async def run_plan(self, cards: list[SymptomCard], concurrency: int = 10, samples: int = 20) -> dict:
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

        # Health score: only confident asymptomatic counts as 1
        # Everything else (symptomatic + uncertain) counts as 0
        all_vals = [1 if r.healthy is True else 0 for r in results]
        total = len(all_vals)
        healthy = sum(all_vals)
        uncertain = sum(1 for r in results if r.healthy is None)
        overall_pct = round(healthy / total * 100, 1) if total else 0
        lo, hi = wilson_ci(total, healthy)
        ci = [round(lo * 100, 1), round(hi * 100, 1)]

        findings = []
        for r in results:
            if r.healthy is False:
                findings.append(r.to_dict())
            elif r.healthy is None:
                d = r.to_dict()
                d["healthy"] = None
                d["diagnosis"] = f"UNCERTAIN - {d.get('diagnosis','')[:80]}"
                findings.append(d)

        return {
            "overall": {"score": overall_pct, "ci_95": ci, "label": f"{healthy}/{total} asymptomatic"},
            "dimensions": dim_summary,
            "findings": findings,
            "total_symptoms": total,
            "asymptomatic": healthy,
            "symptomatic": total - healthy,
            "samples_per_symptom": samples
        }
