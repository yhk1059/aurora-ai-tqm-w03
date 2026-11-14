"""Claude 호출 한 곳.

기준: brain/3-design/architecture.md "AI 호출".
- 키는 환경변수 ANTHROPIC_API_KEY, 없으면 w03_system/.env의 같은 이름. 키 값은 어디에도 기록하지 않는다.
- 모델은 환경변수 W03_AI_MODEL(없으면 .env의 같은 이름)로 바꿀 수 있다. 없으면 claude-opus-5-5. 서버를 시작할 때 한 번 읽는다.
- 재생 모드(개발용): 환경변수 W03_AI_REPLAY=1이면 API를 부르지 않고, 마지막으로 받은 실제 답(data/ai_replay.json, task별 1개)을 돌려준다. 서버를 시작할 때 한 번 읽는다.
- 출력 형식은 구조화 출력(output_config.format, JSON 스키마)으로 고정한다.
- stop_reason이 end_turn이 아니면 결과로 쓰지 않는다.
- API 예외는 잡아서 'api_error'로 돌려준다(서버가 죽지 않게).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import anthropic

DEFAULT_MODEL = "claude-opus-5-5"
MODEL_NAME = "W03_AI_MODEL"
MAX_TOKENS = 16000
EFFORT = "medium"  # Opus 5.5 기본값과 같지만 명시한다
KEY_NAME = "ANTHROPIC_API_KEY"
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"  # w03_system/.env

OK_STOP = "end_turn"


def _read_env(env_name: str) -> str | None:
    """환경변수를 먼저 보고, 없으면 w03_system/.env 파일의 같은 이름을 읽는다."""
    env = os.environ.get(env_name, "").strip()
    if env:
        return env
    try:
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        name, sep, value = line.strip().partition("=")
        if sep and name.strip() == env_name:
            value = value.strip().strip('"').strip("'")
            return value or None
    return None


def _read_key() -> str | None:
    return _read_env(KEY_NAME)


MODEL = _read_env(MODEL_NAME) or DEFAULT_MODEL


REPLAY_NAME = "W03_AI_REPLAY"
REPLAY_PATH = Path(__file__).resolve().parents[2] / "data" / "ai_replay.json"  # git에 올리지 않는다 (data/)
REPLAY = _read_env(REPLAY_NAME) == "1"


def load_replay(task: str) -> dict | None:
    """재생 모드에서 돌려줄 답. 저장된 것이 없으면 None."""
    try:
        return json.loads(REPLAY_PATH.read_text(encoding="utf-8")).get(task)
    except (OSError, json.JSONDecodeError):
        return None


def save_replay(task: str, data: dict) -> None:
    """실제 호출에서 확인을 통과한 답을 task별로 하나 남긴다 (재생 모드가 읽는다)."""
    try:
        saved = json.loads(REPLAY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        saved = {}
    saved[task] = data
    REPLAY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPLAY_PATH.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")


def is_available() -> bool:
    """ANTHROPIC_API_KEY가 있으면 True. 환경변수를 먼저 보고, 없으면 w03_system/.env 파일의 같은 이름을 읽는다."""
    return _read_key() is not None


def make_client():
    return anthropic.Anthropic(api_key=_read_key())


@dataclass
class CallResult:
    data: dict | None        # 파싱한 JSON (정상 종료일 때만)
    received: dict           # 받은 내용 그대로 (ai_log에 남김)
    error: str | None        # None | 'refusal' | 'max_tokens' | 'api_error' | 'invalid_output'
    message: str | None


def call(client, *, system: str, user: str, schema: dict) -> CallResult:
    """메시지 한 번 호출. 도구·루프 없음."""
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": schema}},
        )
    except anthropic.APIStatusError as e:
        return CallResult(None, {"exception": type(e).__name__, "status_code": e.status_code, "detail": str(e)},
                          "api_error", f"API 오류 (HTTP {e.status_code})")
    except anthropic.APIConnectionError as e:
        return CallResult(None, {"exception": type(e).__name__, "detail": str(e)},
                          "api_error", "API에 연결하지 못했다")
    except Exception as e:  # 서버가 죽지 않게: SDK 밖의 예외도 오류 결과로 바꾼다
        return CallResult(None, {"exception": type(e).__name__, "detail": str(e)},
                          "api_error", f"AI 호출 중 예외: {type(e).__name__}")

    stop = getattr(resp, "stop_reason", None)
    text = "".join(getattr(b, "text", "") or "" for b in (getattr(resp, "content", None) or [])
                   if getattr(b, "type", None) == "text")
    received = {"stop_reason": stop, "text": text, "request_id": getattr(resp, "_request_id", None)}
    details = getattr(resp, "stop_details", None)
    if details is not None:
        received["stop_details"] = {"category": getattr(details, "category", None),
                                    "explanation": getattr(details, "explanation", None)}

    if stop == "refusal":
        return CallResult(None, received, "refusal", "AI가 응답을 거절했다. 결과로 쓰지 않는다")
    if stop == "max_tokens":
        return CallResult(None, received, "max_tokens", "응답이 길이 한도에서 잘렸다. 결과로 쓰지 않는다")
    if stop != OK_STOP:
        return CallResult(None, received, "invalid_output", f"정상 종료가 아니다 (stop_reason={stop})")

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return CallResult(None, received, "invalid_output", "응답이 JSON이 아니다")
    if not isinstance(data, dict):
        return CallResult(None, received, "invalid_output", "응답이 JSON 객체가 아니다")
    return CallResult(data, received, None, None)
