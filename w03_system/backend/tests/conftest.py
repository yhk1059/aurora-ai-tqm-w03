"""공용 fixture. DB는 ':memory:'를 쓴다."""

import pytest

from backend.core import db, loader


@pytest.fixture
def conn():
    """빈 DB."""
    c = db.connect(":memory:")
    yield c
    c.close()


@pytest.fixture
def loaded(conn):
    """B-02-2602-01로 load_incident_scope를 마친 DB."""
    loader.load_incident_scope(conn, "B-02-2602-01")
    return conn
