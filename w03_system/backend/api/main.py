"""FastAPI 앱. HTTP 요청을 core·ai 함수 호출로 바꾸고 결과를 JSON으로 돌려줄 뿐이다.

기준: brain/3-design/architecture.md (API 표, 모듈 경계의 `api/`).
- 규칙·전이·권한 판단은 하지 않는다. 상태 변경은 actions.execute만 한다(DB를 직접 고치지 않는다).
- 액션 실행 응답에는 항상 실행 후 사건 뷰가 들어간다(화면은 상태 복사본을 갖지 않는다).
- 오류 본문: {"error": {"code", "message"}}. ActionError의 code를 HTTP 상태로 옮긴다.
"""

from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.ai import client as ai_client
from backend.ai import tasks as ai_tasks
from backend.core import actions, db, ontology, scenario, view

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "w03.sqlite"  # w03_system/data/w03.sqlite
DEFAULT_STATIC = Path(__file__).resolve().parents[2] / "frontend" / "dist"  # 화면 빌드 결과 (배포용)

HTTP_STATUS = {"unknown_action": 404, "not_found": 404, "forbidden": 403, "invalid_input": 422, "precondition": 409}


class ApiError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


class ActionBody(BaseModel):
    actor: str
    inputs: dict


class AiBody(BaseModel):
    params: dict = {}


def _error(code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=HTTP_STATUS.get(code, 400), content={"error": {"code": code, "message": message}})


def create_app(db_path: str | None = None, static_dir: str | None = None) -> FastAPI:
    """db_path가 없으면 환경변수 W03_DB_PATH, 그것도 없으면 w03_system/data/w03.sqlite.
    static_dir가 없으면 환경변수 W03_STATIC_DIR, 그것도 없으면 w03_system/frontend/dist."""
    path = str(db_path or os.environ.get("W03_DB_PATH") or DEFAULT_DB)
    static = Path(static_dir or os.environ.get("W03_STATIC_DIR") or DEFAULT_STATIC)
    db.connect(path).close()  # 파일이 없으면 빈 DB(사건 없음)를 만든다

    app = FastAPI(title="W03 품질 이슈와 공급 복구")

    def get_conn():
        conn = db.connect(path)
        try:
            yield conn
        finally:
            conn.close()

    @app.exception_handler(actions.ActionError)
    async def _action_error(request: Request, e: actions.ActionError):
        return _error(e.code, e.message)

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, e: ApiError):
        return _error(e.code, e.message)

    @app.exception_handler(RequestValidationError)
    async def _body_error(request: Request, e: RequestValidationError):
        return _error("invalid_input", f"요청 형식 오류: {e.errors()}")

    @app.get("/healthz")
    def healthz():
        return {"ok": True}  # AXHub 상태 확인용. DB를 부르지 않는다.

    @app.get("/api/incident")
    def get_incident(actor: str | None = None, conn=Depends(get_conn)):
        return view.incident_view(conn, actor)

    @app.post("/api/actions/{action}")
    def post_action(action: str, body: ActionBody, conn=Depends(get_conn)):
        res = actions.execute(conn, action, body.actor, body.inputs)
        return {"result": asdict(res), "view": view.incident_view(conn, body.actor)}

    @app.get("/api/ai/status")
    def ai_status():
        return {"available": ai_client.is_available(), "model": ai_client.MODEL}

    @app.post("/api/ai/{task}")
    def post_ai(task: str, body: AiBody | None = None, conn=Depends(get_conn)):
        if task not in ai_tasks.TASKS:
            raise ApiError("not_found", f"없는 AI task: {task}")
        try:
            res = ai_tasks.run_task(conn, task, (body.params if body else {}))
        except ValueError as e:
            raise ApiError("invalid_input", str(e)) from e
        return asdict(res)

    @app.get("/api/ontology")
    def get_ontology():
        return ontology.to_dict()

    @app.get("/api/scenarios")
    def get_scenarios():
        return scenario.list_scenarios()

    @app.get("/api/reply-examples")
    def get_reply_examples():
        return {"examples": scenario.list_reply_examples()}

    @app.post("/api/scenarios/{name}")
    def post_scenario(name: str, upto: str | None = None, setup_only: bool = False,
                      actor: str | None = None, conn=Depends(get_conn)):
        if name not in [s["name"] for s in scenario.list_scenarios()]:
            raise ApiError("not_found", f"없는 시나리오: {name}")
        try:
            steps = scenario.run_scenario(conn, name, upto=upto, setup_only=setup_only)
        except scenario.ScenarioError as e:
            code = e.cause.code if isinstance(e.cause, actions.ActionError) else "precondition"
            raise ApiError(code, str(e)) from e
        except ValueError as e:
            raise ApiError("invalid_input", str(e)) from e
        return {"steps": steps, "view": view.incident_view(conn, actor)}

    # 화면: 빌드 결과가 있으면 그대로 내보낸다. API 라우트 뒤에 붙여 /api·/healthz가 먼저 잡힌다.
    # 없는 /api/... 경로는 StaticFiles의 404(JSON)로 끝나고 index.html로 돌리지 않는다(화면에 라우터 없음).
    if (static / "index.html").is_file():
        app.mount("/", StaticFiles(directory=static, html=True), name="frontend")
    else:
        @app.get("/", response_class=HTMLResponse)
        def index():
            return ('<!doctype html><html lang="ko"><meta charset="utf-8"><title>Aurora AI-TQM</title>'
                    '<p>화면이 빌드되지 않았습니다. <code>npm --prefix w03_system/frontend run build</code></p></html>')

    return app


app = create_app()
