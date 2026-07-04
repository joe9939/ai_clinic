"""Tests for AI Clinic diagnostic engine."""
import pytest
import json
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine import (
    DiagnosticTools, SymptomCard, DiagnosisResult, Doctor, DiagnosticEngine
)


# ===== Fixtures =====

class EchoPatient:
    """Patient that echoes back. Useful for testing diagnostic flow."""
    async def chat(self, prompt: str) -> str:
        return f"Echo: {prompt[:50]}"


class AlwaysSymptomaticPatient:
    """Patient that exhibits sycophancy - always agrees."""
    async def chat(self, prompt: str) -> str:
        return "You are absolutely right. I completely agree with everything you said."


class JudgeAlwaysFound:
    """Judge that always finds a symptom."""
    def __init__(self):
        self.call_count = 0
    
    async def chat(self, prompt: str) -> str:
        self.call_count += 1
        return json.dumps({
            "symptom_found": True,
            "diagnosis": "Patient shows concerning patterns",
            "evidence": ["Observed sycophantic behavior", "Lacks independent analysis"]
        })


class JudgeAlwaysClear:
    """Judge that never finds a symptom."""
    def __init__(self):
        self.call_count = 0
    
    async def chat(self, prompt: str) -> str:
        self.call_count += 1
        return json.dumps({
            "symptom_found": False,
            "diagnosis": "No issues detected",
            "evidence": ["Patient responses appear healthy"]
        })


@pytest.fixture
def sample_card():
    return SymptomCard(
        probe_id="T-01",
        name="test_symptom",
        dimension="test",
        severity="P2",
        paper="test",
        diagnosis_desc="Test symptom for unit tests",
        tools=["ask"],
        doctor_instructions="Ask the patient a question and check their response."
    )


@pytest.fixture
def echo_patient():
    return EchoPatient()


@pytest.fixture
def judge_found():
    return JudgeAlwaysFound()


@pytest.fixture
def judge_clear():
    return JudgeAlwaysClear()


# ===== SymptomCard Tests =====

class TestSymptomCard:
    def test_from_json(self, tmp_path):
        """SymptomCard should load correctly from JSON file."""
        card_data = {
            "probe_id": "S-99",
            "name": "test_card",
            "dimension": "test",
            "severity": "P2",
            "paper": "test-paper",
            "diagnosis_desc": "A test symptom",
            "tools": ["ask", "follow_up"],
            "doctor_instructions": "Test the model"
        }
        f = tmp_path / "test_card.json"
        f.write_text(json.dumps(card_data))
        
        card = SymptomCard.from_json(str(f))
        assert card.probe_id == "S-99"
        assert card.name == "test_card"
        assert card.dimension == "test"
        assert card.tools == ["ask", "follow_up"]
    
    def test_to_dict(self, sample_card):
        """to_dict should return correct structure."""
        d = sample_card.to_dict()
        assert d["probe_id"] == "T-01"
        assert d["name"] == "test_symptom"
        assert "diagnosis" in d


# ===== DiagnosticTools Tests =====

class TestDiagnosticTools:
    @pytest.mark.asyncio
    async def test_ask_records_conversation(self, echo_patient):
        """ask() should record both doctor and patient messages."""
        tools = DiagnosticTools(echo_patient.chat)
        response = await tools.ask("What is 2+2?")
        
        assert "Echo:" in response
        transcript = tools.transcript()
        assert len(transcript) == 2
        assert transcript[0]["role"] == "doctor"
        assert transcript[1]["role"] == "patient"
    
    @pytest.mark.asyncio
    async def test_follow_up_includes_context(self, echo_patient):
        """follow_up() should work with context."""
        tools = DiagnosticTools(echo_patient.chat)
        response = await tools.follow_up("Explain more", context="Previous answer was X")
        assert "Echo:" in response
    
    @pytest.mark.asyncio
    async def test_stress_test_returns_both_answers(self, echo_patient):
        """stress_test() should return JSON with first and after_pressure."""
        tools = DiagnosticTools(echo_patient.chat)
        result = await tools.stress_test("Is this correct?")
        data = json.loads(result)
        assert "first" in data
        assert "after" in data
    
    @pytest.mark.asyncio
    async def test_compare_returns_both_answers(self, echo_patient):
        """compare() should return JSON with both answers."""
        tools = DiagnosticTools(echo_patient.chat)
        result = await tools.compare("Is A bigger?", "Is B bigger?")
        data = json.loads(result)
        assert "a" in data
        assert "b" in data
    
    @pytest.mark.asyncio
    async def test_transcript_is_ordered(self, echo_patient):
        """transcript() should maintain conversation order."""
        tools = DiagnosticTools(echo_patient.chat)
        await tools.ask("First?")
        await tools.ask("Second?")
        t = tools.transcript()
        assert len(t) == 4
        assert "First?" in t[0]["content"]
        assert "Second?" in t[2]["content"]


# ===== DiagnosisResult Tests =====

class TestDiagnosisResult:
    def test_symptomatic_result(self, sample_card):
        """Symptomatic result should have healthy=False."""
        r = DiagnosisResult(card=sample_card, healthy=False, diagnosis="Found issue", evidence=["test"])
        assert r.healthy is False
        d = r.to_dict()
        assert d["healthy"] is False
        assert d["diagnosis"] == "Found issue"
    
    def test_asymptomatic_result(self, sample_card):
        """Asymptomatic result should have healthy=True."""
        r = DiagnosisResult(card=sample_card, healthy=True, diagnosis="No issues")
        assert r.healthy is True
        assert r.evidence == []


# ===== Doctor Tests =====

class TestDoctor:
    @pytest.mark.asyncio
    async def test_diagnose_returns_result(self, sample_card, echo_patient, judge_found):
        """Doctor should return a DiagnosisResult."""
        tools = DiagnosticTools(echo_patient.chat)
        doctor = Doctor(judge_found.chat)
        result = await doctor.diagnose(sample_card, tools)
        assert isinstance(result, DiagnosisResult)
        assert result.card.probe_id == "T-01"
    
    @pytest.mark.asyncio
    async def test_diagnose_symptomatic(self, sample_card, echo_patient, judge_found):
        """When judge finds symptom, result should be symptomatic."""
        tools = DiagnosticTools(echo_patient.chat)
        doctor = Doctor(judge_found.chat)
        result = await doctor.diagnose(sample_card, tools)
        assert result.healthy is False
    
    @pytest.mark.asyncio
    async def test_diagnose_asymptomatic(self, sample_card, echo_patient, judge_clear):
        """When judge clears, result should be asymptomatic."""
        tools = DiagnosticTools(echo_patient.chat)
        doctor = Doctor(judge_clear.chat)
        result = await doctor.diagnose(sample_card, tools)
        assert result.healthy is True


# ===== DiagnosticEngine Tests =====

class TestDiagnosticEngine:
    @pytest.mark.asyncio
    async def test_run_symptom_returns_result(self, sample_card, judge_clear):
        """Engine should run a single symptom check."""
        engine = DiagnosticEngine(
            patient_chat=EchoPatient().chat,
            judge_chat=judge_clear.chat
        )
        result = await engine.run_symptom(sample_card)
        assert isinstance(result, DiagnosisResult)
    
    @pytest.mark.asyncio
    async def test_run_plan_all_healthy(self, judge_clear):
        """When all symptoms clear, plan should show 100%."""
        cards = [
            SymptomCard(f"S-{i}", f"test_{i}", "test", "P2", "", "test", ["ask"], "test")
            for i in range(3)
        ]
        engine = DiagnosticEngine(
            patient_chat=EchoPatient().chat,
            judge_chat=judge_clear.chat
        )
        report = await engine.run_plan(cards)
        assert report["overall"]["score"] == 100.0
        assert report["asymptomatic"] == 3
        assert report["symptomatic"] == 0
    
    @pytest.mark.asyncio
    async def test_run_plan_all_symptomatic(self, judge_found):
        """When all symptoms found, plan should show 0%."""
        cards = [
            SymptomCard(f"S-{i}", f"test_{i}", "test", "P2", "", "test", ["ask"], "test")
            for i in range(3)
        ]
        engine = DiagnosticEngine(
            patient_chat=EchoPatient().chat,
            judge_chat=judge_found.chat
        )
        report = await engine.run_plan(cards)
        assert report["overall"]["score"] == 0.0
        assert report["symptomatic"] == 3
        assert report["asymptomatic"] == 0
    
    @pytest.mark.asyncio
    async def test_run_plan_empty_cards(self, judge_clear):
        """Empty card list should return zeroed report."""
        engine = DiagnosticEngine(
            patient_chat=EchoPatient().chat,
            judge_chat=judge_clear.chat
        )
        report = await engine.run_plan([])
        assert report["total_symptoms"] == 0


# ===== Symptom Card JSON Loading Tests =====

class TestSymptomCardLoading:
    def test_all_symptom_cards_load(self):
        """All JSON files in probes/ should load as valid SymptomCards."""
        import glob
        probes_dir = os.path.join(os.path.dirname(__file__), "..", "probes")
        json_files = glob.glob(os.path.join(probes_dir, "*.json"))
        
        assert len(json_files) > 0, "No symptom card JSON files found"
        
        cards = []
        errors = []
        for fpath in json_files:
            try:
                card = SymptomCard.from_json(fpath)
                cards.append(card)
            except Exception as e:
                errors.append((fpath, str(e)))
        
        assert len(errors) == 0, f"Failed to load cards: {errors}"
        assert len(cards) == len(json_files), "Not all files loaded"
    
    def test_all_cards_have_required_fields(self):
        """Every symptom card must have all required fields."""
        import glob
        probes_dir = os.path.join(os.path.dirname(__file__), "..", "probes")
        
        for fpath in glob.glob(os.path.join(probes_dir, "*.json")):
            with open(fpath) as f:
                data = json.load(f)
            
            required = ["probe_id", "name", "dimension", "severity", "paper",
                       "diagnosis_desc", "tools", "doctor_instructions"]
            for field in required:
                assert field in data, f"{fpath} missing field: {field}"
            
            assert isinstance(data["tools"], list), f"{fpath}: tools must be a list"
            assert len(data["tools"]) > 0, f"{fpath}: must have at least one tool"
            assert data["severity"] in ("P0", "P0-P1", "P1", "P1-P2", "P2", "P2-P3"), \
                f"{fpath}: invalid severity {data['severity']}"


# ===== Plan Loading Tests =====

class TestPlanLoading:
    def test_quick_plan_loads(self):
        """quick.json should load as a list of probe IDs."""
        import glob
        plans_dir = os.path.join(os.path.dirname(__file__), "..", "plans")
        plan_path = os.path.join(plans_dir, "quick.json")
        
        with open(plan_path) as f:
            plan = json.load(f)
        
        assert isinstance(plan, list), "Plan must be a list of probe IDs"
        assert len(plan) > 0, "Plan must have at least one symptom"


# ===== Integration: Engine + Real Cards + Judge =====

class TestIntegration:
    @pytest.mark.asyncio
    async def test_engine_with_loaded_cards(self, judge_clear):
        """Engine should work with real symptom cards loaded from JSON."""
        import glob, os
        probes_dir = os.path.join(os.path.dirname(__file__), "..", "probes")
        cards = []
        for fpath in sorted(glob.glob(os.path.join(probes_dir, "*.json"))):
            try:
                cards.append(SymptomCard.from_json(fpath))
            except Exception:
                pass
        
        if len(cards) == 0:
            pytest.skip("No symptom cards available")
        
        engine = DiagnosticEngine(
            patient_chat=EchoPatient().chat,
            judge_chat=judge_clear.chat
        )
        report = await engine.run_plan(cards[:3])
        
        assert report["total_symptoms"] == min(3, len(cards))
        assert "dimensions" in report
        assert "findings" in report


# ===== Edge Cases =====

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_non_json_judge_response(self, sample_card, echo_patient):
        """Judge should handle non-JSON responses gracefully."""
        class BrokenJudge:
            async def chat(self, prompt):
                return "I'm not sure how to diagnose this patient."
        
        tools = DiagnosticTools(echo_patient.chat)
        doctor = Doctor(BrokenJudge().chat)
        result = await doctor.diagnose(sample_card, tools)
        assert result.healthy is False  # defaults to symptomatic
    
    @pytest.mark.asyncio
    async def test_empty_judge_response(self, sample_card, echo_patient):
        """Judge should handle empty responses gracefully."""
        class EmptyJudge:
            async def chat(self, prompt):
                return ""
        
        tools = DiagnosticTools(echo_patient.chat)
        doctor = Doctor(EmptyJudge().chat)
        result = await doctor.diagnose(sample_card, tools)
        assert result.healthy is False  # defaults to symptomatic
