"""브라우저 테스트 준비 (brain/3-design/browser-test-scenarios.md).

실행: w03_system/.venv/bin/python -m pytest e2e   (w03_system 폴더에서, 먼저 frontend에서 npm run build)
- 서버는 테스트 전용 DB(임시 폴더)로 따로 띄운다. data/w03.sqlite는 건드리지 않는다.
- AI 테스트(TC-07)는 E2E_AI=1일 때만 실제로 호출한다.
- 화면 캡처는 data/e2e/ 에 남긴다 (data/는 git에 올리지 않는 폴더).
"""
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]  # w03_system
SHOTS = ROOT / "data" / "e2e"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def base_url():
    assert (ROOT / "frontend" / "dist" / "index.html").is_file(), "frontend/dist 없음: npm run build 먼저"
    port = _free_port()
    env = {**os.environ, "W03_DB_PATH": str(Path(tempfile.mkdtemp()) / "e2e.sqlite")}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.api.main:app", "--port", str(port), "--log-level", "warning"],
        cwd=ROOT, env=env,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f"{url}/healthz", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("서버가 뜨지 않음")
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser, base_url, request):
    """1440×900 화면. 테스트가 끝나면 콘솔 오류·API 오류가 없었는지 확인하고 화면을 캡처한다."""
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, base_url=base_url)
    pg = ctx.new_page()
    pg.set_default_timeout(8000)
    problems: list[str] = []
    pg.expected_api_errors = 0  # 일부러 실패시키는 단계가 있는 테스트가 올린다
    pg.on("console", lambda m: problems.append(f"console: {m.text}") if m.type == "error" else None)
    pg.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
    api_errors: list[str] = []
    pg.on("response", lambda r: api_errors.append(f"{r.status} {r.request.method} {r.url}")
          if "/api/" in r.url and r.status >= 400 else None)
    pg.goto("/")
    yield pg
    SHOTS.mkdir(parents=True, exist_ok=True)
    pg.screenshot(path=str(SHOTS / f"{request.node.name}.png"), full_page=True)
    ctx.close()
    assert len(api_errors) == pg.expected_api_errors, f"API 오류: {api_errors}"
    # 실패한 API 응답은 브라우저가 콘솔 오류로도 남긴다. 그것은 위에서 셌으므로 뺀다
    others = [p for p in problems if "Failed to load resource" not in p]
    assert not others, f"화면 오류: {others}"
