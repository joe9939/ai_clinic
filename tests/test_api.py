"""Tests for AI Clinic API routes — comparison, leaderboard."""
import pytest, json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from api.routes import app, SYMPTOM_CARDS, _load_leaderboard, _save_leaderboard, _generate_checkup_id


@pytest.fixture
def client():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestLeaderboardStorage:
    """RED: Write failing tests for leaderboard persistence."""

    def test_generate_checkup_id(self):
        """Checkup ID should be unique and start with 'ck_'."""
        cid = _generate_checkup_id()
        assert cid.startswith("ck_")
        assert len(cid) > 4

    def test_save_and_load_leaderboard(self, tmp_path):
        """Saved entry should be loadable."""
        entry = {
            "checkup_id": "ck_test",
            "model": "deepseek-chat",
            "score": 69.8,
            "ci_95": [60.5, 77.7],
            "total_symptoms": 106,
            "asymptomatic": 74,
            "symptomatic": 32,
            "personality": "Test AI personality",
            "timestamp": time.time(),
        }
        _save_leaderboard(entry, db_path=str(tmp_path / "leaderboard.json"))
        data = _load_leaderboard(db_path=str(tmp_path / "leaderboard.json"))
        assert len(data) == 1
        assert data[0]["model"] == "deepseek-chat"
        assert data[0]["score"] == 69.8

    def test_leaderboard_empty(self, tmp_path):
        """Empty file should return empty list."""
        data = _load_leaderboard(db_path=str(tmp_path / "empty.json"))
        assert data == []

    def test_leaderboard_sorted_by_score_desc(self, tmp_path):
        """Leaderboard should return entries sorted by score descending."""
        entries = [
            {"checkup_id": "ck_1", "model": "A", "score": 50.0, "timestamp": 1},
            {"checkup_id": "ck_2", "model": "B", "score": 80.0, "timestamp": 2},
            {"checkup_id": "ck_3", "model": "C", "score": 70.0, "timestamp": 3},
        ]
        for e in entries:
            _save_leaderboard(e, db_path=str(tmp_path / "sorted.json"))
        data = _load_leaderboard(db_path=str(tmp_path / "sorted.json"))
        assert data[0]["model"] == "B"  # 80 highest
        assert data[1]["model"] == "C"  # 70
        assert data[2]["model"] == "A"  # 50 lowest

    def test_leaderboard_dedup_by_checkup_id(self, tmp_path):
        """Same checkup_id should update, not duplicate."""
        e1 = {"checkup_id": "ck_same", "model": "A", "score": 50.0, "timestamp": 1}
        e2 = {"checkup_id": "ck_same", "model": "A", "score": 80.0, "timestamp": 2}
        _save_leaderboard(e1, db_path=str(tmp_path / "dedup.json"))
        _save_leaderboard(e2, db_path=str(tmp_path / "dedup.json"))
        data = _load_leaderboard(db_path=str(tmp_path / "dedup.json"))
        assert len(data) == 1
        assert data[0]["score"] == 80.0  # updated value


class TestCompareEndpoint:
    """RED: Write failing tests for multi-model comparison."""

    @pytest.mark.asyncio
    async def test_compare_empty_targets_returns_empty(self, client):
        """Compare with empty targets should return empty results."""
        resp = await client.post("/v1/compare", json={
            "targets": [],
            "plan": ["S-01"]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"] == []

    @pytest.mark.asyncio
    async def test_compare_rejects_invalid_plan(self, client):
        """Compare with invalid symptom ID should return 400."""
        resp = await client.post("/v1/compare", json={
            "targets": [{"type": "mock", "api_key": "sk-test", "model": "mock"}],
            "plan": ["INVALID"]
        })
        assert resp.status_code == 400


class TestLeaderboardEndpoint:
    """RED: Tests for the leaderboard API."""

    @pytest.mark.asyncio
    async def test_leaderboard_returns_list(self, client):
        """GET /v1/leaderboard should return a list."""
        resp = await client.get("/v1/leaderboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "leaderboard" in data
        assert isinstance(data["leaderboard"], list)

    @pytest.mark.asyncio
    async def test_leaderboard_has_entry_structure(self, client):
        """Each leaderboard entry should have required fields."""
        resp = await client.get("/v1/leaderboard")
        data = resp.json()
        if data["leaderboard"]:
            entry = data["leaderboard"][0]
            for key in ["model", "score", "ci_95", "total_symptoms", "personality"]:
                assert key in entry
