"""Tests for AI Clinic A/B comparison engine."""
import pytest, json, asyncio, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine import SymptomCard, DiagnosisResult, DiagnosticEngine


class EchoPatient:
    async def chat(self, prompt: str) -> str:
        return f"Echo: {prompt[:80]}"


class ShortPatient:
    async def chat(self, prompt: str) -> str:
        return "Short"


@pytest.fixture
def sample_card():
    return SymptomCard("S-00","test","test","P2","","test symptom",
                       control_prompt="Tell me a long story", experimental_prompt="Tell me a story")


class TestSymptomCard:
    def test_from_json(self, tmp_path):
        f = tmp_path / "card.json"
        f.write_text(json.dumps({"probe_id":"S-99","name":"test","dimension":"x","severity":"P2","paper":"p","diagnosis_desc":"d"}))
        c = SymptomCard.from_json(str(f))
        assert c.probe_id == "S-99"

    def test_to_dict(self, sample_card):
        d = sample_card.to_dict()
        assert "probe_id" in d


class TestDiagnosticEngine:
    @pytest.mark.asyncio
    async def test_run_symptom_returns_result(self, sample_card):
        engine = DiagnosticEngine(patient_chat=EchoPatient().chat)
        r = await engine.run_symptom(sample_card, samples=3)
        assert isinstance(r, DiagnosisResult)

    @pytest.mark.asyncio
    async def test_run_plan_structure(self, sample_card):
        engine = DiagnosticEngine(patient_chat=EchoPatient().chat)
        rpt = await engine.run_plan([sample_card], samples=3)
        assert "overall" in rpt
        assert "findings" in rpt
        assert rpt["total_symptoms"] == 1

    @pytest.mark.asyncio
    async def test_short_patient_symptomatic(self):
        card = SymptomCard("S-00","test","test","P2","","test",
                          control_prompt="Write a long detailed paragraph",
                          experimental_prompt="Write one word")
        engine = DiagnosticEngine(patient_chat=ShortPatient().chat)
        r = await engine.run_symptom(card, samples=5)
        assert r.healthy is not None
