# 카카오톡 색 맞추기 미니게임 자동 플레이 봇 — 설계 문서 (v4)

- 작성일: 2026-07-01
- 상태: 초안 v4 (폐루프 제어 리뷰 반영, 사용자 리뷰 대기)
- v4 변경(핵심): 폐루프 드래그 제어를 **안전한 제어기**로 구체화 —
  (1) 매 라운드 **부호 탐침(sign-probe)** 으로 드래그→색판 반응 방향·gain을 실측,
  (2) **감쇠 비례 제어**(v = −λ·e/gain, λ≈0.5)로 오버슈트/발산 억제,
  (3) gain 갱신 **게이팅**(min_dist·이동량·방향 일치), 부호 포함 clamp,
  (4) 측정 전 **settle 게이트**(애니메이션 안정까지 폴링),
  (5) **stall/anti-windup** 정지 규칙 + 라운드 예산 타이머,
  (6) 드래그 입력을 **fling 방지 모션 프로파일** + `SendInput ABSOLUTE|VIRTUALDESK`로,
  (7) 좌표/벡터를 **np.array**로 통일. 구현 전 **상호작용 탐침(step 0)** 으로 실측.
- 유지: DPI, BGRA→BGR, 색 거리 지표, 캘리브레이션 골격, 안전장치, 순수/IO 분리.

## 0. 구현 전 필수: 상호작용 탐침 (probe)

이 설계의 상당수는 **실측이 필요한 가정**(§10)에 의존한다. 그래서 본 구현
이전에 아주 작은 실험 스크립트(`probe.py`)로 아래를 먼저 확인한다:

- 마우스 down→move→up 드래그가 게임에 **드래그로 등록**되는가(클릭/플링이 아니라)?
- 드래그하면 색 판이 **커서와 같은 방향(팬)** 으로 움직이는가, 반대인가? (부호)
- 놓은 뒤 **관성으로 더 미끄러지는가**(fling)? `선택`이 실시간 갱신되는가?
- 놓아도(up) 선택이 **잠기지 않고** 계속 조정 가능한가?

여기서 얻은 사실로 §5 제어 상수와 모션 프로파일을 확정한다. (탐침은 F8 arm
상태에서만 1회 드래그하고 전/후 스크린샷·`선택` 색을 로그.)

## 1. 목표 / 메커니즘

카카오톡 PC "정답과 같은 색 찾기"(라운드당 3초, 5라운드)를 자동으로 푼다.

### 1.1 게임 조작 (확인됨)
- 컬러 피커(마커)는 **팔레트 정중앙 고정**. **마커 지점 색 = `선택` 색(동일).**
- **팔레트를 드래그하면 색 판이 움직여** 중앙 마커 아래 색이 바뀐다(클릭으로
  마커가 이동하지 않음). 정답을 맞추려면 **정답 색을 중앙으로 끌어오는 드래그**.
- 팔레트는 각 위치에 실제 색을 표시(중앙=현재 선택)하므로, 정답 색의 화면상
  위치를 찾을 수 있다.

### 1.2 접근법: 부호 탐침 + 감쇠 비례 폐루프
드래그 커서 이동 대비 색판 이동 비율(gain)과 **부호**가 미지수이므로, 개루프가
아니라 관측 기반 폐루프로 수렴시킨다. 좌표는 화면 물리 픽셀, 벡터는 `np.array`.

- 오차 벡터 `e = P − C` (P=정답색 현재 위치, C=중앙 마커점).
- 콘텐츠가 커서를 따라 이동(팬)한다고 보면 필요한 커서 이동은 `v = −e/gain`.
  단 gain의 부호/크기가 미지수라 아래 제어기로 감싼다.

**제어기(정확한 안정성):** 위치 루프의 오차는 `e' = (1 − k/gain_est)·e`
(k=실제 gain, gain_est=제어기 추정치)로, `0 < k/gain_est < 2`에서만 수렴.
따라서 **감쇠 스텝** `v = −λ·e/gain_est` (λ≈0.5)를 쓰면 gain을 2배 잘못
추정해도 수축하고, 첫 스텝 오버슈트를 죽인다. gain 추정 평활(alpha)은 이
위치 루프와 **별개 루프**다(둘을 혼동하지 않는다).

## 2. 실행 환경 / 확정 사항

| 항목 | 결정 |
| --- | --- |
| 게임 위치 | 카카오톡 PC 클라이언트 (Windows 11, CEF 웹뷰) |
| 조작 | 화면 캡처 + 마우스 **드래그**(부호 탐침 + 감쇠 비례 폐루프) |
| 자동화 | 완전 자동 (정답색 변화로 새 라운드 감지) |
| 캘리브 | 1회: 정답/선택 스와치 + 팔레트 + 마커점 |
| 안전 | F8 arm/disarm(시작 disarm), F9 종료 |
| 런타임/권한 | Python 3.x; 봇·카톡 동일 integrity level(둘 다 비관리자) |

### 2.1 fail-safe (구체 규칙)
- **부호 탐침 실패**: 탐침 드래그 후 색판 이동 `< probe_min_shift_px` → "색판이
  반응 안 함"으로 그 라운드 중단(로그).
- **stall/anti-windup**: `best_dist`와 `no_improve_count` 추적. `color_dist`가
  `improve_margin` 이상 개선 못 하는 드래그가 `stall_no_improve_n`회(기본 3)
  연속이거나, 필요한 드래그 방향으로 P가 팔레트 경계에 붙으면(도달 불가) →
  드래그 중단, best 상태 유지, 로그.
- **발산 감지**: `color_dist(cur,target)`가 2회 연속 증가하면 그 타깃 드래그 중단.
- **라운드 예산**: `now − round_start > round_budget_ms`면 중단(best-effort).
- **disarm 우선**(F8), **미캘리브 가드**(§6.1).

## 3. 기술 스택

| 용도 | 라이브러리 | 비고 |
| --- | --- | --- |
| 캡처 | `mss` | BGRA→BGR(alpha 제거) |
| 색 계산 | `numpy` | 벡터화 거리, 좌표 np.array |
| 클러스터/캘리브 | `opencv-python` | connectedComponentsWithStats, selectROI |
| 마우스 | `ctypes` (Win32 `SendInput`) | ABSOLUTE\|VIRTUALDESK\|MOVE, 단일 채널 |
| 단축키 | `keyboard` | F8/F9 (§3.2) |

### 3.1 DPI (첫 줄, 창 생성 전) — 3단계 폴백
`user32.SetProcessDpiAwarenessContext(c_void_p(-4))` →
`shcore.SetProcessDpiAwareness(2)` → `user32.SetProcessDPIAware()`
(각 `try/except (AttributeError, OSError)`). DPI-aware면 mss와 SendInput이 동일
물리 픽셀 공간 공유.

### 3.2 입력 권한
카톡이 관리자면 UIPI로 비관리자 훅/입력이 막힘 → integrity level 일치. 통합
테스트에서 게임 포커스 상태로 F8/F9·드래그 등록 확인.

## 4. 색 거리 지표 (단일 정의)
`color_dist(a,b) = sqrt(Σ(채널차)^2)` (BGR, 0~441.67). 모든 색 임계값은 이 기준.

## 5. 아키텍처 / 모듈

```
color/
├── config.py       # 로드/저장/검증, Region/Point(np.array), is_calibrated()
├── dpi.py          # set_dpi_aware()
├── capture.py      # [I/O] grab(region)->BGR ndarray(alpha 제거)
├── coloralg.py     # [순수] color_dist, swatch_color(+dispersion), find_nearest_cluster
├── controller.py   # [순수] is_matched, probe_plan, plan_drag(감쇠), update_gain(게이팅), 발산/stall 규칙
├── targetstate.py  # [순수] 정답색 디바운스 → 안정 타깃 + 라운드 변화 감지
├── input_win.py    # [I/O] SendInput move/drag(모션 프로파일), settle 헬퍼
├── hotkeys.py      # [I/O] F8/F9
├── calibrate.py    # 진입점: 스케일-안전 selectROI + 마커점
├── probe.py        # 진입점: §0 상호작용 탐침
├── main.py         # 진입점: 폐루프 배선 + --dry-run + 가드 + 라운드 타이머
├── requirements.txt
└── README.md
```

### 5.1 `coloralg.py` (순수)
- `color_dist`, `swatch_color(img)->(color, dispersion)`(중앙 50% median + MAD 산포),
  `find_nearest_cluster(pal, target, eps)->(col,row,min_dist)`(최대 연결성분 중심점).

### 5.2 `controller.py` (순수 제어기 — 핵심)
모든 점/벡터는 `np.array([x,y])`. 상태는 명시 인자로 전달(순수).

- `is_matched(cur, target, tol) -> bool`.
- `probe_plan(C, ehat, probe_frac, bounds) -> (start, end)` — 부호/gain 탐침용
  고정 크기 드래그(방향 −ê 근사, 크기 `probe_frac·palette_dim`), 팔레트 내부.
- `estimate_gain(measured_shift, cursor_move) -> gain` — **부호 포함** 벡터/스칼라
  gain = shift/cursor_move; `|gain|`을 `[gain_min, gain_max]`로 clamp(0 근처 금지).
- `update_gain(gain, cursor_move, measured_shift, min_dist, cfg) -> gain` — **게이팅**:
  (a) `min_dist <= cluster_eps`(타깃 실제 존재), (b) `|cursor_move| >= move_floor_px`,
  (c) `dot(measured_shift, cursor_move) > 0` 및 수직성분 작음(클러스터 점프 아님)
  일 때만 새 추정을 지수평활로 반영; 아니면 이전 gain 유지.
- `plan_drag(e, gain, C, bounds, cfg) -> (start,end) | None` — **감쇠 비례**:
  `v = −λ·e/gain` (λ=`gain_lambda`≈0.5). `|e| <= e_deadband_px`면 `None`(데드밴드).
  `|v|`를 `max_drag_frac·palette_dim`로 cap. `start`는 −v 진행 여유가 남도록 C에서
  `+ê` 쪽으로 배치하고, **start·end 모두 팔레트 경계로 clamp 후 v를 clamp된
  끝점에서 재계산**(실행 드래그=계획 드래그).
- `divergence/stall`: 호출측(main)이 `prev_dist`, `best_dist`, `no_improve_count`를
  갖고, §2.1 규칙으로 중단 판단(controller는 순수 판정 함수 제공).

### 5.3 `targetstate.py` (순수)
`정답`색 디바운스(dispersion 배제 + N-프레임 안정) → 안정되고 직전 타깃과
`new_round_threshold` 초과로 달라지면 `NEW_TARGET`. 라운드 중 `정답` 불변이라
감지가 깔끔.

### 5.4 `input_win.py` — 드래그 프리미티브 (fling 방지)
전 제스처(down+이동+up)를 **하나의 SendInput 채널**로. 좌표는 절대이며
`MOUSEEVENTF_ABSOLUTE|MOUSEEVENTF_VIRTUALDESK|MOUSEEVENTF_MOVE`, 정규화는
`nx = round((px − SM_XVIRTUALSCREEN)·65535/(SM_CXVIRTUALSCREEN − 1))`(y 동일).

모션 프로파일(핵심):
1. down 후 **pre-dwell**(`drag_pre_dwell_ms`≈20) + 1~2px 미소 이동으로 OS/웹뷰
   드래그 임계(`SM_CXDRAG/SM_CYDRAG`) 통과 → 클릭이 아니라 드래그로 latch.
2. **ease-in/out** 보간 `drag_steps`(≈20)·`drag_step_ms`(≈9)로 시작·끝 속도 최소화.
3. **종단 정지 dwell**(`drag_end_dwell_ms`≈40): up 직전 무이동으로 릴리스 속도 ≈0
   → **fling 제거**.
4. up 후 **settle**: `settle_swatch()`가 `선택`을 `settle_poll_ms`(≈15)마다 폴링해
   연속 `settle_stable_reads`(2)회 안정(색차 ≤ stability_tolerance)까지 대기(cap
   `settle_cap_ms`≈120). 마커색과 판이 함께 움직이므로 **한 settle이 스와치·팔레트
   경쟁을 모두 커버** → 이후 `선택`/팔레트 캡처는 settle 뒤에 수행.
- **미등록/잠금 감지**: `|v|>move_floor`인데 측정 이동≈0이 2회 → 필드 잠김/무반응
  으로 중단(§10-A,D 실패를 표면화). 필요시 fallback: `InitializeTouchInjection/
  InjectTouchInput`로 포인터/터치 주입.

### 5.5 `main.py` 폐루프 배선
```
dpi.set_dpi_aware(); cfg = config.load()
if not config.is_calibrated(cfg): exit("calibrate.py 먼저")
ts = TargetState(cfg); C = cfg.marker if cfg.marker is not None else center(cfg.palette)  # np.array
gain = None; prev_v = prev_P = None; round_start = None
best_dist = inf; no_improve = 0; prev_dist = inf

loop (loop_delay_ms):
  if not armed: continue
  ans, adisp = swatch_color(grab(cfg.answer_swatch))
  if ts.observe(ans, adisp) == 'NEW_TARGET':
      gain=None; prev_v=prev_P=None; round_start=now; best_dist=inf; no_improve=0; prev_dist=inf
  target = ts.target
  if target is None: continue
  if now - round_start > cfg.round_budget_ms: continue        # 예산 초과 → best-effort 대기

  settle_swatch(cfg)                                          # 애니메이션 안정까지
  cur,_ = swatch_color(grab(cfg.selected_swatch))
  d = color_dist(cur, target)
  if controller.is_matched(cur, target, cfg.match_tolerance):
      prev_v=prev_P=None; continue                            # 매치: 상태 리셋 후 대기
  # stall/발산
  if d < best_dist - cfg.improve_margin: best_dist=d; no_improve=0
  else: no_improve += 1
  if no_improve >= cfg.stall_no_improve_n or d > prev_dist:    # 정체/발산
      prev_v=prev_P=None; continue                            # 이 타깃 드래그 중단
  prev_dist = d

  pal = grab(cfg.palette); col,row,mind = find_nearest_cluster(pal,target,cfg.cluster_eps)
  P = np.array([cfg.palette.left+col, cfg.palette.top+row]); e = P - C

  if gain is None:                                            # 라운드 첫 드래그 = 부호 탐침
      s,en = controller.probe_plan(C, unit(-e), cfg.probe_frac, cfg.palette)
      exec_or_dryrun(s,en); prev_P=P; prev_v=(en-s); continue # 다음 루프서 gain 추정
  if prev_P is not None:
      gain = controller.update_gain(gain, prev_v, P-prev_P, mind, cfg)  # 게이팅
      if gain is None or abs(gain)==0: ...                    # estimate 실패 → 재탐침
  plan = controller.plan_drag(e, gain, C, cfg.palette, cfg)
  if plan is None: continue                                   # 데드밴드
  s,en = plan; exec_or_dryrun(s,en); prev_P=P; prev_v=(en-s)
```
- `exec_or_dryrun`: 실행이면 `input_win.drag(s,en,cfg)`, dry-run이면 로그+디버그
  이미지 저장(및 `prev_P/prev_v`는 실드래그가 없으므로 갱신 안 함 — 그래서 dry-run은
  gain 적응 경로를 검증하지 못함; 그건 §11.1 폐루프 시뮬레이션으로 커버).
- **예산 현실화**: 반복당 캡처(3회)+매칭+드래그(≈180–260ms)+settle(≈60–120ms) ≈
  300ms → 3초에 **≤5회 보정** 설계. 첫 드래그는 크게(가능한 한 감쇠 내에서), 능동
  보정 중 `loop_delay_ms`는 작게(≈5). 매치 시 팔레트 재캡처/매칭 생략.

## 6. 설정 (`config.json`)
```json
{
  "answer_swatch":   {"left":0,"top":0,"width":0,"height":0},
  "selected_swatch": {"left":0,"top":0,"width":0,"height":0},
  "palette":         {"left":0,"top":0,"width":0,"height":0},
  "marker": null,

  "stability_tolerance": 6, "stability_frames": 2, "dispersion_tolerance": 12,
  "new_round_threshold": 40, "match_tolerance": 10, "cluster_eps": 6,

  "gain_lambda": 0.5, "gain_min": 0.05, "gain_max": 20, "gain_smooth_alpha": 0.5,
  "probe_frac": 0.12, "probe_min_shift_px": 4, "move_floor_px": 15,
  "max_drag_frac": 0.6, "e_deadband_px": 4,
  "stall_no_improve_n": 3, "improve_margin": 3, "round_budget_ms": 2800,

  "loop_delay_ms": 15,
  "drag_pre_dwell_ms": 20, "drag_steps": 20, "drag_step_ms": 9,
  "drag_end_dwell_ms": 40, "settle_poll_ms": 15, "settle_stable_reads": 2, "settle_cap_ms": 120
}
```
- 좌표: 물리 픽셀 절대(가상화면, 음수 가능). `marker: null`=미지정(팔레트 중심 사용).
  값은 모두 §0 탐침·§11.3 실측으로 보정하는 초기값.

### 6.1 검증
`is_calibrated`: answer/selected/palette 세 Region이 모두 `width>0 and height>0`.
아니면 main 종료 안내. (marker는 선택적, null 허용.)

## 7. 캘리브레이션 (`calibrate.py`)
1. `dpi.set_dpi_aware()`(첫 줄).
2. 기본 전체 가상화면(`monitors[0]`) 캡처(→ROI가 곧 절대좌표). `--monitor N` 가능.
   저장: `absolute = captured_origin(음수 가능) + roi_offset`.
3. 스케일-안전: 캡처가 화면보다 크면 다운스케일 복사본 표시, 반환 좌표에 스케일
   배수를 곱해 원본 픽셀로 되돌려 저장.
4. 지정: (1)정답 스와치 (2)선택 스와치 (3)팔레트 (4)마커점 클릭(생략 시 중심).
5. 확인: 저장 좌표 재캡처로 대표색/썸네일/마커점 출력.

## 8. 안전/검증 기능
F8/F9; §2.1 fail-safe(부호탐침/stall/발산/예산); `--dry-run`(드래그 미실행, 계획
드래그·e·gain·mind·디버그 이미지 로그 — 단 gain 적응은 dry-run서 미검증);
settle 게이트.

## 9. 엣지 케이스 / 한계
1. 색판 경계로 도달 불가 → stall 규칙으로 중단, best-effort.
2. 마커가 중앙 가림 → 현재색은 `선택` 스와치로 읽음.
3. 드래그 미등록/플링 → 모션 프로파일(pre-dwell/ease/종단 dwell) + settle; 미반응
   감지 시 중단·터치주입 fallback.
4. gain 부호/크기 오판 → 부호 탐침 + 게이팅 + 감쇠(λ) + 발산 중단.
5. 라운드 중 정답 변경 → `NEW_TARGET` 재발화·리셋.
6. 매치 근방 진동 → 데드밴드 + 감쇠.
7. 매치 분기서 상태 리셋(prev_P/prev_v=None)으로 stale 측정 방지.
8. DPI/멀티모니터 → §3.1/§7, VIRTUALDESK 정규화.

## 10. 실측 필요 가정 (§0 탐침·§11.3)
- (A) 드래그가 등록되고 색판이 팬 방식으로 이동(부호 포함) — 탐침으로 확정.
- (B) gain이 구간별로 대략 일정(심한 비선형이면 스텝 축소).
- (C) `선택`이 드래그 후 안정 시 현재 중앙색을 반영(settle로 완화).
- (D) up이 선택을 잠그지 않음(잠기면 미반응 감지·hold 방식 fallback).

## 11. 테스트 전략
### 11.1 단위(순수, 화면 불필요)
- coloralg.* / controller.plan_drag(방향·데드밴드·경계 clamp)·update_gain(게이팅·
  부호·평활)·is_matched / targetstate.observe.
- **폐루프 시뮬레이션**: 알려진 k(양·음·큰 값)의 가상 이동 색판으로, 부호 탐침 후
  ≤N스텝 수렴, 오판·클러스터 점프에도 발산/무한드래그 없음 검증. **핵심.**
- 좌표 변환(음수 origin 포함), VIRTUALDESK 정규화 산술.
### 11.2 수동/통합
- `probe.py`로 §0 확정. `--dry-run`으로 방향/계획 확인. 실드래그: 1보정 방향→
  1라운드 수렴→5라운드. 게임 포커스서 F8/F9·드래그 등록·post-up drift 측정.
### 11.3 실게임 실측
- 부호/gain/수렴 스텝/라운드 소요(3초 예산) 측정·튜닝. 창백·고채도 정답 도달성.

## 12. 구현 순서
1. `config.py`(+검증, np.array Point) · `dpi.py` · `capture.py`.
2. `coloralg.py` (TDD).
3. `controller.py` (TDD + 폐루프 시뮬레이션).
4. `targetstate.py` (TDD).
5. `input_win.py` (SendInput 드래그/모션 프로파일/settle) + **`probe.py`**.
6. **§0 탐침 실행** — 부호/팬/플링/잠금 실측, 상수 확정.
7. `calibrate.py`.
8. `main.py` 폐루프 배선 + `--dry-run` + 라운드 타이머/가드.
9. `hotkeys.py` 통합, README.
10. 실게임 dry-run → 실플레이 검증/튜닝.
