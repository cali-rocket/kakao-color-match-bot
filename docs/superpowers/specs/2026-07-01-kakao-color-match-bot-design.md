# 카카오톡 색 맞추기 미니게임 자동 플레이 봇 — 설계 문서 (v2)

- 작성일: 2026-07-01
- 상태: 초안 v2 (4-critic 리뷰 반영, 사용자 리뷰 대기)
- v2 변경: 상태 머신 재작성/모듈 분리, 색 거리 지표 통일, min-distance fail-safe
  가드, 클러스터 중심점 클릭, BGRA alpha 처리, DPI/포커스/selectROI 정합성 등
  자체 리뷰(기술/일관성/스코프/견고성 4개 critic) 결과 반영.

## 1. 목표

카카오톡 PC 클라이언트에서 실행되는 "정답과 같은 색 찾기" 미니게임을,
제한 시간 3초 안에 자동으로 풀어주는 프로그램을 만든다.

- 매 라운드 정답(정답 스와치) 색을 화면에서 읽는다.
- 그 순간의 컬러 팔레트를 **새로 캡처**해, 색이 가장 가까운 픽셀(정확히는 최적
  매칭 클러스터의 중심점)의 화면 좌표를 찾아 클릭한다.
- 5라운드를 완전 자동으로 반복 처리한다.

### 1.1 핵심 원리와 그 전제 (중요)

접근법: 팔레트의 색 모델(HSV 등)을 역산하지 않고, "정답 색 읽기 → 팔레트
캡처 → 최근접 색 위치 클릭"만 한다.

**이 접근법은 하나의 전제 위에 서 있다: "정답 색이 캡처한 팔레트 영역 안에
실제 픽셀로 (거의) 정확히 존재한다."** 그래야 최근접 픽셀의 거리가 ~0이 되어
정확한 클릭 지점을 찾는다.

이 전제는 **미검증이며, 창백/저채도 정답에서 깨질 수 있다.** 예: 예시 화면의
정답은 창백한 크림색인데 팔레트는 고채도로 보인다. 만약 이 게임이 밝기/명도를
별도 슬라이더로 두는 구조라면, 창백한 색은 팔레트 픽셀에 존재하지 않고,
최근접 탐색은 팔레트의 가장 흰/옅은 모서리를 "자신 있게 틀리게" 클릭한다.

→ 따라서 설계는 **이 전제에 의존하지 않고 fail-safe로 동작**해야 한다(§2.1,
§5.4, §8). 그리고 구현 전/중에 **실측(§11.3)으로 전제를 검증**한다.

## 2. 실행 환경 / 확정된 결정 사항

| 항목 | 결정 |
| --- | --- |
| 게임 실행 위치 | 카카오톡 PC 클라이언트 (Windows 11) |
| 조작 방식 | PC 화면 캡처 + 마우스 직접 클릭 |
| 자동화 수준 | 완전 자동 루프 (정답 색 변화를 새 라운드 신호로 감지) |
| 영역 설정 | 수동 캘리브레이션 1회 (드래그로 지정, config에 저장) |
| 안전장치 | F8 arm/disarm 토글, F9 종료. 시작 시 disarm |
| 언어/런타임 | Python 3.x (Windows) |
| 권한 | 봇과 카카오톡을 **동일 integrity level**로 실행(둘 다 비관리자 권장). 전역 훅/클릭이 서로 도달하려면 필요 |

### 2.1 fail-safe 원칙

- **min-distance 가드**: 최적 매칭의 색 거리가 `max_match_dist`를 초과하면,
  "정답이 팔레트에 없음(풀 수 없음)"으로 보고 **클릭하지 않는다**(자신 있게
  틀리느니 그 라운드를 건너뛴다). 로그로 남긴다.
- **disarm 우선**: F8로 언제든 즉시 마우스 조작 중단.
- **미캘리브레이션 가드**: 영역이 0이면 실행 거부(§6.1).

## 3. 기술 스택

| 용도 | 라이브러리 | 비고 |
| --- | --- | --- |
| 화면 캡처 | `mss` | 영역 캡처, **BGRA(4채널) 반환 → alpha 즉시 제거** |
| 색 계산 | `numpy` | 벡터화 거리 계산 |
| 클러스터/캘리브 | `opencv-python` | `connectedComponentsWithStats`, `selectROI` |
| 마우스 클릭 | `ctypes` (Win32 `SendInput`) | DPI 배율 회피 위해 물리 픽셀 절대 좌표 |
| 전역 단축키 | `keyboard` | F8 토글 / F9 종료 (§3.2 권한 주의) |

### 3.1 DPI 처리 (중요, 순서 제약)

DPI aware 설정은 **어떤 창/스크린샷 생성보다 먼저**, 각 진입점(`calibrate.py`,
`main.py`)의 첫 줄에서 호출한다(`dpi.set_dpi_aware()`). 특히 `calibrate.py`는
OpenCV HighGUI 창을 열기 때문에 그 전에 호출해야 한다.

`set_dpi_aware()`는 아래 순서로 시도하며 각 호출을 `try/except (AttributeError,
OSError)`로 감싼다(구버전/매니페스트 선설정 대비):
1. `user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))`  # PER_MONITOR_AWARE_V2 (Win10 1703+/Win11 권장)
2. `shcore.SetProcessDpiAwareness(2)`  # PER_MONITOR_AWARE v1 (Win8.1+)
3. `user32.SetProcessDPIAware()`  # 레거시 시스템 DPI

DPI-aware가 되면 `mss` 캡처와 `SendInput`(SetCursorPos 포함)이 **동일한 물리
픽셀 좌표 공간**을 공유한다 — 이것이 캡처 좌표=클릭 좌표를 보장하는 근거다.

### 3.2 단축키/클릭 권한 주의

- `keyboard`는 Windows에서 대개 관리자 권한 없이 전역 훅이 동작한다. 단
  **카카오톡이 관리자 권한으로 실행되면** UIPI 때문에 비관리자 봇의 훅/클릭이
  그 창에 도달하지 못한다 → 둘의 integrity level을 맞춘다(둘 다 비관리자 권장).
- 대안: 두 개 정도의 핫키는 `RegisterHotKey`(ctypes)로 등록하면 더 안정적.
  v1은 `keyboard`로 시작하되 통합 테스트에서 게임 창 포커스 상태로 토글 동작을
  반드시 확인한다.

## 4. 색 거리 지표 (전 구간 단일 정의)

모든 색 비교는 **BGR 유클리드 거리**로 통일한다:

```
color_dist(a, b) = sqrt( (a.b-b.b)^2 + (a.g-b.g)^2 + (a.r-b.r)^2 )   # 범위 0 ~ 441.67
```

- 상태 머신 임계값(`stability_tolerance`, `new_round_threshold`)과 매칭 가드
  (`max_match_dist`)는 모두 이 지표(0~441) 기준의 값이다.
- sRGB(감마 인코딩) 상의 유클리드 거리는 지각적으로 균일하지 않다. 정확히
  일치하는 픽셀이 존재할 때는 문제없지만(거리 ~0), min-distance가 커지는
  경우엔 지각적으로 틀릴 수 있다 → 이때는 클릭을 거부한다(§2.1). (선택적
  향후 개선: min-distance가 애매할 때 CIELAB 재계산.)

## 5. 아키텍처 / 모듈 구성

각 모듈은 단일 책임을 가지며, 순수 로직과 I/O를 분리해 화면 없이 단위 테스트가
가능하게 한다.

```
color/
├── config.py       # config.json 로드/저장/검증, Region 데이터클래스, is_calibrated()
├── dpi.py          # set_dpi_aware() (3-단계 폴백, try/except)
├── capture.py      # [I/O] mss 래퍼: grab(region) -> BGR ndarray (alpha 제거)
├── coloralg.py     # [순수] color_dist, swatch_color(+dispersion), find_nearest_cluster
├── roundstate.py   # [순수] RoundState: observe()/mark_solved() 상태 머신
├── clicker.py      # [I/O] Win32 SendInput 클릭 (foreground/이동/dwell/hold)
├── hotkeys.py      # [I/O] F8 arm 토글, F9 종료 (keyboard)
├── calibrate.py    # 진입점: 가상화면 캡처 + selectROI(스케일 안전) -> config.json
├── main.py         # 진입점: 루프 배선 + --dry-run + 미캘리브 가드 + rate 가드
├── requirements.txt
└── README.md
```

### 5.1 `coloralg.py` (순수 함수, 화면 불필요)

- `color_dist(a, b) -> float` — §4 정의.
- `swatch_color(img_bgr) -> (color_bgr, dispersion)`
  - 중앙 50% 영역만 크롭(둥근 모서리/테두리/그림자 배제).
  - `color` = 채널별 median (평탄 스와치의 대표색).
  - `dispersion` = 크롭 내 픽셀 산포도(채널별 MAD의 평균 등). **blended/전환
    중간/가림 프레임 감지용** — 산포가 크면 그 프레임은 "안정 색"으로 쓰지 않음.
- `find_nearest_cluster(palette_bgr, target_bgr, eps) -> (col, row, min_dist)`
  - `dist2 = ((palette.astype(int32) - target)**2).sum(axis=2)` (모두 3채널 보장).
  - `min_dist = sqrt(dist2.min())`.
  - `mask = dist2 <= (min_dist + eps)**2` → `cv2.connectedComponentsWithStats`로
    가장 큰 컴포넌트 선택 → 그 **중심점(centroid)** 의 (col, row) 반환.
  - 단일 argmin 대신 클러스터 중심을 쓰는 이유: 노이즈/안티에일리어싱 경계/
    마커 헤일로에 강인하고, 동질 색 영역 내부를 클릭하게 됨.

### 5.2 `roundstate.py` (순수 상태 머신, 화면 불필요)

색 시퀀스만으로 "언제 풀지"를 결정한다. I/O 없음 → 시퀀스 입력 단위 테스트.

상태: `WAIT_STABLE`(새 정답이 안정되길 대기), `SOLVED`(이번 라운드 처리 완료,
색이 바뀌길 대기).

```
class RoundState(cfg):
  state = WAIT_STABLE
  last_solved_color = None
  prev_frame_color  = None
  stable_count      = 0

  def observe(self, color, dispersion) -> action:   # action ∈ {None, 'ATTEMPT'}
    # 1) 전환/가림 프레임 배제
    if dispersion > cfg.dispersion_tolerance:
        self.stable_count = 0
        self.prev_frame_color = color
        return None

    # 2) 안정성 카운터 (N-프레임)
    if self.prev_frame_color is not None and \
       color_dist(color, self.prev_frame_color) <= cfg.stability_tolerance:
        self.stable_count += 1
    else:
        self.stable_count = 0
    self.prev_frame_color = color
    is_stable = self.stable_count >= cfg.stability_frames

    # 3) 상태별 처리
    if self.state == WAIT_STABLE:
        if is_stable and (self.last_solved_color is None or
                          color_dist(color, self.last_solved_color) > cfg.new_round_threshold):
            return 'ATTEMPT'        # main이 팔레트 캡처+매칭+클릭 수행
    elif self.state == SOLVED:
        # 정답이 충분히 다른 색으로 '변화'해야 다음 라운드 대기로 복귀
        if self.last_solved_color is not None and \
           color_dist(color, self.last_solved_color) > cfg.new_round_threshold:
            self.state = WAIT_STABLE
            self.stable_count = 0
    return None

  def mark_solved(self, color):    # main이 ATTEMPT 처리 후(클릭했든 가드로 스킵했든) 호출
    self.last_solved_color = color
    self.state = SOLVED
```

- **첫 라운드 trace**: 초기 `WAIT_STABLE`, `last_solved_color=None`,
  `prev_frame_color=None`. 첫 프레임: prev=None이므로 stable_count=0(불안정),
  prev←color. 같은 색 프레임이 이어지면 stable_count가 오르고,
  `stable_count>=stability_frames`가 되는 순간 `last_solved_color=None` 조건으로
  `ATTEMPT` 반환 → 첫 라운드가 확실히 풀린다(데드락 없음).
- **중복 클릭 방지**: `ATTEMPT` 후 `mark_solved`가 `SOLVED`로 전환. 같은 색이
  유지되는 동안은 다시 풀지 않음.
- **재무장**: 정답이 `new_round_threshold`를 넘겨 변하면 `WAIT_STABLE` 복귀.
- **알려진 한계**: 연속 두 라운드의 정답 색이 `new_round_threshold` 이내로
  비슷하면 새 라운드를 놓칠 수 있음(§9.1). 임계값은 실측으로 보정(§11.3),
  `new_round_threshold >> stability_tolerance` 여유를 둔다.

### 5.3 I/O 래퍼

- `capture.grab(region) -> ndarray` : `np.array(sct.grab(region))[:, :, :3]`
  (BGRA→BGR). 모든 하류 배열은 3채널 보장.
- `clicker.click(x, y, cfg)` : (선택) 대상 창 foreground 확인/보정 → `SetCursorPos`
  → 짧은 dwell → `SendInput` LEFTDOWN → `click_hold_ms` → LEFTUP.
  - `SendInput` 사용(권장; `mouse_event`는 공식적으로 superseded). 좌표는 DPI-aware
    물리 픽셀. `SetCursorPos`는 음수 좌표(좌/상단 모니터)도 처리.
- `hotkeys` : F8 arm 토글(시작 disarm), F9 종료.

### 5.4 `main.py` 루프 배선

```
dpi.set_dpi_aware()                     # 첫 줄
cfg = config.load()
if not config.is_calibrated(cfg): exit("calibrate.py를 먼저 실행하세요")
rs = RoundState(cfg)
loop (loop_delay_ms 간격):
  if not armed: continue
  img = capture.grab(cfg.answer_swatch)                 # BGR
  color, disp = coloralg.swatch_color(img)
  if rs.observe(color, disp) == 'ATTEMPT':
      palette = capture.grab(cfg.palette)               # 매 라운드 새로 캡처
      col, row, min_dist = coloralg.find_nearest_cluster(palette, color, cfg.cluster_eps)
      sx, sy = cfg.palette.left + col, cfg.palette.top + row
      if min_dist > cfg.max_match_dist:
          log(f"UNSOLVABLE min_dist={min_dist:.1f} → 클릭 스킵")   # fail-safe (§2.1)
      elif not respects_min_interval(now, last_click):
          log("클릭 간격 가드로 스킵")
      elif dry_run:
          log(f"[dry-run] target=({sx},{sy}) min_dist={min_dist:.1f}")
          save_debug_image(palette, col, row)           # 목표 지점 마킹 저장
      else:
          clicker.click(sx, sy, cfg); last_click = now
      rs.mark_solved(color)
```

- **3초 예산**: `loop_delay_ms=30`(~33fps)이면 감지+캡처+매칭+클릭이 3초 대비
  충분히 빠름 → 별도 타임아웃 로직 불필요. 단 dry-run에서 루프별 wall-time을
  로그해 실측 마진을 확인(§11.3).
- **rate 가드**: `min_click_interval_ms`(기본 500)로 우발적 연속 클릭 방지
  (상태 머신 dedup이 1차 방어, 이건 보조).

## 6. 설정 파일 (`config.json`)

```json
{
  "answer_swatch": { "left": 0, "top": 0, "width": 0, "height": 0 },
  "palette":       { "left": 0, "top": 0, "width": 0, "height": 0 },

  "stability_tolerance": 6,
  "stability_frames": 2,
  "dispersion_tolerance": 12,
  "new_round_threshold": 40,

  "cluster_eps": 6,
  "max_match_dist": 30,

  "loop_delay_ms": 30,
  "click_hold_ms": 20,
  "min_click_interval_ms": 500
}
```

- 좌표는 **물리 픽셀 절대 좌표**(가상 화면 기준, 음수 가능).
- 색 관련 임계값은 §4 지표(0~441) 기준. **모두 실측으로 보정**하는 초기값이다.

### 6.1 검증

- `is_calibrated(cfg)`: 두 Region 모두 `width>0 and height>0`인지 확인. 아니면
  `main.py`가 안내 메시지 후 종료.

## 7. 캘리브레이션 흐름 (`calibrate.py`)

1. `dpi.set_dpi_aware()` (첫 줄, 창 생성 전).
2. **모니터 선택**: 기본은 전체 가상 화면(`sct.monitors[0]`)을 캡처 → ROI 좌표가
   곧 가상 화면 절대 좌표가 되어 오프셋 변환이 단순해진다. 여러 모니터면
   `--monitor N`으로 특정 모니터(`monitors[N]`)만 캡처 가능.
   - 저장 규칙(단일 규약): `absolute = captured_origin + roi_offset`, 여기서
     `captured_origin`은 실제 사용한 mss monitor dict의 `left/top`(음수 가능).
     `monitors[0]` 사용 시 그 origin이 곧 가상화면 원점이다.
3. **selectROI 스케일 안전 처리**: 캡처 이미지가 화면보다 크면(4K/배율/멀티모니터)
   기본 `selectROI` 창이 넘쳐 드래그 불가/스케일 좌표 오염이 생긴다. 따라서:
   - 화면에 들어오도록 **다운스케일한 복사본**을 표시하되, 반환된 (x,y,w,h)에
     **정확한 스케일 배수를 곱해 원본 픽셀로 되돌린 뒤** 저장한다. 스케일된
     이미지를 그대로 쓰고 원좌표를 저장하지 않는다.
4. `selectROI`로 (1) 정답 스와치, (2) 팔레트 사각형 지정 → 위 규칙으로 절대
   좌표 계산 → `config.json` 저장.
5. **확인**: 저장 좌표로 두 영역을 다시 grab해 대표색/썸네일을 출력(스케일/오프셋
   실수 즉시 발견).

## 8. 안전 및 검증 기능

- **F8 arm/disarm** (시작 disarm), **F9 종료**.
- **min-distance fail-safe** (§2.1): `max_match_dist` 초과 시 클릭 거부.
- **`--dry-run`**: 클릭 대신 목표 좌표·min_dist·루프 wall-time 로그 + 팔레트에
  목표 지점을 마킹한 디버그 이미지 저장. 실클릭 전 정확도/전제 검증용.
- **min_click_interval 가드**: 우발적 연속 클릭 방지.

## 9. 엣지 케이스 및 알려진 한계

1. **연속 라운드 정답 색이 매우 유사**(≤ new_round_threshold) → 새 라운드 놓칠
   수 있음. 임계값 실측 보정으로 완화, 잔여 한계로 문서화.
2. **마커 핀이 정답 픽셀 가림** → 클러스터 중심점 방식이 가림 경계를 자연히
   회피. 추가로 마지막 클릭 좌표 부근을 위치 기반 마스킹(색 기반 아님) 가능.
   near-white 색 마스킹은 정답이 창백할 때 정답 영역을 지울 수 있어 지양.
3. **DPI 배율** → §3.1 처리.
4. **멀티 모니터** → §7의 단일 좌표 규약(음수 origin 포함)으로 처리. 캡처와
   클릭이 동일 절대 좌표 사용.
5. **캘리브 후 창 이동** → 좌표 무효화, `calibrate.py` 재실행.
6. **게임 아닌 화면에서 arm** → 오클릭 가능. F8 disarm + min-distance 가드가 완화.
7. **페이드 전환 중간색 오클릭** → dispersion 체크 + N-프레임 안정성 + '변화 후
   안정' 요구로 완화. 잔여 위험은 실측으로 임계값 보정.

## 10. 검증이 필요한 가정 (실제 카톡에서 확인)

- (A) 팔레트를 한 번 클릭하면 그게 바로 답으로 제출된다(별도 확인 버튼 없음).
  드래그로 마커를 옮기는 방식이 아니라 탭/클릭으로 지정된다.
  → 드래그 방식이면 `clicker`에 drag 동작만 추가.
- (B) **[핵심 리스크]** 정답 색이 캡처한 팔레트 영역 안에 픽셀로 존재한다(§1.1).
  창백/저채도 정답이 팔레트에 없을 수 있음. → §11.3 실측으로 검증하며, 없으면
  캘리브 영역에 명도 슬라이더 등 추가 영역 포함 또는 접근법 조정.
- (C) 마커 핀의 실제 색/형태(near-white 가정 검증).

## 11. 테스트 전략

### 11.1 단위 테스트 (순수 로직, 화면 불필요)
- `coloralg.color_dist` — 알려진 값 검증.
- `coloralg.swatch_color` — 합성 이미지의 median/ dispersion 검증(평탄 vs 혼합).
- `coloralg.find_nearest_cluster` — 합성 팔레트에 색을 심고 (col,row)·min_dist,
  노이즈 픽셀 강인성(클러스터 중심) 검증.
- `roundstate.RoundState` — 색 시퀀스 입력으로 action 시점 검증:
  첫 라운드 solve, 중복 클릭 없음, 유사 라운드 스킵, 페이드 프레임 배제,
  변화 후 재무장.
- **좌표 변환** — (모니터 origin, ROI) → 절대 좌표 산술(음수 origin 포함) 검증.

### 11.2 수동/통합 테스트
- `--dry-run`으로 실게임에서 목표 좌표·디버그 이미지 확인.
- 클릭 활성화 후 1라운드 → 전체 5라운드 검증. F8/F9가 게임 포커스 상태에서
  동작하는지 확인.

### 11.3 전제 실측 (구현 전/중 필수)
- 여러 실제 라운드(창백·고채도 정답 모두 포함)에서 `find_nearest_cluster`의
  `min_dist`를 수집·로그.
- 모든 라운드에서 min_dist가 작게(수 LSB) 유지되면 §1.1 전제 성립 → 진행.
- 창백 정답에서 min_dist가 크면 전제 불성립 → 캘리브 영역/접근법 조정(§10-B).
- 루프별 wall-time을 측정해 3초 예산 대비 마진 확인.

## 12. 구현 순서 (개략)

1. `config.py`(+검증) · `dpi.py` · `capture.py`(BGRA→BGR) 골격.
2. `coloralg.py` (TDD).
3. `roundstate.py` (TDD) — 상태 머신 시퀀스 테스트.
4. `calibrate.py` — 스케일 안전 selectROI → config 생성.
5. `clicker.py` — Win32 SendInput 클릭.
6. `main.py` — 루프 배선 + `--dry-run` + 미캘리브 가드.
7. `hotkeys.py` 통합, README(권한/실행법/전제 검증) 작성.
8. **실게임 dry-run으로 §11.3 전제·좌표 정확도 검증 → 실클릭 검증.**
