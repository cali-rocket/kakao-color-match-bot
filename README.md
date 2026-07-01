# kakao-color-match-bot

카카오톡 PC 미니게임 "정답과 같은 색 찾기"를 제한 시간(3초) 안에 자동으로
풀어주는 봇. 화면을 캡처해 정답 스와치 색을 읽고, 팔레트에서 가장 가까운 색
위치를 찾아 마우스로 클릭한다.

> ⚠️ 개인 학습/자동화 실험용 프로젝트입니다.

## 상태

🚧 **설계 단계** — 아직 구현 전. 설계 문서:
[docs/superpowers/specs/2026-07-01-kakao-color-match-bot-design.md](docs/superpowers/specs/2026-07-01-kakao-color-match-bot-design.md)

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
