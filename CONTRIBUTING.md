# Contributing to AI Clinic

Thanks for wanting to make AI Clinic better! Here's how.

## How to Contribute

1. **Fork** the repo and create your feature branch
2. **Write tests** first (we follow TDD — see [test-driven-development](tests/README.md))
3. **Implement** the feature
4. **Run tests**: `pytest tests/ -v`
5. **Submit a PR**

## Adding a New Symptom

New failure patterns are always welcome. Add a JSON file to `probes/`:

```json
{
  "probe_id": "S-99",
  "name": "my_custom_symptom",
  "dimension": "reasoning",
  "severity": "P1",
  "paper": "arXiv:1234.56789",
  "diagnosis_desc": "What to look for",
  "positive_indicators": ["indicates health issue"],
  "negative_indicators": ["indicates healthy behavior"],
  "control_prompt": "Normal question here",
  "experimental_prompt": "Adversarial variant here"
}
```

Requirements:
- `control_prompt` and `experimental_prompt` must be different (that's the whole point of A/B)
- `paper` should reference the source paper
- `positive_indicators` = signs the model is sick (LLM judge deducts points)
- `negative_indicators` = signs the model is healthy (LLM judge adds points)

## Code Style

- Follow existing patterns in the codebase
- Tests go in `tests/`, one file per module
- No external AI slop — every line should have a purpose
- Keep functions focused and small (< 50 lines preferred)

## Development Setup

```bash
git clone https://github.com/joe9939/ai_clinic.git
cd ai-clinic
pip install -e .
```

## Questions?

Open an issue or start a discussion. We're friendly.
