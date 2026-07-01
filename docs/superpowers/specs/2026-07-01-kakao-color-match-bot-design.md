# 카카오톡 색 맞추기 미니게임 자동 플레이 봇 — 설계 문서

- 작성일: 2026-07-01
- 상태: 초안 (사용자 리뷰 대기)

## 1. 목표

카카오톡 PC 클라이언트에서 실행되는 "정답과 같은 색 찾기" 미니게임을,
제한 시간 3초 안에 자동으로 풀어주는 프로그램을 만든다.

- 매 라운드 정답(정답 스와치) 색을 화면에서 읽는다.
- 그 순간의 컬러 팔레트를 새로 캡처해, **색이 가장 가까운 픽셀의 화면 좌표**를 찾아 클릭한다.
- 5라운드를 완전 자동으로 반복 처리한다.

### 핵심 원리 (색 공식 역산 안 함)

팔레트가 어떤 색 모델(HSV 등)로 그려지는지 **역산하지 않는다.** 정답 색은
반드시 팔레트 어딘가에 존재하므로(게임이 그렇게 설계됨), 매 라운드
"정답 색 읽기 → 팔레트 캡처 → 최근접 픽셀 클릭"만 하면 팔레트가 라운드마다
바뀌어도 항상 정답을 맞힐 수 있다. 팔레트는 라운드마다 **새로 캡처**한다(캐시 금지).

## 2. 실행 환경 / 확정된 결정 사항

| 항목 | 결정 |
| --- | --- |
| 게임 실행 위치 | 카카오톡 PC 클라이언트 (Windows 11) |
| 조작 방식 | PC 화면 캡처 + 마우스 직접 클릭 |
| 자동화 수준 | 완전 자동 루프 (정답 색 변화를 새 라운드 신호로 감지) |
| 영역 설정 | 수동 캘리브레이션 1회 (드래그로 지정, config에 저장) |
| 안전장치 | F8 arm/disarm 토글, F9 종료. 시작 시 disarm 상태 |
| 언어/런타임 | Python 3.x (Windows) |

## 3. 기술 스택

| 용도 | 라이브러리 | 비고 |
| --- | --- | --- |
| 화면 캡처 | `mss` | 빠른 영역 캡처, BGRA 반환 |
| 색 계산 | `numpy` | 벡터화된 최근접 색 탐색 |
| 마우스 클릭 | `ctypes` (Win32 API) | DPI 배율 문제 회피 위해 물리 픽셀로 직접 클릭 |
| 전역 단축키 | `keyboard` | F8 토글 / F9 종료 |
| 캘리브레이션 UI | `opencv-python` | `cv2.selectROI`로 드래그 영역 지정 |

### DPI 처리 (중요)

`calibrate.py`와 `main.py` **양쪽 모두** 시작 시 프로세스를 per-monitor DPI aware로
설정한다: `ctypes.windll.shcore.SetProcessDpiAwareness(2)`.
이렇게 하면 `mss` 캡처 좌표와 `SetCursorPos` 클릭 좌표가 **동일한 물리 픽셀 공간**을
공유하므로, 화면 배율(125%/150% 등)에서도 캡처 위치와 클릭 위치가 어긋나지 않는다.

## 4. 아키텍처 / 모듈 구성

각 모듈은 하나의 역할만 가지며 독립적으로 테스트 가능하도록 분리한다.

```
color/
├── config.py       # config.json 로드/저장, Region 데이터클래스
├── capture.py      # DPI 설정 + mss 래퍼: 영역 → numpy(BGR); 스와치 대표색
├── matcher.py      # 최근접 색 픽셀 탐색 (순수 함수, numpy)
├── clicker.py      # Win32 커서 이동 + 클릭 (DPI-aware, 물리 픽셀)
├── hotkeys.py      # F8 arm 토글, F9 종료 (keyboard)
├── calibrate.py    # cv2.selectROI 캘리브레이션 → config.json 저장
├── main.py         # 자동 루프 / 상태 머신 (--dry-run 지원)
├── requirements.txt
└── README.md
```

### 4.1 순수 로직 (화면 없이 테스트 가능)

- **matcher.py** — `find_nearest(palette_bgr, target_bgr) -> (col, row, distance)`
  - `dist2 = ((palette.astype(int) - target)**2).sum(axis=2)` → `argmin`.
  - RGB(BGR) 유클리드 거리 사용. 정답 색이 팔레트에 정확히 존재하므로
    최근접 픽셀의 거리는 ~0에 수렴한다(어떤 합리적 지표든 같은 지점을 찾음).
- **capture.py의 `swatch_color(img) -> (b,g,r)`** — 둥근 모서리/테두리/그림자
  영향을 피하려고 중앙 50% 영역만 잘라 **채널별 median**을 대표색으로 사용.
- **round-detection 상태 머신** (main.py 내 순수 함수로 분리) — 아래 5절.

### 4.2 I/O 래퍼 (수동 테스트)

- **capture.py**의 mss 캡처, **clicker.py**의 Win32 클릭, **hotkeys.py** — 얇은 래퍼.

## 5. 데이터 흐름 / 자동 루프 상태 머신

`main.py`는 다음 상태 머신을 돌린다. F8로 arm된 동안에만 동작한다.

```
상태: WAIT_STABLE  (새 정답이 안정되길 기다림)
상태: SOLVED       (이미 이 라운드를 풀었음, 색이 바뀌길 기다림)

last_solved_color = None

매 루프(loop_delay_ms 간격):
  if not armed: continue
  c = 정답 스와치 대표색 캡처

  [WAIT_STABLE]
    - 직전 프레임 색과 c의 거리가 stability tolerance 이하 → "안정"
    - 안정 && (last_solved_color 없음 OR dist(c, last_solved_color) > new_round_threshold):
        palette = 팔레트 영역 새로 캡처
        (col,row,dist) = find_nearest(palette, c)
        screen_x = palette.left + col;  screen_y = palette.top + row
        커서 이동 후 클릭
        last_solved_color = c
        상태 → SOLVED

  [SOLVED]
    - dist(c, last_solved_color) > new_round_threshold  (정답이 다른 색으로 전환됨)
        → 상태 = WAIT_STABLE
```

- **stability 체크**: 전환 페이드 애니메이션 중간 색을 클릭하는 것을 방지.
  연속 `stability_frames` 프레임 동안 색이 안정적일 때만 푼다.
- **SOLVED → WAIT_STABLE 전환**: 같은 라운드에서 중복 클릭 방지.
  라운드가 바뀌면 정답 색이 달라지므로 다시 WAIT_STABLE로 돌아간다.

## 6. 설정 파일 (`config.json`)

```json
{
  "answer_swatch": { "left": 0, "top": 0, "width": 0, "height": 0 },
  "palette":       { "left": 0, "top": 0, "width": 0, "height": 0 },
  "new_round_threshold": 25,
  "stability_tolerance": 8,
  "stability_frames": 2,
  "loop_delay_ms": 30,
  "click_hold_ms": 20
}
```

- 좌표는 **물리 픽셀** 기준 절대 좌표(전체 가상 화면).
- 임계값은 기본값 제공, 필요 시 사용자가 조정.

## 7. 캘리브레이션 흐름 (`calibrate.py`)

1. DPI aware 설정.
2. 대상 모니터 전체를 `mss`로 캡처.
3. `cv2.selectROI("정답 스와치를 드래그하세요", 스크린샷)` → 스와치 사각형.
4. `cv2.selectROI("팔레트 영역을 드래그하세요", 스크린샷)` → 팔레트 사각형.
5. 두 ROI를 화면 절대 좌표로 변환(모니터 오프셋 더하기) → `config.json` 저장.
6. 저장 후 확인용으로 각 영역을 다시 캡처해 대표색/썸네일을 출력.

## 8. 안전 및 검증 기능

- **F8 arm/disarm 토글** — 시작 시 disarm. arm 상태일 때만 마우스를 움직인다.
- **F9 종료** — 즉시 프로그램 종료.
- **`--dry-run` 모드** — 클릭 대신 계산된 목표 좌표를 콘솔에 출력하고,
  팔레트 캡처에 목표 지점을 마킹한 디버그 이미지를 저장. 실제 클릭 켜기 전
  정확도 검증용.
- **클릭 rate limit** — 초당 클릭 수 상한(예: 최대 5회/초)으로 폭주 방지.

## 9. 엣지 케이스 및 알려진 한계

1. **연속 라운드의 정답 색이 매우 비슷**하면 새 라운드를 놓칠 수 있음
   (dist ≤ new_round_threshold). 색 맞추기 게임 특성상 드묾 — v1 한계로 문서화.
2. **마커 핀이 정답 픽셀을 가림** — 드물게 그 라운드만 빗나갈 수 있음.
   완화책(선택): 팔레트에서 near-white 마커 픽셀을 마스킹 후 최근접 탐색.
3. **DPI 배율** — 두 스크립트 모두 SetProcessDpiAwareness로 처리.
4. **멀티 모니터** — 물리 픽셀 절대 좌표 사용. 캘리브레이션은 게임이 있는
   모니터를 캡처. mss와 SetCursorPos가 같은 좌표계를 공유.
5. **캘리브레이션 후 창 이동** — 좌표 무효화. 사용자가 `calibrate.py` 재실행.
6. **게임이 아닌 화면에서 arm 상태** — 오클릭 가능. 사용자가 F8로 disarm.

## 10. 검증이 필요한 가정 (실제 카톡에서 확인)

- 팔레트를 한 번 클릭하면 그게 바로 답으로 제출된다(별도 확인 버튼 없음).
- 마커를 드래그해 옮기는 방식이 아니라 탭/클릭으로 위치가 지정된다.
- → 만약 드래그 방식이면 `clicker.py`에 drag 동작만 추가하면 됨.

## 11. 테스트 전략

- **단위 테스트 (순수 로직, 화면 불필요)**:
  - `matcher.find_nearest` — 합성 배열에 알려진 색을 심고 argmin 좌표 검증.
  - `capture.swatch_color` — 합성 이미지의 median 대표색 검증.
  - round-detection 상태 머신 — 색 시퀀스를 입력해 "언제 solve하는지" 검증
    (연속 유사색 스킵, 전환 후 재-arm 등).
- **수동/통합 테스트**:
  - `--dry-run`으로 실제 게임 화면에서 목표 좌표 정확도 확인.
  - 클릭 활성화 후 1라운드 → 전체 5라운드 순으로 검증.
- 구현은 순수 로직 모듈에 대해 TDD(테스트 먼저) 적용.

## 12. 구현 순서 (개략)

1. `config.py` + `capture.py`(DPI/캡처/대표색) 골격.
2. `matcher.py` (TDD).
3. `calibrate.py` — config 생성.
4. `clicker.py` — Win32 클릭.
5. `main.py` — 상태 머신 + `--dry-run`.
6. `hotkeys.py` 통합, README 작성.
7. 실게임에서 dry-run → 실클릭 검증.
