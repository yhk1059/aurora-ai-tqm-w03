"""시연 영상 자동 녹화 (brain/3-design/shooting-script.md v5의 A1 ~ D3, 장면 1 ~ 6).

실행 (w03_system 폴더에서, 먼저 frontend에서 npm run build):
    .venv/bin/python scripts/record_demo.py

- 서버를 임시 DB로 따로 띄운다. data/w03.sqlite는 건드리지 않는다. AI는 실제로 부른다(W03_AI_REPLAY=0).
- 실제 앱을 브라우저(1920×1080)로 조작하면서 화면을 프레임으로 받아 ffmpeg로 MP4를 만든다.
- AI 응답 대기와 대본의 "빨리 감기" 구간은 시간을 줄이고, 그 동안 화면에 `빨리 감기` 표시를 띄운다.
- .env에 ELEVENLABS_API_KEY가 있으면 해설을 음성으로 합성해(data/video/audio/, 바뀐 토막만 다시 만든다) 그 길이에 맞춰 찍고 영상에 얹는다.
- 결과는 data/video/ 에 둔다 (data/는 git에 올리지 않는 폴더): demo.mp4, demo.srt(해설 자막), cues.json.
"""
import base64
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import Locator, Page, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]  # w03_system
OUT = ROOT / "data" / "video"
FRAMES = OUT / "frames"
AUDIO = OUT / "audio"
VOICE_ID = "cjVigY5qzO86Huf0OWal"   # ElevenLabs 기본 음성 Eric (사용자 선택 2026-11-15)
VOICE_MODEL = "eleven_multilingual_v2"
VOICE_SPEED = 1.1
W, H, ZOOM = 1920, 1080, 1.15
FPS = 30
READ_CPS = 5.5      # 해설 읽는 속도 (공백 뺀 글자 / 초)
FF_TARGET = 2.0     # 빨리 감는 구간 하나가 영상에서 차지할 길이 (초)
AI_TIMEOUT = 90_000

OWNER, COMMITTEE, SCM = "품질 담당자", "품질위원회", "SCM"
B1, B3 = "B-02-2602-01", "B-02-2602-03"

# 해설. caption = 화면 자막(대본의 말할 문장 그대로), spoken = 음성 합성에 넣는 읽기용 문장(숫자·영문을 소리 나는 대로). spoken이 없으면 caption을 읽는다
NARRATION: dict[str, dict[str, str]] = {
    "S1": {
        "caption": 'W03, 품질 이슈와 공급 복구입니다. 사용자는 화장품 회사 Corevia의 품질팀 사건 담당자입니다. 불량률이 회수 기준을 넘고 91일이 지났는데 위원회에 올린 기록이 없는 사건 하나를, 처음부터 끝까지 따라갑니다. 시스템은 두 결정을 돕습니다. 품질위원회의 회수 결정과 SCM의 재공급 계획 승인입니다. 판정과 상태 변경은 실제 작동이고, 위원회와 SCM의 결정, 부서 회신은 모의 입력입니다.',
        "spoken": '더블유 공삼, 품질 이슈와 공급 복구입니다. 사용자는 화장품 회사 코레비아의 품질팀 사건 담당자입니다. 불량률이 회수 기준을 넘고 구십일 일이 지났는데 위원회에 올린 기록이 없는 사건 하나를, 처음부터 끝까지 따라갑니다. 시스템은 두 결정을 돕습니다. 품질위원회의 회수 결정과 에스씨엠의 재공급 계획 승인입니다. 판정과 상태 변경은 실제 작동이고, 위원회와 에스씨엠의 결정, 부서 회신은 모의 입력입니다.',
    },
    "A1": {
        "caption": '목록 위쪽이 회수 기준 10%를 넘은 배치입니다. 하나를 골라 사건을 엽니다. 시스템이 같은 원료 로트로 만든 배치 네 개를 묶었습니다. 두 개는 불량률 11.9%, 11.6%로 기준을 넘었고 91일, 51일째 미상신입니다. 합격 배치 두 개는 90일 넘게 클레임이 없어 관찰에서 해제됐습니다. 보류 상태로 출하된 배치와, 출하 기록에 없는 고객 C-105에는 확인 작업이 자동으로 생겼습니다.',
        "spoken": '목록 위쪽이 회수 기준 십 퍼센트를 넘은 배치입니다. 하나를 골라 사건을 엽니다. 시스템이 같은 원료 로트로 만든 배치 네 개를 묶었습니다. 두 개는 불량률 십일 점 구 퍼센트, 십일 점 육 퍼센트로 기준을 넘었고 구십일 일, 오십일 일째 미상신입니다. 합격 배치 두 개는 구십 일 넘게 클레임이 없어 관찰에서 해제됐습니다. 보류 상태로 출하된 배치와, 출하 기록에 없는 고객 씨 백오에는 확인 작업이 자동으로 생겼습니다.',
    },
    "A2": {
        "caption": 'AI가 안건 요약 초안을 씁니다. 숫자 표는 AI 글이 아니라 시스템 계산값이고, 대안은 세 가지입니다. 담당자가 확인하고 상신합니다.',
        "spoken": '에이아이가 안건 요약 초안을 씁니다. 숫자 표는 에이아이 글이 아니라 시스템 계산값이고, 대안은 세 가지입니다. 담당자가 확인하고 상신합니다.',
    },
    "A3": {
        "caption": '품질위원회의 승인은 모의 입력입니다. 배치 두 개가 회수진행이 되고, 부서별 작업 다섯 개와 재공급 계획 초안이 자동으로 생겼습니다.',
    },
    "A4": {
        "caption": '여유 능력이 월 약 1만 5천 개라 마지막 고객은 2028년 3월에 끝납니다. C-105는 출하처가 확인되지 않아 보류입니다.',
        "spoken": '여유 능력이 월 약 만 오천 개라 마지막 고객은 이천이십팔 년 삼 월에 끝납니다. 씨 백오는 출하처가 확인되지 않아 보류입니다.',
    },
    "A5": {
        "caption": 'SCM의 승인도 모의 입력입니다. 보류 배치가 왜 출하됐는지 아직 답이 없어서, 근거를 적어야 승인됩니다. 계획 v1이 확정됐고, 여기까지가 기록에 남았습니다.',
        "spoken": '에스씨엠의 승인도 모의 입력입니다. 보류 배치가 왜 출하됐는지 아직 답이 없어서, 근거를 적어야 승인됩니다. 계획 버전 일이 확정됐고, 여기까지가 기록에 남았습니다.',
    },
    "B1": {
        "caption": '새 조건 첫 번째는 미확정 언론 보도입니다. 판정은 바뀌지 않고, 재검토했다는 기록만 남습니다.',
    },
    "B2": {
        "caption": '두 번째는 해제된 합격 배치에 뒤늦게 들어온 클레임입니다. 접수 단계에서는 관찰로 되돌리기만 합니다. 확정되면 다시 계산합니다. 0.5%로 기준에 못 미쳐 결론은 유지됩니다.',
        "spoken": '두 번째는 해제된 합격 배치에 뒤늦게 들어온 클레임입니다. 접수 단계에서는 관찰로 되돌리기만 합니다. 확정되면 다시 계산합니다. 영 점 오 퍼센트로 기준에 못 미쳐 결론은 유지됩니다.',
    },
    "B3": {
        "caption": '영업의 안내 대상 회신은 빨리 감습니다.',
    },
    "B4": {
        "caption": '세 번째는 영업 임원의 요청입니다. 수주가 줄고 있는 C-101을 먼저 공급해 달라고 합니다. 계획이 다시 계산됐습니다. C-101은 11개월 빨라지고, C-103과 C-102는 4개월씩 늦어집니다.',
        "spoken": '세 번째는 영업 임원의 요청입니다. 수주가 줄고 있는 씨 백일을 먼저 공급해 달라고 합니다. 계획이 다시 계산됐습니다. 씨 백일은 열한 개월 빨라지고, 씨 백삼과 씨 백이는 네 개월씩 늦어집니다.',
    },
    "B5": {
        "caption": '생산·물류가 출하 경위를, 생산이 능력 확보 방안을 회신했습니다. 계획의 경고 두 개가 풀립니다.',
    },
    "B6": {
        "caption": 'SCM 결정 창에 두 회신이 판단 근거로 들어와 있습니다. 다시 승인하면 v2가 확정되고 v1은 대체됨이 됩니다.',
        "spoken": '에스씨엠 결정 창에 두 회신이 판단 근거로 들어와 있습니다. 다시 승인하면 버전 이가 확정되고 버전 일은 대체됨이 됩니다.',
    },
    "C1": {
        "caption": 'C-105는 클레임을 14건 냈는데 출하 기록에는 없습니다. 그래서 점선이고, 회수와 재공급에서 보류돼 있었습니다.',
        "spoken": '씨 백오는 클레임을 열네 건 냈는데 출하 기록에는 없습니다. 그래서 점선이고, 회수와 재공급에서 보류돼 있었습니다.',
    },
    "C2": {
        "caption": '물류가 기록을 확인할 수 없고 7일이 더 필요하다고 회신합니다. AI는 이 문장을 분류만 하고, 반영은 담당자가 합니다. 작업은 열린 채 기한만 7월 17일로 연장됩니다.',
        "spoken": '물류가 기록을 확인할 수 없고 칠 일이 더 필요하다고 회신합니다. 에이아이는 이 문장을 분류만 하고, 반영은 담당자가 합니다. 작업은 열린 채 기한만 칠 월 십칠 일로 연장됩니다.',
    },
    "C3": {
        "caption": '일주일 뒤 출하가 확인됩니다. 수량 기록이 없어, 클레임 수량 합 11,765개를 최소 회수량으로 쓰고 하한이라고 표시합니다. 계획 v3 초안에 C-105가 여섯 번째로 들어갑니다.',
        "spoken": '일주일 뒤 출하가 확인됩니다. 수량 기록이 없어, 클레임 수량 합 만 천칠백육십오 개를 최소 회수량으로 쓰고 하한이라고 표시합니다. 계획 버전 삼 초안에 씨 백오가 여섯 번째로 들어갑니다.',
    },
    "C4": {
        "caption": 'SCM이 승인하면 v3가 확정됩니다.',
        "spoken": '에스씨엠이 승인하면 버전 삼이 확정됩니다.',
    },
    "D1": {
        "caption": '이번에는 영업 임원이 C-104도 먼저 공급해 달라고 요청합니다. 계획이 다시 계산됩니다. C-104는 10개월 빨라지지만 C-103은 4개월, C-102는 3개월 더 늦어집니다.',
        "spoken": '이번에는 영업 임원이 씨 백사도 먼저 공급해 달라고 요청합니다. 계획이 다시 계산됩니다. 씨 백사는 열 개월 빨라지지만 씨 백삼은 네 개월, 씨 백이는 세 개월 더 늦어집니다.',
    },
    "D2": {
        "caption": 'SCM이 거절합니다. 거절은 근거를 적어야 실행됩니다. 초안 v4는 기각되고 확정된 v3가 그대로 유지됩니다. 영업 임원에게 결과를 알리는 작업이 자동으로 생겼습니다.',
        "spoken": '에스씨엠이 거절합니다. 거절은 근거를 적어야 실행됩니다. 초안 버전 사는 기각되고 확정된 버전 삼이 그대로 유지됩니다. 영업 임원에게 결과를 알리는 작업이 자동으로 생겼습니다.',
    },
    "D3": {
        "caption": '통보가 확인되면 열린 작업이 없어집니다. 사건을 연 날부터 여기까지 서른다섯 건이 이전 값과 이후 값으로 남았습니다.',
    },
    "S5": {
        "caption": '필수 확장은 원료 로트 기반 영향 추적입니다. 장면 2에서 배치 네 개를 묶고 합격 배치를 회수하지 않고 관찰로 둔 것, 장면 3에서 늦은 클레임에 관찰로 되돌린 것, 그리고 출하 경위가 확인되기 전에는 승인에 근거를 요구한 것이 여기에 속합니다. 다른 부서 영향은 세 곳입니다. 장면 3에서 영업 임원의 요청이 재공급 순서를 바꾸고 SCM의 재승인을 요구했고, 장면 4에서 물류의 회신이 계획에 C-105를 넣었으며, 두 번째 요청은 다른 고객이 더 늦어져 SCM이 거절했습니다.',
        "spoken": '필수 확장은 원료 로트 기반 영향 추적입니다. 장면 이에서 배치 네 개를 묶고 합격 배치를 회수하지 않고 관찰로 둔 것, 장면 삼에서 늦은 클레임에 관찰로 되돌린 것, 그리고 출하 경위가 확인되기 전에는 승인에 근거를 요구한 것이 여기에 속합니다. 다른 부서 영향은 세 곳입니다. 장면 삼에서 영업 임원의 요청이 재공급 순서를 바꾸고 에스씨엠의 재승인을 요구했고, 장면 사에서 물류의 회신이 계획에 씨 백오를 넣었으며, 두 번째 요청은 다른 고객이 더 늦어져 에스씨엠이 거절했습니다.',
    },
    "S6": {
        "caption": '추가 확장은 복구 기간 신호입니다. 완료 예상이 12개월을 넘어 장면 2에서 생산에 능력 확보 검토가 자동으로 요청됐고, 장면 3에서 그 회신이 SCM의 판단 근거로 쓰였습니다. 계획 숫자는 바꾸지 않습니다.',
        "spoken": '추가 확장은 복구 기간 신호입니다. 완료 예상이 십이 개월을 넘어 장면 이에서 생산에 능력 확보 검토가 자동으로 요청됐고, 장면 삼에서 그 회신이 에스씨엠의 판단 근거로 쓰였습니다. 계획 숫자는 바꾸지 않습니다.',
    },
}

CURSOR_JS = """
(() => {
  const init = () => {
    document.documentElement.style.zoom = '%s';
    const c = document.createElement('div');
    c.id = '__cursor';
    c.style.cssText = 'position:fixed;left:0;top:0;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%%;' +
      'background:rgba(79,70,229,.35);border:2px solid #4338ca;z-index:2147483647;pointer-events:none;transition:transform .12s';
    document.body.appendChild(c);
    const z = %s;
    addEventListener('mousemove', e => { c.style.left = e.clientX / z + 'px'; c.style.top = e.clientY / z + 'px'; }, true);
    addEventListener('mousedown', () => { c.style.transform = 'scale(.6)'; }, true);
    addEventListener('mouseup', () => { c.style.transform = 'scale(1)'; }, true);
  };
  document.body ? init() : addEventListener('DOMContentLoaded', init);
})();
""" % (ZOOM, ZOOM)


def exact(text: str) -> re.Pattern:
    return re.compile(rf"^\s*{re.escape(text)}\s*$")


class Recorder:
    """화면 프레임을 받아 두고, 해설 구간과 빨리 감기 구간의 시각을 적는다."""

    def __init__(self, page: Page):
        self.page = page
        self.frames: list[tuple[float, Path]] = []
        self.cues: list[dict] = []       # {id, scene, text, start, end}
        self.ff: list[tuple[float, float]] = []
        self.scenes: list[dict] = []     # {n, title, start}
        self.cdp = page.context.new_cdp_session(page)
        self.cdp.on("Page.screencastFrame", self._on_frame)
        self.t0 = 0.0

    def _on_frame(self, ev: dict) -> None:
        path = FRAMES / f"{len(self.frames):06d}.jpg"
        path.write_bytes(base64.b64decode(ev["data"]))
        self.frames.append((ev["metadata"]["timestamp"], path))
        self.cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})

    def start(self) -> None:
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 95, "everyNthFrame": 1})
        self.page.wait_for_timeout(300)
        self.t0 = time.time()

    def stop(self) -> float:
        self.page.wait_for_timeout(500)
        end = time.time()
        self.cdp.send("Page.stopScreencast")
        return end

    def now(self) -> float:
        return time.time()

    def scene(self, n: int, title: str) -> None:
        self.scenes.append({"n": n, "title": title, "start": self.now()})
        print(f"[장면 {n}] {title}", flush=True)

    @contextmanager
    def step(self, sid: str, tail: float = 0.3):
        """해설 한 토막. 조작이 해설보다 빨리 끝나면 해설이 끝날 때까지 화면을 붙잡아 둔다.
        길이는 합성한 음성이 있으면 그 길이, 없으면 글자 수로 어림한다."""
        text = NARRATION[sid]["caption"]
        start = self.now()
        audio = AUDIO / f"{sid}.mp3"
        need = audio_seconds(audio) + 0.2 if audio.is_file() else len(re.sub(r"\s", "", text)) / READ_CPS
        cue = {"id": sid, "scene": self.scenes[-1]["n"], "text": text, "start": start, "need": need}
        self.cues.append(cue)
        print(f"  {sid} (해설 {need:.1f}초)", flush=True)
        yield
        spent = self._video_seconds(start, self.now())
        if spent < need:
            self.page.wait_for_timeout(int((need - spent) * 1000))
        cue["end"] = self.now()
        self.page.wait_for_timeout(int(tail * 1000))

    def _video_seconds(self, a: float, b: float) -> float:
        """실제 시각 a ~ b가 완성 영상에서 차지하는 길이 (빨리 감기 반영)."""
        return self.map(b) - self.map(a)

    def map(self, t: float) -> float:
        out = t - self.t0
        for a, b in self.ff:
            if t <= a:
                continue
            real = min(t, b) - a
            full = b - a
            out -= real - real * min(1.0, FF_TARGET / full)
        return out

    @contextmanager
    def fast(self):
        """빨리 감는 구간. 화면에 표시를 띄우고, 영상에서는 FF_TARGET초로 줄인다."""
        self.page.evaluate("""() => {
          const d = document.createElement('div'); d.id = '__ff';
          d.textContent = '▶▶ 빨리 감기';
          d.style.cssText = 'position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:2147483646;' +
            'background:#111827;color:#fff;font-size:15px;font-weight:600;padding:6px 14px;border-radius:999px;pointer-events:none';
          document.body.appendChild(d);
        }""")
        self.page.wait_for_timeout(150)
        a = self.now()
        try:
            yield
        finally:
            b = self.now()
            if b - a > FF_TARGET:
                self.ff.append((a, b))
            self.page.wait_for_timeout(150)
            self.page.evaluate("() => document.getElementById('__ff')?.remove()")


# --- 음성 합성 (ElevenLabs) -----------------------------------------------------

def audio_seconds(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def synthesize() -> bool:
    """해설 토막마다 음성 파일을 만든다. 문장·음성·속도가 같으면 다시 만들지 않는다.
    .env에 ELEVENLABS_API_KEY가 없으면 아무것도 하지 않는다 (자막만 있는 영상이 된다)."""
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    env_file = ROOT / ".env"
    if not key and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("ELEVENLABS_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("\"'")
    if not key:
        print("ELEVENLABS_API_KEY 없음: 음성 없이 자막만 만든다")
        return False
    AUDIO.mkdir(parents=True, exist_ok=True)
    meta_file = AUDIO / "meta.json"
    meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.is_file() else {}
    for sid, n in NARRATION.items():
        spoken = n.get("spoken", n["caption"])
        sig = hashlib.sha256(f"{VOICE_ID}|{VOICE_MODEL}|{VOICE_SPEED}|{spoken}".encode()).hexdigest()
        path = AUDIO / f"{sid}.mp3"
        if meta.get(sid) == sig and path.is_file():
            continue
        body = json.dumps({"text": spoken, "model_id": VOICE_MODEL,
                           "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "speed": VOICE_SPEED}}).encode()
        req = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}?output_format=mp3_44100_128",
            data=body, headers={"xi-api-key": key, "Content-Type": "application/json"})
        try:
            data = urllib.request.urlopen(req, timeout=180).read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"음성 합성 실패 ({sid}): {e.code} {e.read().decode()[:300]}") from None
        path.write_bytes(data)
        meta[sid] = sig
        meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        print(f"  음성 {sid}: {len(spoken)}자, {audio_seconds(path):.1f}초", flush=True)
    return True


# --- 조작 도우미 ----------------------------------------------------------------

def point(page: Page, loc: Locator, hold: float = 0.6, mark: bool = True) -> None:
    """요소로 커서를 옮기고 잠깐 테두리를 둘러 짚는다."""
    loc = loc.first
    loc.scroll_into_view_if_needed()
    page.wait_for_timeout(200)
    box = loc.bounding_box()
    if not box:
        return
    x = box["x"] + min(box["width"] / 2, 260)
    y = box["y"] + min(box["height"] / 2, 60)
    page.mouse.move(x, y, steps=22)
    if mark:
        loc.evaluate("""e => { const o = e.style.outline, f = e.style.outlineOffset;
            e.style.outline = '3px solid #f59e0b'; e.style.outlineOffset = '3px';
            setTimeout(() => { e.style.outline = o; e.style.outlineOffset = f; }, 1400); }""")
    page.wait_for_timeout(int(hold * 1000))


def click(page: Page, loc: Locator, after: float = 0.35) -> None:
    loc = loc.first
    loc.scroll_into_view_if_needed()
    page.wait_for_timeout(150)
    box = loc.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=16)
    page.wait_for_timeout(150)
    loc.click()
    page.wait_for_timeout(int(after * 1000))


def run(page: Page, loc: Locator, after: float = 0.6) -> None:
    """실행 버튼을 누르고 액션 응답을 기다린다."""
    loc = loc.first
    loc.scroll_into_view_if_needed()
    box = loc.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=16)
    page.wait_for_timeout(200)
    with page.expect_response(lambda r: "/api/actions/" in r.url) as info:
        loc.click()
    assert info.value.ok, f"액션 실패: {info.value.status} {info.value.url} {info.value.text()[:200]}"
    page.wait_for_timeout(int(after * 1000))


def type_into(page: Page, loc: Locator, text: str) -> None:
    click(page, loc, after=0.2)
    loc.first.press_sequentially(text, delay=28)
    page.wait_for_timeout(300)


def set_date(page: Page, date: str) -> None:
    box = page.locator("header").get_by_label("적용일", exact=True)
    point(page, box, hold=0.3, mark=False)
    box.fill(date)
    page.wait_for_timeout(300)


def set_role(page: Page, name: str) -> None:
    sel = page.locator("header select")
    point(page, sel, hold=0.3, mark=False)
    with page.expect_response(lambda r: "/api/incident" in r.url):
        sel.select_option(label=name)
    page.wait_for_timeout(400)


def tab(page: Page, label: str) -> None:
    click(page, page.locator("nav").get_by_role("button", name=re.compile(rf"^{re.escape(label)}( |$)")), after=0.5)
    page.mouse.wheel(0, -5000)


def card(page: Page, title) -> Locator:
    return page.locator("main section").filter(has=page.locator("h2", has_text=title))


def action_bar(page: Page) -> Locator:
    return page.locator("main section").filter(
        has=page.locator("span", has_text=re.compile(r"^\s*(판정|새 입력)\s*$"))).first


def task(page: Page, type_: str, customer: str | None = None) -> Locator:
    li = page.locator("main li[data-task-state]").filter(has_text=type_)
    return li.filter(has_text=customer) if customer else li


def reply_example(page: Page, li: Locator, example: str) -> None:
    click(page, li.get_by_role("button", name="회신 입력"))
    click(page, li.get_by_role("button", name=example, exact=True), after=0.8)
    run(page, li.get_by_role("button", name="회신 반영 실행", exact=True))


def open_plan_decision(page: Page) -> Locator:
    click(page, card(page, exact("결정")).get_by_role("button", name="결정 입력"))
    dlg = page.get_by_role("dialog")
    expect(dlg).to_be_visible()
    return dlg


def choose(page: Page, dlg: Locator, result: str) -> None:
    click(page, dlg.locator("button[aria-pressed]").filter(has=page.locator("span", has_text=exact(result))))


def state(page: Page) -> dict:
    v = page.request.get("/api/incident", params={"actor": "quality_owner"}).json()
    return {
        "status": v["incident"]["status"],
        "plans": {p["id"]: p["state"] for p in v["plans"]},
        "open": sum(1 for t in v["tasks"] if t["state"] != "완료"),
        "tasks": len(v["tasks"]),
        "log": len(v["log"]["actions"]),
    }


def check(page: Page, sid: str, **want) -> None:
    got = state(page)
    for k, v in want.items():
        assert got[k] == v, f"{sid}: {k} = {got[k]!r}, 기대 {v!r}"


# --- 대본 ---------------------------------------------------------------------

def play(page: Page, rec: Recorder) -> None:
    main = page.locator("main")

    # 장면 1. 소개
    rec.scene(1, "소개")
    with rec.step("S1"):
        page.wait_for_timeout(1500)
        point(page, main.locator("article", has_text=B1), hold=2.0)
        point(page, page.locator("header select"), hold=2.0)

    # 장면 2. 정상
    rec.scene(2, "정상")
    with rec.step("A1"):
        set_date(page, "2026-07-01")
        point(page, main.locator("article", has_text=B1), hold=1.5)
        run(page, main.locator("article", has_text=B1).get_by_role("button", name="이 배치로 사건 열기"), after=2.0)
        point(page, page.locator(f'main section[data-batch="{B1}"]'), hold=3.5)
        point(page, page.locator('main section[data-batch="B-02-2603-01"]'), hold=2.5)
        point(page, page.locator('main section[data-batch="B-02-2602-02"]'), hold=2.0)
        point(page, page.locator(f'main section[data-batch="{B3}"]'), hold=2.0)
        point(page, card(page, re.compile(r"^작업 열림")), hold=3.0)
        point(page, page.locator("main [data-open-network]"), hold=2.0)
        page.mouse.wheel(0, -5000)
    check(page, "A1", status="열림", open=2, tasks=2, log=7)

    with rec.step("A2"):
        bar = action_bar(page)
        click(page, bar.get_by_role("button", name="안건 상신", exact=True))
        click(page, bar.get_by_role("button", name="AI로 안건 요약"))
        use = bar.get_by_role("button", name="이 내용 사용")
        with rec.fast():
            expect(use).to_be_visible(timeout=AI_TIMEOUT)
        draft = bar.locator("div.border-dashed").filter(has_text="AI 초안").first
        point(page, draft.get_by_text("요지", exact=True), hold=0.9)
        point(page, draft.get_by_text(re.compile("배치 수치 · 시스템 계산값")), hold=1.5)
        point(page, draft.get_by_text(re.compile(r"^대안 \d")), hold=1.2)
        point(page, draft.get_by_text(re.compile(r"^확인 안 된 것")), hold=0.9)
        click(page, use, after=0.9)
        dlg = page.get_by_role("dialog")
        expect(dlg.get_by_role("heading", name="안건 요약 확인·수정")).to_be_visible()
        run(page, dlg.get_by_role("button", name="안건 상신 실행", exact=True), after=0.9)
        page.mouse.wheel(0, -5000)
    check(page, "A2", log=8)

    with rec.step("A3"):
        set_role(page, COMMITTEE)
        set_date(page, "2026-07-02")
        click(page, action_bar(page).get_by_role("button", name="위원회 결정 입력", exact=True))
        dlg = page.get_by_role("dialog")
        choose(page, dlg, "승인")
        run(page, dlg.get_by_role("button", name=re.compile("결정 실행$")), after=0.9)
        point(page, page.locator(f'main section[data-batch="{B1}"]'), hold=0.9)
        point(page, card(page, re.compile(r"^작업 열림")).locator("h2"), hold=1.2)
        last = card(page, exact("방금 바뀐 것"))
        more = last.locator('button[aria-expanded="false"]')
        if more.count():
            click(page, more, after=0.9)
    check(page, "A3", status="회수진행", open=7, tasks=7, log=13)

    with rec.step("A4"):
        tab(page, "재공급 계획")
        point(page, card(page, "고객별 재공급 순서"), hold=3.5)
        point(page, main.get_by_text("계획에서 보류된 고객").locator("xpath=ancestor::section[1]"), hold=2.5)
        page.mouse.wheel(0, -5000)

    with rec.step("A5"):
        set_role(page, SCM)
        set_date(page, "2026-07-03")
        point(page, page.locator("main [data-hold-shipment]"), hold=0.9)
        dlg = open_plan_decision(page)
        choose(page, dlg, "승인")
        point(page, dlg.get_by_role("button", name=re.compile("결정 실행$")), hold=1.1)
        click(page, dlg.get_by_role("button", name="승인 (출고 조건 충족)", exact=True), after=0.8)
        run(page, dlg.get_by_role("button", name=re.compile("결정 실행$")), after=0.9)
        point(page, card(page, exact("결정")), hold=0.9)
        tab(page, "기록")
        point(page, card(page, re.compile(r"^액션 기록")).locator("h2"), hold=1.2)
    check(page, "A5", status="복구계획확정", open=6, tasks=7, log=14)

    # 장면 3. 조건 변경
    rec.scene(3, "조건 변경")
    with rec.step("B1"):
        set_role(page, OWNER)
        set_date(page, "2026-07-06")
        tab(page, "사건")
        bar = action_bar(page)
        click(page, bar.get_by_role("button", name="보도 등록", exact=True))
        click(page, bar.get_by_role("button", name="언론 보도 (미확정, 제품·배치 지목 없음)", exact=True), after=0.8)
        run(page, bar.get_by_role("button", name="보도 등록 실행", exact=True))
        point(page, card(page, exact("방금 바뀐 것")), hold=1.5)
    check(page, "B1", log=15)

    with rec.step("B2"):
        set_date(page, "2026-07-07")
        bar = action_bar(page)
        click(page, bar.get_by_role("button", name="클레임 등록", exact=True))
        click(page, bar.get_by_role("button", name="해제 배치 늦은 클레임 접수 (C-101, 800 EA)", exact=True), after=1.0)
        run(page, bar.get_by_role("button", name="클레임 등록 실행", exact=True))
        b3 = page.locator(f'main section[data-batch="{B3}"]')
        if b3.get_attribute("data-collapsed"):
            click(page, b3.get_by_role("button", name="펼치기"))
        point(page, b3, hold=2.5)
        set_date(page, "2026-07-08")
        click(page, b3.get_by_role("button", name="판정 반영"))
        click(page, b3.get_by_role("button", name="확정 → 재계산", exact=True), after=0.8)
        run(page, b3.get_by_role("button", name="클레임 판정 반영 실행", exact=True))
        point(page, b3, hold=2.5)
    check(page, "B2", status="복구계획확정", log=18)

    with rec.step("B3"):
        set_date(page, "2026-07-09")
        with rec.fast():
            reply_example(page, task(page, "안내 대상 결정"), "회수 배치 고객만")
            page.wait_for_timeout(800)
    check(page, "B3", log=19)

    with rec.step("B4"):
        reply_example(page, task(page, "수주 급감 확인", "C-101"), "C-101 우선 공급 요청")
        tab(page, "재공급 계획")
        point(page, card(page, exact("결정")), hold=2.0)
        point(page, card(page, "이전 버전과 비교"), hold=4.0)
        page.mouse.wheel(0, -5000)
    check(page, "B4", status="회수진행", open=5, tasks=8, log=22)

    with rec.step("B5"):
        tab(page, "사건")
        with rec.fast():
            reply_example(page, task(page, "출하 경위 확인"), "경위 확인됨 (보류 표시 미반영, 차단 항목 추가)")
            reply_example(page, task(page, "능력 확보 검토"), "확보 방안 있음 (증설·전환안, CEO/이사회 상신)")
        tab(page, "재공급 계획")
        point(page, card(page, exact("결정")), hold=1.5)
    check(page, "B5", log=24)

    with rec.step("B6"):
        set_role(page, SCM)
        dlg = open_plan_decision(page)
        point(page, dlg.locator('[data-hold-row="done"]'), hold=1.2)
        point(page, dlg.locator('[data-capacity-row="done"]'), hold=1.2)
        click(page, dlg.get_by_role("button", name="승인 (우선 공급 요청 반영)", exact=True), after=0.8)
        run(page, dlg.get_by_role("button", name=re.compile("결정 실행$")), after=0.9)
        point(page, card(page, exact("버전")), hold=1.5)
    check(page, "B6", status="복구계획확정", open=2, tasks=8, log=25, plans={"RP-v1": "대체됨", "RP-v2": "확정"})

    # 장면 4. 정보 부족과 승인 거절
    rec.scene(4, "정보 부족과 승인 거절")
    with rec.step("C1"):
        set_role(page, OWNER)
        set_date(page, "2026-07-10")
        tab(page, "연결망")
        cell = page.locator("[data-network] button[data-link]").filter(has_text="확인요청중").first
        point(page, cell, hold=2.0)
        click(page, cell, after=1.0)
        point(page, main.get_by_text(re.compile("출하 기록 없음")), hold=2.5)
        page.mouse.wheel(0, -5000)

    with rec.step("C2"):
        tab(page, "사건")
        t = task(page, "출하처 확인")
        click(page, t.get_by_role("button", name="회신 입력"))
        type_into(page, t.locator("textarea"), "기록 확인 불가, 7일 추가 필요")
        click(page, t.get_by_role("button", name="AI로 회신 분류"))
        use = t.get_by_role("button", name="이 내용 사용")
        with rec.fast():
            expect(use).to_be_visible(timeout=AI_TIMEOUT)
        point(page, t.get_by_text("분류 결과"), hold=1.2)
        click(page, use, after=0.8)
        expect(t.locator("select")).to_have_value("확인 불가")
        run(page, t.get_by_role("button", name="회신 반영 실행", exact=True))
        point(page, task(page, "출하처 확인").locator('[data-due="extended"]'), hold=1.8)
    check(page, "C2", status="복구계획확정", open=2, tasks=8, log=26)

    with rec.step("C3"):
        set_date(page, "2026-07-17")
        reply_example(page, task(page, "출하처 확인"), "출하 확인 (수량 기록 없음)")
        tab(page, "연결망")
        point(page, page.locator('[data-node="customer:C-105"]'), hold=1.5)
        tab(page, "재공급 계획")
        point(page, card(page, "고객별 재공급 순서").locator("tbody tr").nth(5), hold=4.0)
        page.mouse.wheel(0, -5000)
    check(page, "C3", status="회수진행", open=2, tasks=9, log=29)

    with rec.step("C4"):
        set_role(page, SCM)
        dlg = open_plan_decision(page)
        choose(page, dlg, "승인")
        type_into(page, dlg.locator("textarea"), "C-105 출하 확인 반영")
        run(page, dlg.get_by_role("button", name=re.compile("결정 실행$")), after=0.8)
        point(page, card(page, exact("버전")), hold=0.9)
    check(page, "C4", status="복구계획확정", open=1, tasks=9, log=30)

    with rec.step("D1"):
        set_role(page, OWNER)
        set_date(page, "2026-07-20")
        tab(page, "사건")
        reply_example(page, task(page, "수주 급감 확인", "C-104"), "C-104 우선 공급 요청")
        tab(page, "재공급 계획")
        point(page, card(page, "이전 버전과 비교"), hold=4.5)
        page.mouse.wheel(0, -5000)
    check(page, "D1", status="회수진행", open=1, tasks=10, log=33)

    with rec.step("D2"):
        set_role(page, SCM)
        set_date(page, "2026-07-21")
        dlg = open_plan_decision(page)
        choose(page, dlg, "거절")
        point(page, dlg.get_by_role("button", name=re.compile("결정 실행$")), hold=1.1)
        type_into(page, dlg.locator("textarea"), "C-103·C-102가 더 늦어져 v3 유지")
        run(page, dlg.get_by_role("button", name=re.compile("결정 실행$")), after=0.9)
        point(page, card(page, exact("버전")), hold=1.8)
        tab(page, "사건")
        point(page, page.locator("main [data-steps]"), hold=0.9)
        point(page, task(page, "결과 통보"), hold=1.5)
    check(page, "D2", status="복구계획확정", open=1, tasks=11, log=34,
          plans={"RP-v1": "대체됨", "RP-v2": "대체됨", "RP-v3": "확정", "RP-v4": "기각"})

    with rec.step("D3"):
        set_role(page, OWNER)
        set_date(page, "2026-07-22")
        t = task(page, "결과 통보")
        click(page, t.get_by_role("button", name="회신 입력"))
        type_into(page, t.locator("textarea"), "결과 확인함. 확정된 순서대로 진행")
        t.locator("select").select_option(label="확인함")
        page.wait_for_timeout(500)
        run(page, t.get_by_role("button", name="회신 반영 실행", exact=True))
        point(page, card(page, re.compile(r"^작업 열림")).locator("h2"), hold=1.2)
        tab(page, "기록")
        log = card(page, re.compile(r"^액션 기록"))
        point(page, log.locator("h2"), hold=0.9)
        row = log.locator("> div > ul > li").filter(has_text="2026-07-21").first
        click(page, row.locator("button").first, after=1.5)
    check(page, "D3", status="복구계획확정", open=0, tasks=11, log=35)

    # 장면 5. 필수 확장·다른 부서 영향
    rec.scene(5, "필수 확장·다른 부서 영향")
    with rec.step("S5"):
        tab(page, "연결망")
        point(page, page.locator('[data-node^="lot:"]'), hold=3.0)
        point(page, page.locator('[data-node="batch:B-02-2602-02"]'), hold=3.0)
        point(page, page.locator(f'[data-node="batch:{B3}"]'), hold=4.0)
        point(page, page.locator('[data-node="customer:C-105"]'), hold=3.0)
        tab(page, "재공급 계획")
        point(page, card(page, exact("버전")), hold=5.0)
        point(page, card(page, "고객별 재공급 순서"), hold=4.0)

    # 장면 6. 추가 확장
    rec.scene(6, "추가 확장")
    with rec.step("S6", tail=1.5):
        tab(page, "사건")
        more = card(page, re.compile(r"^작업 열림")).get_by_role("button", name=re.compile(r"^끝난 작업 \d+건 보기$"))
        click(page, more, after=1.0)
        cap = task(page, "능력 확보 검토")
        point(page, cap, hold=3.5)
        point(page, cap.locator("[data-capacity-options]"), hold=4.0)


# --- 조립 ---------------------------------------------------------------------

def srt_time(s: float) -> str:
    ms = int(round(s * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def split_caption(text: str, limit: int = 42) -> list[str]:
    """해설 한 토막을 문장 단위 자막 여러 줄로 나눈다."""
    out, cur = [], ""
    for sent in re.findall(r"[^.]+\.?\s*", text):
        sent = sent.strip()
        if not sent:
            continue
        if cur and len(cur) + len(sent) + 1 > limit:
            out.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        out.append(cur)
    return out


def assemble(rec: Recorder, end: float) -> None:
    # 녹화 시작 시각에 화면에 떠 있던 프레임(시작 전 마지막 프레임)부터 쓴다. 빼면 영상이 그만큼 앞당겨져 자막과 어긋난다
    before = [(t, p) for t, p in rec.frames if t < rec.t0]
    frames = ([(rec.t0, before[-1][1])] if before else []) + [(t, p) for t, p in rec.frames if t >= rec.t0]
    assert frames, "프레임 없음"
    # 초당 30장으로 고르게 편다: 영상의 n번째 그림 = 그 시각에 화면에 떠 있던 프레임 (링크만 만든다).
    # 프레임마다 길이를 적어 붙이는 방식은 길이가 조금씩 반올림돼 5분에 10초쯤 밀렸다
    seq = OUT / "seq"
    if seq.exists():
        shutil.rmtree(seq)
    seq.mkdir()
    times = [rec.map(t) for t, _ in frames]
    total = int(rec.map(end) * FPS)
    k = 0
    for n in range(total):
        while k + 1 < len(frames) and times[k + 1] <= n / FPS:
            k += 1
        os.symlink(frames[k][1], seq / f"{n:06d}.jpg")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(seq / "%06d.jpg"),
         "-vf", f"scale={W}:{H}:flags=lanczos,format=yuv420p", "-c:v", "libx264", "-crf", "18", "-preset", "medium",
         "-movflags", "+faststart", str(OUT / "video_only.mp4")], check=True)
    shutil.rmtree(seq)
    voiced = [c for c in rec.cues if (AUDIO / f"{c['id']}.mp3").is_file()]
    if voiced:
        # 해설 토막을 각자의 시작 시각에 놓고 하나로 섞어 영상에 얹는다
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(OUT / "video_only.mp4")]
        parts = []
        for i, c in enumerate(voiced, start=1):
            cmd += ["-i", str(AUDIO / f"{c['id']}.mp3")]
            ms = int(rec.map(c["start"]) * 1000)
            parts.append(f"[{i}:a]adelay={ms}:all=1[a{i}]")
        mix = "".join(f"[a{i}]" for i in range(1, len(voiced) + 1))
        parts.append(f"{mix}amix=inputs={len(voiced)}:normalize=0,apad[aout]")
        cmd += ["-filter_complex", ";".join(parts), "-map", "0:v", "-map", "[aout]", "-c:v", "copy",
                "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(OUT / "demo.mp4")]
        subprocess.run(cmd, check=True)
        (OUT / "video_only.mp4").unlink()
    else:
        (OUT / "video_only.mp4").replace(OUT / "demo.mp4")

    srt, n = [], 0
    cues = []
    for c in rec.cues:
        a, b = rec.map(c["start"]), rec.map(c["end"])
        cues.append({"id": c["id"], "scene": c["scene"], "start": round(a, 2), "end": round(b, 2), "read_seconds": round(c["need"], 1), "text": c["text"]})
        parts = split_caption(c["text"])
        total = sum(len(x) for x in parts)
        t = a
        for x in parts:
            d = c["need"] * len(x) / total
            n += 1
            srt += [str(n), f"{srt_time(t)} --> {srt_time(t + d)}", x, ""]
            t += d
    (OUT / "demo.srt").write_text("\n".join(srt), encoding="utf-8")
    info = {
        "length_seconds": round(rec.map(end), 1),
        "scenes": [{"n": s["n"], "title": s["title"], "start": round(rec.map(s["start"]), 2)} for s in rec.scenes],
        "fast_forward": [{"start": round(rec.map(a), 2), "video_seconds": FF_TARGET, "real_seconds": round(b - a, 1)} for a, b in rec.ff],
        "cues": cues,
    }
    (OUT / "cues.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"완성: {OUT / 'demo.mp4'} ({info['length_seconds']}초, 프레임 {len(frames)}장)")
    for s in info["scenes"]:
        print(f"  장면 {s['n']} {s['title']}: {s['start']}초부터")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> None:
    assert (ROOT / "frontend" / "dist" / "index.html").is_file(), "frontend/dist 없음: npm run build 먼저"
    assert shutil.which("ffmpeg"), "ffmpeg 없음"
    if FRAMES.exists():
        shutil.rmtree(FRAMES)
    FRAMES.mkdir(parents=True)
    synthesize()
    port = free_port()
    env = {**os.environ, "W03_DB_PATH": str(Path(tempfile.mkdtemp()) / "video.sqlite"), "W03_AI_REPLAY": "0"}
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.api.main:app", "--port", str(port), "--log-level", "warning"],
        cwd=ROOT, env=env)
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
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--lang=ko-KR"])
            ctx = browser.new_context(viewport={"width": W, "height": H}, base_url=url, locale="ko-KR")
            ctx.add_init_script(CURSOR_JS)
            page = ctx.new_page()
            page.set_default_timeout(10_000)
            page.goto("/")
            # 빈 상태에서 시작한다 (임시 DB라 이미 비어 있지만 화면 문구를 확인한다)
            expect(page.locator("main").get_by_role("heading", name="사건 열기", exact=True)).to_be_visible()
            page.mouse.move(W / 2, H / 2)
            rec = Recorder(page)
            rec.start()
            try:
                play(page, rec)
            except Exception:
                page.screenshot(path=str(OUT / "failed.png"))
                raise
            end = rec.stop()
            assemble(rec, end)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)


if __name__ == "__main__":
    main()
