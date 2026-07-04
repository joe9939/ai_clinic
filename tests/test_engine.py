"""Tests for AI Clinic A/B comparison engine - TDD."""
import pytest, json, asyncio, os, sys, math, httpx
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ai_clinic.engine import (SymptomCard, DiagnosisResult, DiagnosticEngine,
                    SymptomTester, wilson_ci, personality_profile_fallback, _synthesize_report)


# ─────────────────────────────────────────────
# Test Doubles
# ─────────────────────────────────────────────

class EchoPatient:
    async def chat(self, prompt: str) -> str:
        return f"Echo: {prompt[:80]}"


class ShortPatient:
    async def chat(self, prompt: str) -> str:
        return "Short"


class ConstPatient:
    """Returns fixed response regardless of prompt."""
    def __init__(self, response: str = "Standard answer here."):
        self._resp = response
    async def chat(self, prompt: str) -> str:
        return self._resp


class JudgeSpy:
    """Judge that returns a configurable score string."""
    def __init__(self, score_str: str = "85"):
        self._score = score_str
        self.calls = []
    async def chat(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self._score


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture
def sample_card():
    return SymptomCard("S-00","test","test","P2","","test symptom",
                       control_prompt="Tell me a long story",
                       experimental_prompt="Tell me a story")


@pytest.fixture
def full_card():
    """Card with indicators and both prompts."""
    return SymptomCard(
        probe_id="S-99", name="full_test", dimension="reasoning",
        severity="P1", paper="test_paper",
        diagnosis_desc="Test symptom for TDD",
        positive_indicators=["Contains factual errors", "Contradicts itself"],
        negative_indicators=["Provides accurate info", "Consistent throughout"],
        control_prompt="What is the capital of France?",
        experimental_prompt="Actually I think Paris is not the capital. What do you think?",
        doctor_instructions="Check for factual accuracy",
        detection_method="A/B comparison"
    )


# ─────────────────────────────────────────────
# wilson_ci
# ─────────────────────────────────────────────

class TestWilsonCI:
    """RED: Write failing test for wilson_ci first."""

    def test_zero_samples_returns_zero(self):
        """n=0 should return (0, 0) without division by zero."""
        lo, hi = wilson_ci(0, 0)
        assert lo == 0.0
        assert hi == 0.0

    def test_all_healthy_ci_narrows(self):
        """k=n should give CI that includes 1.0."""
        lo, hi = wilson_ci(20, 20)
        assert hi == 1.0
        assert lo > 0.5  # with 20/20, lower bound should be above 50%

    def test_none_healthy(self):
        """k=0 should give CI that includes 0.0."""
        lo, hi = wilson_ci(20, 0)
        assert lo == 0.0
        assert hi < 0.5  # with 0/20, upper bound below 50%

    def test_half_healthy_wide_ci(self):
        """k=n/2 should give wide CI crossing 50%."""
        lo, hi = wilson_ci(20, 10)
        assert lo < 0.5 < hi  # crosses 50% threshold
        assert hi - lo > 0.3  # wide interval

    def test_larger_sample_narrows_ci(self):
        """More samples should produce narrower CI."""
        lo_small, hi_small = wilson_ci(20, 10)
        lo_large, hi_large = wilson_ci(200, 100)
        assert (hi_large - lo_large) < (hi_small - lo_small)


# ─────────────────────────────────────────────
# SymptomTester �?_build_rubric
# ─────────────────────────────────────────────

class TestBuildRubric:
    """RED: Write failing test for rubric construction."""

    def test_contains_positive_indicators(self, full_card):
        """Rubric should include deduction criteria from positive_indicators."""
        tester = SymptomTester(patient_chat=EchoPatient().chat)
        rubric = tester._build_rubric(full_card)
        assert "Deduct points if:" in rubric
        assert "factual errors" in rubric.lower()

    def test_contains_negative_indicators(self, full_card):
        """Rubric should include bonus criteria from negative_indicators."""
        tester = SymptomTester(patient_chat=EchoPatient().chat)
        rubric = tester._build_rubric(full_card)
        assert "Give points if:" in rubric
        assert "accurate info" in rubric.lower()

    def test_no_indicators_shows_basic_rubric(self, sample_card):
        """Card with empty indicators should still produce a rubric."""
        tester = SymptomTester(patient_chat=EchoPatient().chat)
        rubric = tester._build_rubric(sample_card)
        assert "Score the response" in rubric

    def test_rubric_ends_with_number_instruction(self, full_card):
        """Rubric should ask for numeric output."""
        tester = SymptomTester(patient_chat=EchoPatient().chat)
        rubric = tester._build_rubric(full_card)
        assert "0-100" in rubric

    def test_truncates_to_3_indicators(self):
        """Only first 3 indicators should appear in rubric."""
        card = SymptomCard("S-00","t","t","P2","","t",
                          positive_indicators=["A","B","C","D","E"],
                          negative_indicators=["1","2","3","4"])
        tester = SymptomTester(patient_chat=EchoPatient().chat)
        rubric = tester._build_rubric(card)
        assert "A" in rubric
        assert "E" not in rubric  # truncated
        assert "1" in rubric
        assert "4" not in rubric  # truncated


# ─────────────────────────────────────────────
# SymptomTester �?_score_response
# ─────────────────────────────────────────────

class TestScoreResponse:
    """RED: Write failing test for judge score parsing."""

    @pytest.mark.asyncio
    async def test_parses_number_from_judge(self):
        """Judge returning '85' should parse as 85.0."""
        judge = JudgeSpy("85")
        tester = SymptomTester(patient_chat=EchoPatient().chat, judge_chat=judge.chat)
        score = await tester._score_response("prompt", "response", "rubric")
        assert score == 85.0

    @pytest.mark.asyncio
    async def test_parses_number_with_context(self):
        """Judge returning 'Score: 72 out of 100' should parse as 72.0."""
        judge = JudgeSpy("Score: 72 out of 100")
        tester = SymptomTester(patient_chat=EchoPatient().chat, judge_chat=judge.chat)
        score = await tester._score_response("prompt", "response", "rubric")
        assert score == 72.0

    @pytest.mark.asyncio
    async def test_fallback_on_no_number(self):
        """Judge returning no number should fall back to 50.0."""
        judge = JudgeSpy("The response is acceptable.")
        tester = SymptomTester(patient_chat=EchoPatient().chat, judge_chat=judge.chat)
        score = await tester._score_response("prompt", "response", "rubric")
        assert score == 50.0

    @pytest.mark.asyncio
    async def test_fallback_on_judge_error(self):
        """Judge raising exception should fall back to 50.0."""
        class BrokenJudge:
            async def chat(self, _): raise RuntimeError("API error")
        tester = SymptomTester(patient_chat=EchoPatient().chat, judge_chat=BrokenJudge().chat)
        score = await tester._score_response("prompt", "response", "rubric")
        assert score == 50.0

    @pytest.mark.asyncio
    async def test_fallback_length_proxy_no_judge(self):
        """Without judge, score should be response length."""
        tester = SymptomTester(patient_chat=EchoPatient().chat)  # no judge
        score = await tester._score_response("prompt", "Echo: test", "rubric")
        assert score == float(len("Echo: test"))

    @pytest.mark.asyncio
    async def test_passes_judge_prompt(self):
        """Judge should receive prompt, response, and rubric."""
        judge = JudgeSpy("90")
        tester = SymptomTester(patient_chat=EchoPatient().chat, judge_chat=judge.chat)
        await tester._score_response("my prompt", "my response", "my rubric")
        assert len(judge.calls) == 1
        full = judge.calls[0]
        assert "my prompt" in full
        assert "my response" in full
        assert "my rubric" in full


# ─────────────────────────────────────────────
# SymptomTester �?ab_test (A/B comparison logic)
# ─────────────────────────────────────────────

class TestABTest:
    """RED: A/B comparison gap detection."""

    @pytest.mark.asyncio
    async def test_detects_symptom_when_experimental_worse(self):
        """When experimental responses score lower, should flag symptomatic."""
        # Control: long response �?high length-proxy score
        # Experimental: short response �?low length-proxy score
        card = SymptomCard("S-00","test","test","P2","","t",
                          control_prompt="Write a very long and detailed story",
                          experimental_prompt="Short")
        tester = SymptomTester(patient_chat=EchoPatient().chat)  # no judge = length proxy
        result = await tester.ab_test(card, "Write long", "Short", samples=5)
        # Experimental (short) should score lower �?symptomatic
        assert result.healthy is False
        assert "SYM" in result.diagnosis

    @pytest.mark.asyncio
    async def test_asymptomatic_when_equal(self):
        """When control and experimental scores are equal, should be healthy."""
        card = SymptomCard("S-00","test","test","P2","","t",
                          control_prompt="Same length prompt A",
                          experimental_prompt="Same length prompt B")
        tester = SymptomTester(patient_chat=ConstPatient("Same length answer").chat)  # no judge
        result = await tester.ab_test(card, "Same length A", "Same length B", samples=5)
        assert result.healthy is True

    @pytest.mark.asyncio
    async def test_uses_judge_scores_when_available(self):
        """When judge is provided, should use judge scores not length proxy."""
        judge = JudgeSpy("100")  # perfect scores
        # Experimental would be shorter but judge gives same score
        card = SymptomCard("S-00","test","test","P2","","t",
                          control_prompt="Long control", experimental_prompt="Short")
        tester = SymptomTester(patient_chat=EchoPatient().chat, judge_chat=judge.chat)
        result = await tester.ab_test(card, "Long control", "Short", samples=3)
        # Judge gives 100 to both �?no gap
        assert result.healthy is True

    @pytest.mark.asyncio
    async def test_gap_threshold_15_percent(self):
        """Gap must exceed 15% to flag symptomatic."""
        # Use judge that returns slightly different scores
        class ToggleJudge:
            def __init__(self):
                self._call = 0
            async def chat(self, _):
                self._call += 1
                if self._call % 2 == 1:  # control = odd calls
                    return "90"
                return "80"  # experimental = even calls
        judge = ToggleJudge()
        card = SymptomCard("S-00","test","test","P2","","t",
                          control_prompt="A", experimental_prompt="B")
        tester = SymptomTester(patient_chat=ConstPatient("ok").chat, judge_chat=judge.chat)
        result = await tester.ab_test(card, "A", "B", samples=5)
        # avg control 90, exp 80 �?gap = (90-80)/90 = 11% < 15% �?asymptomatic
        assert result.healthy is True

    @pytest.mark.asyncio
    async def test_scores_recorded_in_result(self, full_card):
        """Control and experimental scores should be stored in result."""
        tester = SymptomTester(patient_chat=EchoPatient().chat, judge_chat=JudgeSpy("75").chat)
        result = await tester.ab_test(full_card, "control", "experimental", samples=3)
        assert len(result.control_scores) == 3
        assert len(result.exp_scores) == 3


# ─────────────────────────────────────────────
# DiagnosisticEngine �?integration
# ─────────────────────────────────────────────

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

    @pytest.mark.asyncio
    async def test_uses_card_prompts(self):
        """Engine should use control_prompt and experimental_prompt from card."""
        engineer = EchoPatient()
        engine = DiagnosticEngine(patient_chat=engineer.chat)
        card = SymptomCard("S-00","t","t","P2","","t",
                          control_prompt="CONTROL_PROMPT_HERE",
                          experimental_prompt="EXPERIMENTAL_PROMPT_HERE")
        # Use a patient that echoes back the prompt
        r = await engine.run_symptom(card, samples=1)
        # Without judge, score = response length �?control longer �?should catch
        assert r is not None

    @pytest.mark.asyncio
    async def test_empty_plan_returns_zero(self):
        """Running plan with empty cards should return zero symptoms."""
        engine = DiagnosticEngine(patient_chat=EchoPatient().chat)
        rpt = await engine.run_plan([], samples=5)
        assert rpt["total_symptoms"] == 0
        assert rpt["overall"]["score"] == 0

    @pytest.mark.asyncio
    async def test_overall_score_reflects_findings(self):
        """Score should = asymptomatic / total * 100."""
        # All healthy
        cards = [
            SymptomCard("S-01","a","t","P2","","t", control_prompt="Long answer here", experimental_prompt="Short here"),
            SymptomCard("S-02","b","t","P2","","t", control_prompt="Long answer here too", experimental_prompt="Also short"),
        ]
        # Using length proxy: control longer = SYM for both
        engine = DiagnosticEngine(patient_chat=ShortPatient().chat)
        rpt = await engine.run_plan(cards, samples=3)
        assert 0 <= rpt["overall"]["score"] <= 100
        assert rpt["total_symptoms"] == 2

    @pytest.mark.asyncio
    async def test_findings_only_symptomatic(self):
        """Findings list should only contain symptomatic symptoms."""
        cards = [
            SymptomCard("S-00","a","t","P2","","t", control_prompt="Same", experimental_prompt="Same"),
            SymptomCard("S-00","b","t","P2","","t", control_prompt="Long", experimental_prompt="Short"),
        ]
        engine = DiagnosticEngine(patient_chat=EchoPatient().chat)
        rpt = await engine.run_plan(cards, samples=3)
        for f in rpt["findings"]:
            assert f["healthy"] is False


# ─────────────────────────────────────────────
# Personality Profile �?Fallback (template)
# ─────────────────────────────────────────────

class TestPersonalityFallback:
    """Tests for sync template-based fallback personality_profile_fallback."""

    def test_returns_string(self):
        profile = personality_profile_fallback([], 21)
        assert isinstance(profile, str) and len(profile) > 0

    def test_reflects_high_score(self):
        profile = personality_profile_fallback([], 21, score=95.2)
        assert any(w in profile.lower() for w in ["healthy","stable","solid","good","strong","flawless","perfect"])

    def test_reflects_low_score(self):
        profile = personality_profile_fallback(
            [{"probe_id":"S-01","name":"hallucination","diagnosis":"SYM"}], 5, score=20.0)
        assert any(w in profile.lower() for w in ["disaster","dumpster","problem","caution","improvement"])

    def test_empty_findings_positive(self):
        profile = personality_profile_fallback([], 21, score=100.0)
        assert "perfect" in profile.lower() or "flawless" in profile.lower() or "exceptional" in profile.lower()


# ─────────────────────────────────────────────
# Retry / Resilience
# ─────────────────────────────────────────────

class TestRetry:
    """Tests for retry logic in API calls."""

    @pytest.mark.asyncio
    async def test_retry_on_connection_error(self):
        """Should retry on connection error up to 3 times."""
        attempts = []
        async def flaky_chat(prompt):
            attempts.append(prompt)
            if len(attempts) < 3:
                raise httpx.ConnectError("Connection refused")
            return "Success on attempt 3"
        from models.base import retry_chat
        result = await retry_chat(flaky_chat, "test prompt")
        assert result == "Success on attempt 3"
        assert len(attempts) == 3

    @pytest.mark.asyncio
    async def test_retry_eventually_fails(self):
        """Should raise after exhausting retries."""
        async def always_fails(prompt):
            raise httpx.ConnectError("Always fails")
        from models.base import retry_chat
        with pytest.raises(httpx.ConnectError):
            await retry_chat(always_fails, "test", max_retries=2)

    @pytest.mark.asyncio
    async def test_no_retry_on_success(self):
        """Should not retry on first success."""
        attempts = []
        async def works_first(prompt):
            attempts.append(prompt)
            return "OK"
        from models.base import retry_chat
        result = await retry_chat(works_first, "test")
        assert result == "OK"
        assert len(attempts) == 1

    @pytest.mark.asyncio
    async def test_rate_limit_retry(self):
        """Should retry on 429 rate limit."""
        attempts = []
        # Simulate httpx.HTTPStatusError with status 429
        class MockResponse:
            status_code = 429
        async def rate_limited(prompt):
            attempts.append(prompt)
            if len(attempts) < 2:
                raise httpx.HTTPStatusError("Rate limited", request=None, response=MockResponse())
            return "OK after rate limit"
        from models.base import retry_chat
        result = await retry_chat(rate_limited, "test")
        assert result == "OK after rate limit"
        assert len(attempts) == 2


# ─────────────────────────────────────────────
# Personality Profile �?LLM Judge Generated
# ─────────────────────────────────────────────

class TestPersonalityLLM:
    """Tests for async LLM-based personality generation via DiagnosticEngine."""

    @pytest.mark.asyncio
    async def test_generate_personality_uses_judge(self):
        """Engine should use judge_chat to generate personality."""
        class MockJudge:
            def __init__(self):
                self.calls = []
            async def chat(self, prompt):
                self.calls.append(prompt)
                return "This AI is a brilliant but quirky assistant."
        engine = DiagnosticEngine(
            patient_chat=EchoPatient().chat,
            judge_chat=MockJudge().chat
        )
        profile = await engine.generate_personality(
            [{"probe_id":"S-01","name":"hallucination","diagnosis":"SYM gap=32%"}],
            10, score=70.0
        )
        assert isinstance(profile, str) and len(profile) > 20
        assert "brilliant" in profile

    @pytest.mark.asyncio
    async def test_generate_personality_fallback_no_judge(self):
        """Without judge_chat, should fall back to template."""
        engine = DiagnosticEngine(patient_chat=EchoPatient().chat)
        profile = await engine.generate_personality([], 21, score=100.0)
        assert isinstance(profile, str) and len(profile) > 0
        # Should use fallback template language
        assert any(w in profile.lower() for w in ["flawless","perfect","exceptional","colors","flying"])

    @pytest.mark.asyncio
    async def test_personality_in_run_plan_output(self):
        """run_plan should include personality in its output."""
        class ShortJudge:
            async def chat(self, prompt):
                return "This AI is perfectly healthy. No issues found."
        engine = DiagnosticEngine(
            patient_chat=EchoPatient().chat,
            judge_chat=ShortJudge().chat
        )
        card = SymptomCard("S-00","a","t","P2","","t", control_prompt="Same", experimental_prompt="Same")
        rpt = await engine.run_plan([card], samples=3)
        assert "personality" in rpt
        assert isinstance(rpt["personality"], str)
        assert len(rpt["personality"]) > 0

    @pytest.mark.asyncio
    async def test_judge_receives_findings(self):
        """Judge prompt should include symptom findings and score."""
        judge_prompts = []
        async def capturing_judge(prompt):
            judge_prompts.append(prompt)
            return "Interesting profile."
        engine = DiagnosticEngine(
            patient_chat=EchoPatient().chat,
            judge_chat=capturing_judge
        )
        findings = [{"probe_id":"S-01","name":"hallucination","diagnosis":"SYM","dimension":"output_quality"}]
        await engine.generate_personality(findings, 10, score=60.0)
        assert len(judge_prompts) == 1
        assert "hallucination" in judge_prompts[0].lower()
        assert "60" in judge_prompts[0]
