"""프로젝트 골격 확인: 패키지 import, 의존성 import, 원본 데이터 위치."""

import importlib
from pathlib import Path

# 이 파일: <root>/w03_system/backend/tests/test_setup.py
PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_backend_packages_import():
    for name in ("backend.core", "backend.ai", "backend.api"):
        importlib.import_module(name)


def test_dependencies_import():
    for name in ("fastapi", "anthropic"):
        importlib.import_module(name)


def test_source_data_exists():
    path = (
        PROJECT_ROOT
        / "01_참가자_배포용/04_원본데이터/01_corevia/quality/qc_claims_cv.csv"
    )
    assert path.is_file(), path
