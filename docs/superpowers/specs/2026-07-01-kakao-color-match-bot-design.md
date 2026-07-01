# 카카오톡 색 맞추기 미니게임 자동 플레이 봇 — 설계 문서 (v3)

- 작성일: 2026-07-01
- 상태: 초안 v3 (조작 메커니즘 정정 반영, 사용자 리뷰 대기)
- v3 변경 (중요): **조작 방식이 "클릭"이 아니라 "드래그"임이 확인됨.** 컬러
  피커(마커)는 팔레트 **정중앙에 고정**이고, 팔레트를 드래그해 색 판을 움직여
  원하는 색을 중앙 마커로 가져오는 구조. 이에 따라 접근법을 **단발 클릭 →
  피드백 루프(closed-loop) 드래그 제어**로 전면 교체.
- v2 대비 유지: DPI 처리, BGRA→BGR, 색 거리 지표, 캘리브레이션 골격, 안전장치,
  순수/IO 분리, 테스트 전략. 교체: 상태 머신 → 타깃 디바운스 + 드래그 컨트롤러.

## 1. 목표

카카오톡 PC 클라이언트의 "정답과 같은 색 찾기" 미니게임(라운드당 3초, 5라운드)을
자동으로 풀어준다.

### 1.1 게임 조작 메커니즘 (확인됨)

- 컬러 팔레트(2D 색 판) 위에 **컬러 피커(마커)가 정중앙에 고정**되어 있다.
- **마커 지점의 색 = `선택` 스와치에 표시되는 색 (완전히 동일).**
- 사용자가 **팔레트를 드래그하면 색 판 자체가 움직이고**, 중앙 마커 아래로 오는
  색이 바뀐다. (클릭한 위치로 마커가 이동하는 것이 **아님**.)
- 따라서 정답을 맞추려면 **정답 색이 중앙 마커에 오도록 색 판을 드래그**해야 한다.
- 팔레트는 각 위치에 그 색을 실제로 표시한다(중앙 = 현재 선택). 즉 정답 색이
  화면 팔레트 어디에 있는지 위치로 찾을 수 있다.

### 1.2 접근법: 피드백 루프(closed-loop) 드래그 제어

정답 색을 중앙으로 "한 번에" 끌어오려면 드래그 이동량 대비 색 판 이동량의
비율(gain)을 정확히 알아야 하지만, 이 비율은 미지수다(1:1 공간 팬인지, drag
양에 비례한 rate 변화인지 불확실). 그래서 **개루프(한 번 계산해 끝)가 아니라
폐루프**로 간다:

1. `정답`(목표) 색과 현재 `선택`(중앙) 색을 읽는다.
2. 화면 팔레트에서 정답 색의 **현재 위치 P**를 찾는다(중앙 C까지의 오차 벡터 e = P−C).
3. e를 줄이는 방향으로 **드래그 한 번** 실행.
4. `선택` 색을 **다시 읽어** 목표에 도달했는지 확인. 아니면 실측으로 gain을
   보정하고 2로 반복 — 3초 예산 안에서 수렴시킨다.

- **자기검증**: 성공 여부를 `선택` 색으로 직접 관측하므로, "정답이 팔레트에서
  도달 가능한가?"가 관측 가능해진다(도달 못 하면 best-effort로 최대한 근접).
- gain을 몰라도 관측 기반 보정으로 수렴한다(합리적 gain 범위에서 수축).

## 2. 실행 환경 / 확정 사항

| 항목 | 결정 |
| --- | --- |
| 게임 실행 위치 | 카카오톡 PC 클라이언트 (Windows 11) |
| 조작 방식 | 화면 캡처 + **마우스 드래그** (피드백 루프) |
| 자동화 수준 | 완전 자동 (정답 색 변화로 새 라운드 감지) |
| 영역 설정 | 수동 캘리브레이션 1회 (정답/선택 스와치 + 팔레트 + 마커점) |
| 안전장치 | F8 arm/disarm(시작 disarm), F9 종료 |
| 언어/런타임 | Python 3.x (Windows) |
| 권한 | 봇과 카카오톡을 동일 integrity level로 실행(둘 다 비관리자 권장) |

### 2.1 fail-safe 원칙

- **수렴 관측**: 매 반복 `선택`↔`정답` 색 거리를 측정. `match_tolerance` 이내면
  성공. 라운드 예산 내 미수렴이면 최근접 상태로 멈추고 로그(자신 있게 틀린
  드래그를 남발하지 않음).
- **역방향/발산 감지**: 드래그 후 오차가 커지면 방향/gain을 반전·감쇠(§5.4).
- **disarm 우선**: F8로 즉시 중단. **미캘리브레이션 가드**로 실행 거부(§6.1).

## 3. 기술 스택

| 용도 | 라이브러리 | 비고 |
| --- | --- | --- |
| 화면 캡처 | `mss` | 영역 캡처, BGRA(4채널) → alpha 즉시 제거 |
| 색 계산 | `numpy` | 벡터화 거리 계산 |
| 클러스터/캘리브 | `opencv-python` | connectedComponentsWithStats, selectROI |
| 마우스 드래그 | `ctypes` (Win32 `SendInput`) | DPI-aware 물리 픽셀, 보간 이동 포함 |
| 전역 단축키 | `keyboard` | F8/F9 (§3.2 권한 주의) |

### 3.1 DPI 처리 (중요, 순서 제약)

각 진입점(`calibrate.py`, `main.py`) **첫 줄**에서 `dpi.set_dpi_aware()` 호출
(어떤 창/스크린샷 생성보다 먼저 — calibrate는 OpenCV 창을 열기 때문). 3-단계
폴백을 각각 `try/except (AttributeError, OSError)`로 감싼다:
1. `user32.SetProcessDpiAwarenessContext(c_void_p(-4))`  # PER_MONITOR_AWARE_V2
2. `shcore.SetProcessDpiAwareness(2)`                     # PER_MONITOR_AWARE v1
3. `user32.SetProcessDPIAware()`                          # 레거시

DPI-aware가 되면 `mss` 캡처와 `SendInput`/`SetCursorPos`가 동일한 물리 픽셀
좌표 공간을 공유한다(캡처 좌표 = 드래그 좌표 보장).

### 3.2 단축키/입력 권한 주의

카카오톡이 관리자 권한으로 실행되면 UIPI 때문에 비관리자 봇의 전역 훅/드래그가
그 창에 도달하지 못한다 → integrity level을 맞춘다(둘 다 비관리자 권장). 통합
테스트에서 게임 창 포커스 상태로 F8/F9와 드래그 입력이 실제로 먹는지 확인.

## 4. 색 거리 지표 (전 구간 단일 정의)

```
color_dist(a, b) = sqrt((a.b-b.b)^2 + (a.g-b.g)^2 + (a.r-b.r)^2)   # 0 ~ 441.67
```

- `match_tolerance`, `stability_tolerance`, `new_round_threshold`, `cluster_eps`는
  모두 이 지표(0~441) 기준. sRGB 유클리드는 지각적으로 완전 균일하진 않지만,
  폐루프가 `선택`을 목표로 직접 수렴시키므로 실용상 충분(필요 시 CIELAB로 교체 가능).

## 5. 아키텍처 / 모듈 구성

```
color/
├── config.py       # config.json 로드/저장/검증, Region/Point, is_calibrated()
├── dpi.py          # set_dpi_aware() (3-단계 폴백)
├── capture.py      # [I/O] mss 래퍼: grab(region) -> BGR ndarray (alpha 제거)
├── coloralg.py     # [순수] color_dist, swatch_color(+dispersion), find_nearest_cluster
├── controller.py   # [순수] 드래그 컨트롤러: is_matched/plan_drag/update_gain
├── targetstate.py  # [순수] 정답색 디바운스 → 안정 타깃 + 라운드 변화 감지
├── clicker.py      # [I/O] Win32 SendInput: move/click/**drag**(보간)
├── hotkeys.py      # [I/O] F8 arm 토글, F9 종료
├── calibrate.py    # 진입점: 스케일-안전 selectROI + 마커점 → config.json
├── main.py         # 진입점: 폐루프 배선 + --dry-run + 가드
├── requirements.txt
└── README.md
```

### 5.1 `coloralg.py` (순수)

- `color_dist(a, b) -> float` — §4.
- `swatch_color(img_bgr) -> (color_bgr, dispersion)` — 중앙 50% 크롭의 채널별
  median = 대표색; 산포(MAD 평균) = 전환/가림 프레임 감지용.
- `find_nearest_cluster(palette_bgr, target_bgr, eps) -> (col, row, min_dist)` —
  `dist2` 최소 픽셀 집합을 `min_dist+eps`로 임계 → 최대 연결성분의 **중심점**
  (col,row) 반환. 노이즈/안티에일리어싱/마커 헤일로에 강인. **팔레트에서 정답
  색의 현재 위치 P를 찾는 데 사용.**

### 5.2 `controller.py` (순수 드래그 컨트롤러 — 핵심 신규)

색/좌표 값만으로 다음 드래그를 계산한다. I/O 없음 → 시뮬레이션 단위 테스트 가능.

- `is_matched(current_bgr, target_bgr, tol) -> bool` — `color_dist <= tol`.
- `plan_drag(e, gain, center, bounds, max_frac) -> (start_pt, end_pt) | None`
  - `e = P - C` (오차 벡터). 색 판을 `-e`만큼 이동시켜야 함(콘텐츠는 커서를
    따라 이동하므로 필요한 커서 이동 `v = -e / gain`).
  - 팔레트 경계(`bounds`)와 `max_frac`(한 번에 팔레트 치수의 최대 비율)로 `v`를
    클램프 → 큰 오차는 여러 번 나눠 드래그(폐루프가 이어받음).
  - `start_pt`는 이동 여유가 있도록 중앙에서 `+ê` 쪽으로 오프셋한 점, `end_pt =
    start_pt + v_clamped`. 둘 다 팔레트 내부.
- `update_gain(gain, last_cursor_move, measured_field_shift) -> new_gain`
  - 직전 커서 이동 대비 타깃 위치 실제 변화(= 색 판 이동)로 gain 추정,
    지수 평활로 갱신. Newton식으로 다음 스텝이 목표에 근접.
- **발산 가드**: 오차가 줄지 않으면(부호 반대/과도) 방향 반전·gain 감쇠(호출측
  main이 measured_field_shift로 감지, controller가 규칙 제공).

### 5.3 `targetstate.py` (순수)

`정답` 색을 디바운스해 **안정 타깃**을 제공하고 라운드 변화를 감지.

```
class TargetState(cfg):
  target = None; prev = None; stable_count = 0
  def observe(self, answer_color, dispersion) -> event:  # event ∈ {None,'NEW_TARGET'}
    if dispersion > cfg.dispersion_tolerance:            # 전환/가림 프레임 배제
        self.stable_count = 0; self.prev = answer_color; return None
    if self.prev is not None and color_dist(answer_color, self.prev) <= cfg.stability_tolerance:
        self.stable_count += 1
    else:
        self.stable_count = 0
    self.prev = answer_color
    if self.stable_count >= cfg.stability_frames:
        if self.target is None or color_dist(answer_color, self.target) > cfg.new_round_threshold:
            self.target = answer_color
            return 'NEW_TARGET'
    return None
```

- 새 라운드에서 `정답`이 안정되면 `NEW_TARGET` → main이 이 타깃으로 폐루프 시작.
- 라운드 진행 중 `정답`은 불변, `선택`만 변하므로 라운드 감지가 깔끔.

### 5.4 `main.py` 폐루프 배선

```
dpi.set_dpi_aware(); cfg = config.load()
if not config.is_calibrated(cfg): exit("calibrate.py를 먼저 실행하세요")
ts = TargetState(cfg); gain = cfg.initial_gain; prev_v = prev_P = None
C = center_point(cfg.palette) 혹은 cfg.marker (있으면 우선)

loop (loop_delay_ms):
  if not armed: continue
  ans, ans_disp = swatch_color(capture.grab(cfg.answer_swatch))
  if ts.observe(ans, ans_disp) == 'NEW_TARGET':
      gain = cfg.initial_gain; prev_v = prev_P = None      # 새 라운드 → 컨트롤러 리셋

  target = ts.target
  if target is None: continue

  cur, _ = swatch_color(capture.grab(cfg.selected_swatch))  # 현재 중앙색(마커 가림 회피)
  if controller.is_matched(cur, target, cfg.match_tolerance):
      continue                                              # 이 라운드 완료, 정답 바뀔 때까지 대기

  pal = capture.grab(cfg.palette)
  col, row, mind = find_nearest_cluster(pal, target, cfg.cluster_eps)
  P = (cfg.palette.left+col, cfg.palette.top+row); e = P - C

  if prev_P is not None and prev_v is not None:
      gain = controller.update_gain(gain, prev_v, P - prev_P)   # 실측 보정
  plan = controller.plan_drag(e, gain, C, cfg.palette, cfg.max_drag_frac)
  if plan is None: continue
  start, end = plan
  if dry_run:
      log(f"[dry-run] target@{P} e={e} gain={gain:.2f} drag {start}->{end} mind={mind:.1f}")
      save_debug_image(pal, col, row)
  else:
      clicker.drag(start, end, cfg)                         # down→보간 이동→up
      prev_P = P; prev_v = (end - start)
```

- **드래그 등록**: 웹뷰가 드래그로 인식하려면 텔레포트가 아니라 다운 후 여러
  보간 move 이벤트 → 업. `drag_steps`/`drag_step_ms`로 제어.
- **3초 예산**: 반복당 캡처+매칭+드래그가 수십 ms → 3초 안에 수 회 보정 가능.
  안전상 라운드별 `round_budget_ms`(예: 2800) 초과 시 best-effort로 멈춤.
- **발산/역방향**: `update_gain`이 측정 이동으로 gain을 잡고, 오차가 커지면
  `plan_drag`가 방향 반전/감쇠. dry-run/통합 테스트로 부호 방향 최초 확인.

## 6. 설정 파일 (`config.json`)

```json
{
  "answer_swatch":   { "left": 0, "top": 0, "width": 0, "height": 0 },
  "selected_swatch": { "left": 0, "top": 0, "width": 0, "height": 0 },
  "palette":         { "left": 0, "top": 0, "width": 0, "height": 0 },
  "marker":          { "x": 0, "y": 0 },

  "stability_tolerance": 6,
  "stability_frames": 2,
  "dispersion_tolerance": 12,
  "new_round_threshold": 40,

  "match_tolerance": 10,
  "cluster_eps": 6,
  "initial_gain": 1.0,
  "max_drag_frac": 0.6,

  "loop_delay_ms": 20,
  "drag_steps": 12,
  "drag_step_ms": 6,
  "round_budget_ms": 2800
}
```

- 좌표는 물리 픽셀 절대 좌표(가상 화면, 음수 가능). `marker` 미지정 시 팔레트
  기하 중심을 C로 사용.
- 색 임계값은 §4(0~441) 기준의 **실측 보정 초기값**.

### 6.1 검증

- `is_calibrated(cfg)`: `answer_swatch`, `selected_swatch`, `palette` 세 Region이
  모두 `width>0 and height>0`인지. 아니면 `main.py`가 안내 후 종료.

## 7. 캘리브레이션 (`calibrate.py`)

1. `dpi.set_dpi_aware()` (첫 줄).
2. **모니터 선택**: 기본 전체 가상 화면(`monitors[0]`) 캡처 → ROI가 곧 절대
   좌표. `--monitor N`로 특정 모니터 지정 가능. 저장 규약: `absolute =
   captured_origin(left/top, 음수 가능) + roi_offset`.
3. **스케일-안전 selectROI**: 캡처가 화면보다 크면 다운스케일 복사본을 보여주되
   반환 (x,y,w,h)에 스케일 배수를 곱해 원본 픽셀로 되돌려 저장(스케일 이미지의
   좌표를 그대로 쓰지 않음).
4. 지정 대상: (1) `정답` 스와치, (2) **`선택` 스와치**, (3) 팔레트 사각형,
   (4) **마커점**(팔레트 중앙을 클릭; 생략 시 기하 중심 사용).
5. **확인**: 저장 좌표로 재캡처해 각 영역 대표색/썸네일과 마커점을 출력(오프셋/
   스케일 실수 즉시 발견).

## 8. 안전 및 검증 기능

- **F8 arm/disarm**(시작 disarm), **F9 종료**.
- **수렴 관측 fail-safe**(§2.1): 미수렴 시 best-effort 정지 + 로그.
- **`--dry-run`**: 드래그를 실행하지 않고 타깃 위치·오차 e·gain·계획된 드래그
  벡터·mind와 디버그 이미지를 로그. (단, 폐루프 전체 검증은 실제 드래그 피드백이
  필요하므로 실게임에서 수행 — §11.3.)
- **round_budget 가드**: 라운드당 드래그 시간 상한.

## 9. 엣지 케이스 / 알려진 한계

1. **색 판 경계**: 정답 색이 판 가장자리에 있어 중앙까지 팬이 부족하면 정확
   일치 불가 → best-effort. 미수렴 감지로 처리.
2. **마커가 중앙 픽셀 가림** → 현재 색은 팔레트 중앙이 아니라 **`선택` 스와치**로
   읽는다(설계에 반영).
3. **드래그 미등록(텔레포트)** → 보간 move + dwell 필수. dry-run/통합에서 확인.
4. **gain 방향/부호 오판** → 첫 드래그 후 측정으로 보정, 발산 시 반전(§5.4).
5. **정답이 라운드 중간에 바뀜(시간초과 등)** → `observe`가 `NEW_TARGET` 재발화,
   컨트롤러 리셋.
6. **오버슈트/진동** → gain 추정 + `max_drag_frac` 감쇠.
7. **DPI/멀티모니터** → §3.1, §7 규약(음수 origin 포함).
8. **캘리브 후 창 이동** → 좌표 무효화, `calibrate.py` 재실행.

## 10. 검증이 필요한 가정 (실제 카톡에서 확인)

- (A) 드래그가 색 판을 이동시키는 방식(§1.1)이 맞고, 마우스 down→move→up
  드래그가 게임에 등록된다.
- (B) 색 판 이동 gain이 대략 일정하다(구간별로 크게 비선형이 아니다). 비선형이어도
  폐루프가 국소적으로 수렴하지만, 심하면 스텝을 더 잘게.
- (C) 드래그 중/후 `선택` 스와치가 실시간으로 현재 중앙색을 반영한다(피드백 신호로 사용).
- (D) 드래그를 놓아도(up) 선택이 "제출/잠금"되지 않고 계속 조정 가능하다.

## 11. 테스트 전략

### 11.1 단위 테스트 (순수, 화면 불필요)
- `coloralg.*` — color_dist / swatch_color(+dispersion) / find_nearest_cluster.
- `controller.plan_drag` — 오차 e에 대한 드래그 방향·경계 클램프·start 내부성.
- `controller.update_gain` — 측정 이동에 대한 gain 수렴.
- `controller` **폐루프 시뮬레이션** — 알려진 gain의 가상 색 판(정답 픽셀을 담은
  이동 가능한 필드)을 모델링해, 컨트롤러가 N스텝 내 `match_tolerance`로 수렴하고
  gain 오차/역부호에서도 발산하지 않음을 검증. **핵심 신규 테스트.**
- `targetstate.observe` — 새 타깃 발화, 유사 라운드/전환 프레임 처리.
- 좌표 변환(모니터 origin, ROI → 절대, 음수 포함).

### 11.2 수동/통합
- `--dry-run`으로 타깃 위치·계획 드래그·디버그 이미지 확인.
- 실드래그 활성화 후: 1회 보정 방향이 맞는지 → 1라운드 수렴 → 5라운드.
- 게임 포커스 상태에서 F8/F9와 드래그 등록 확인.

### 11.3 실게임 실측 (구현 중 필수)
- 첫 드래그의 **부호/방향**이 맞는지(색 판이 예상 방향으로 움직이는지) 확인.
- gain 초기값과 수렴 스텝 수, 라운드당 소요 시간(3초 예산 대비) 측정·튜닝.
- 창백/고채도 정답 모두에서 `선택`이 목표까지 수렴하는지(도달성) 확인.

## 12. 구현 순서

1. `config.py`(+검증) · `dpi.py` · `capture.py`(BGRA→BGR).
2. `coloralg.py` (TDD).
3. `controller.py` (TDD, 폐루프 시뮬레이션 포함).
4. `targetstate.py` (TDD).
5. `calibrate.py` — 스케일-안전 selectROI + 4개 지정(정답/선택/팔레트/마커).
6. `clicker.py` — Win32 SendInput move/**drag**(보간).
7. `main.py` — 폐루프 배선 + `--dry-run` + 미캘리브 가드.
8. `hotkeys.py` 통합, README(권한/실행/검증) 작성.
9. **실게임: 드래그 방향/gain/수렴 실측 → dry-run → 실플레이 검증.**
