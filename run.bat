@echo off
REM 카톡 색맞추기 봇 실행기 — venv 파이썬으로 kcmb.main 실행
REM 사용법:  run.bat --autostart --seconds 26      (자동 시작 + 26초 플레이)
REM         run.bat                                (F8=arm/disarm, F9=quit)
REM 게임 창을 화면에 띄우고, 실행 직전 게임 창을 한 번 클릭해 포커스하세요.
"%~dp0.venv\Scripts\python.exe" -m kcmb.main %*
