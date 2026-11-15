"""공용 fixture. DB는 ':memory:'를 쓴다."""

import pytest

from backend.ai import client as ai_client
from backend.ai import tasks as ai_tasks
from backend.core import db, loader


@pytest.fixture(autouse=True)
def ai_defaults(monkeypatch):
    """로컬 .env·환경변수의 AI 설정(모델 이름, 재생 모드)이 테스트 결과를 바꾸지 않게 기본값으로 고정한다.
    키가 없어야 하는 테스트는 각자 키를 지운다."""
    monkeypatch.setattr(ai_client, "MODEL", ai_client.DEFAULT_MODEL)
    monkeypatch.setattr(ai_tasks, "MODEL", ai_client.DEFAULT_MODEL)
    monkeypatch.setattr(ai_client, "REPLAY", False)


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
