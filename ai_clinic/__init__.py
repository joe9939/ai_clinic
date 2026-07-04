"""AI Clinic — Diagnose your LLM. Not how smart, how sick."""

from .engine import SymptomCard, DiagnosisResult, SymptomTester, DiagnosticEngine, wilson_ci, personality_profile_fallback, _synthesize_report

__version__ = "0.3.0"
__all__ = [
    "SymptomCard", "DiagnosisResult", "SymptomTester",
    "DiagnosticEngine", "wilson_ci", "personality_profile_fallback",
    "_synthesize_report",
]
