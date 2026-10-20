from datetime import datetime, timedelta, timezone

from app import main


def test_seconds_elapsed():
    old = (datetime.now(timezone.utc) - timedelta(seconds=400)).isoformat()
    recent = datetime.now(timezone.utc).isoformat()
    assert main._seconds_elapsed(old, 300) is True
    assert main._seconds_elapsed(recent, 300) is False
    # Unparseable timestamps are treated as "elapsed" so a request can't get stuck.
    assert main._seconds_elapsed("garbage", 300) is True


def _searching_request(tmp_path, monkeypatch):
    """A pending request whose pipeline always reports 'searching, nothing in flight'."""
    from app import config, db, lidarr

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "giveup.db"))
    monkeypatch.setattr(config, "SEARCH_ATTEMPT_INTERVAL_SECONDS", 0)
    db.init()
    row = db.upsert_request(
        type="album", foreign_id="mbid-gu", title="Dawn", artist="RY X",
        image_url=None, lidarr_artist_id=1, lidarr_album_id=2, status="pending",
    )

    async def fake_pipeline(*_a, **_k):
        return lidarr._build_pipeline("searching", 0, 0, 10, "Searching…")

    monkeypatch.setattr(lidarr, "request_pipeline", fake_pipeline)
    return row["id"]


def test_track_search_attempts_gives_up(tmp_path, monkeypatch):
    import asyncio
    from app import config, db

    rid = _searching_request(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "SEARCH_GIVE_UP_ATTEMPTS", 3)
    for _ in range(3):
        asyncio.run(main._track_search_attempts(db.get_request(rid)))
    assert db.get_request(rid)["status"] == "failed"


def test_track_search_attempts_zero_never_gives_up(tmp_path, monkeypatch):
    import asyncio
    from app import config, db

    rid = _searching_request(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "SEARCH_GIVE_UP_ATTEMPTS", 0)
    for _ in range(50):
        asyncio.run(main._track_search_attempts(db.get_request(rid)))
    row = db.get_request(rid)
    assert row["status"] == "pending"
    assert row["search_attempts"] == 50
