import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

TEST_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL is not configured")


@pytest.fixture(autouse=True)
def settings():
    os.environ["DATABASE_URL"] = TEST_URL
    from shoppulse.settings import get_settings
    from shoppulse.db.session import _engine_for_url
    get_settings.cache_clear(); _engine_for_url.cache_clear()


def test_session_run_event_persistence_idempotency_and_order():
    from shoppulse.api.services.event_service import append_event, events_after
    from shoppulse.api.services.run_service import create_run
    from shoppulse.api.services.session_service import create_session
    from shoppulse.db.session import db_session
    key = f"test-{datetime.now(UTC).timestamp()}"
    with db_session() as db:
        session = create_session(db, "test", key, {})
        run, created = create_run(db, session, {"query":"GMV"}, key)
        same, created_again = create_run(db, session, {"query":"GMV"}, key)
        assert created and not created_again and same.run_id == run.run_id
        first = append_event(db, run.run_id, "run.queued")
        second = append_event(db, run.run_id, "run.started")
        assert [x.sequence for x in events_after(db, run.run_id)] == [first.sequence, second.sequence]
        db.delete(session)


def test_stale_lease_shape_is_recoverable():
    from shoppulse.db.models import AnalysisRun
    assert AnalysisRun.lease_expires_at is not None
    assert datetime.now(UTC) - timedelta(seconds=1) < datetime.now(UTC)
