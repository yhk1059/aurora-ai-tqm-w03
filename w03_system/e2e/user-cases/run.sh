#!/bin/bash
# 유저 케이스 실행 (brain/3-design/user-case-scenarios.md).
# 사용: w03_system 폴더에서  e2e/user-cases/run.sh            (전체)
#                            e2e/user-cases/run.sh UC-01 UC-06  (고른 것만)
#       UC_AI=1 e2e/user-cases/run.sh UC-11 UC-12 UC-13 UC-14   (AI를 실제로 호출)
# 먼저 (cd frontend && npm run build). 서버는 임시 DB로 따로 띄운다. AI는 기본이 재생 모드라 API를 부르지 않는다.
# 화면 캡처는 data/e2e/uc/ 에 남는다 (git에 올리지 않는 폴더).
cd "$(dirname "$0")/../.." || exit 2
DIR=e2e/user-cases
[ -f frontend/dist/index.html ] || { echo "frontend/dist 없음: npm run build 먼저"; exit 2; }
command -v dev-browser >/dev/null || { echo "dev-browser 없음: npm install -g dev-browser"; exit 2; }

# AI: 기본은 재생 모드(저장된 답 data/ai_replay.json, API 호출 없음). UC_AI=1이면 실제로 호출한다 (UC-11 ~ UC-14에서 5회, 비용 발생).
if [ "$UC_AI" = "1" ]; then REPLAY=0; AI_REAL=true; LIMIT=600; else REPLAY=1; AI_REAL=false; LIMIT=90; fi
[ "$REPLAY" = "0" ] || [ -f data/ai_replay.json ] || echo "주의: data/ai_replay.json 없음. AI 케이스(UC-11 ~ UC-14)는 UC_AI=1로 한 번 실행해야 재생할 답이 생긴다"

PORT=$(.venv/bin/python -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1])")
TMP=$(mktemp -d)
W03_DB_PATH="$TMP/uc.sqlite" W03_AI_REPLAY=$REPLAY .venv/bin/python -m uvicorn backend.api.main:app --port "$PORT" --log-level warning &
SERVER=$!
trap 'kill $SERVER 2>/dev/null' EXIT
for _ in $(seq 50); do curl -s "http://127.0.0.1:$PORT/healthz" >/dev/null && break; sleep 0.1; done
mkdir -p data/e2e/uc

if [ $# -gt 0 ]; then CASES=("$@"); else CASES=(); for f in "$DIR"/UC-*.js; do CASES+=("$(basename "$f" .js)"); done; fi
FAILED=0
for c in "${CASES[@]}"; do
  { echo "const BASE = \"http://127.0.0.1:$PORT\"; const CASE = \"$c\"; const AI_REAL = $AI_REAL;"; cat "$DIR/lib.js" "$DIR/$c.js"; } > "$TMP/$c.js"
  dev-browser --headless --quiet-page -t $LIMIT run "$TMP/$c.js" || FAILED=$((FAILED + 1))
done
echo "--- 케이스 ${#CASES[@]}개 중 실패 $FAILED개"
[ "$FAILED" -eq 0 ]
