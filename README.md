# kakao-color-match-bot

카카오톡 PC 미니게임 "정답과 같은 색 찾기"를 제한 시간(3초) 안에 자동으로
풀어주는 봇. 화면을 캡처해 정답 스와치 색을 읽고, 팔레트에서 가장 가까운 색
위치를 찾아 마우스로 클릭한다.

> ⚠️ 개인 학습/자동화 실험용 프로젝트입니다.

## 상태

✅ **동작 확인 완료** — 단위 테스트 33 pass + 실게임 라이브 플레이 검증.
- 실측 결과: 5라운드 자동 플레이 **861~967점**, 대부분 라운드 96~99% 정확도.
- 설계: [docs/superpowers/specs/2026-07-01-kakao-color-match-bot-design.md](docs/superpowers/specs/2026-07-01-kakao-color-match-bot-design.md)
- 구현 계획: [docs/superpowers/plans/2026-07-01-kakao-color-match-bot.md](docs/superpowers/plans/2026-07-01-kakao-color-match-bot.md)

### 라이브에서 확인된 게임 메커니즘 / 제어
- 컬러피커는 팔레트 정중앙 고정. 팔레트를 **드래그**해 색 판을 움직여 정답 색을
  중앙으로 가져온다(클릭 아님). **첫 드래그로 게임 시작**, 이후 라운드 자동 진행.
- 드래그 이득(gain)·부호를 매 스텝 실측해 **감쇠 비례 폐루프**로 수렴. 정답 색이
  팔레트에 잘 안 보이면(mind 큼) gain 갱신을 막고 작은 탐침만 해 **발산 방지**.
- 종료 후 "게임 다시하기"로 재시작.

## 실행 방법 (Windows)

```
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest -q            # 단위 테스트 (33 pass)

.venv/Scripts/python -m kcmb.calibrate       # 1) 영역 지정(정답/선택/팔레트/마커)
.venv/Scripts/python -m kcmb.probe           # 2) 상호작용 실측(드래그 부호/팬/플링)
.venv/Scripts/python -m kcmb.main --dry-run  # 3) 목표 좌표 검증(debug/ 이미지)
.venv/Scripts/python -m kcmb.main            # 4) 실플레이 (F8 arm, F9 quit)
# 헤드리스(핫키 없이): 시작 드래그 + 지정 시간 자동 플레이
.venv/Scripts/python -m kcmb.main --autostart --seconds 26
```

> 카톡 게임 창이 foreground여야 드래그가 등록됩니다. 실행 직전 게임 창을 클릭해 두세요.

- 카카오톡과 봇은 같은 권한(둘 다 비관리자 권장)으로 실행.
- `config.json`(기기별 좌표)과 `debug/`는 커밋하지 않음(.gitignore).

## 동작 개요

1. **캘리브레이션(1회)** — 화면에서 정답 스와치와 팔레트 영역을 드래그로 지정.
2. **자동 루프** — 정답 색 변화를 새 라운드 신호로 감지 → 팔레트를 새로 캡처 →
   최적 매칭 클러스터 중심점을 클릭. F8로 on/off, F9로 종료.

핵심 아이디어: 팔레트의 색 모델을 역산하지 않고, 매 라운드 "정답 색 →
최근접 팔레트 위치"만 찾는다. 정답이 팔레트에 없으면(min-distance 초과) 클릭을
거부하는 fail-safe 포함.

## 기술 스택

Python · `mss`(캡처) · `numpy` · `opencv-python` · `ctypes`(Win32 SendInput) ·
`keyboard`(단축키). Windows 전용.

## 라이선스

MIT
