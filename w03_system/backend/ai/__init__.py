"""AI 단발 호출 4종 (요약·분류·설명·초안). 액션을 실행하지 않는다."""

from backend.ai.client import MODEL, is_available
from backend.ai.tasks import TASKS, AiResult, run_task

__all__ = ["MODEL", "TASKS", "AiResult", "is_available", "run_task"]
