# Test Log

Per-run summaries appended automatically by `agent/run_tests.py`.
Raw machine-readable results live in `agent/logs/run_<timestamp>.json`.

## Run 2026-07-07 19:59:50

- Silvia reachable: False
- Tests: 25 | Passed: 0 | Failed: 25
- Raw log: `agent/logs/run_20260707_195950.json`
- Report: `agent/reports/latest_failure_report.md`
  - [FAIL] hal-001 — What is Project Nebula?
  - [FAIL] hal-002 — What is Project Artemis?
  - [FAIL] hal-003 — What is the deadline for Project Nebula?
  - [FAIL] hal-004 — What is the current status of Project Zephyr?
  - [FAIL] hal-005 — What did I decide about Project Nebula in my notes?
  - [FAIL] hal-006 — Give me a quick update on Silvia.
  - [FAIL] lat-001 — Hello, are you online?
  - [FAIL] lat-002 — What time is it?
  - [FAIL] lat-003 — Give me a quick update on Silvia.
  - [FAIL] lat-004 — What are my current main projects?
  - [FAIL] og-001 — What are my current main projects?
  - [FAIL] og-002 — What is Silvia supposed to do?
  - [FAIL] og-003 — What is the current status of Silvia?
  - [FAIL] og-004 — What are my robotics projects?
  - [FAIL] og-005 — Summarise what you know about my projects from Obsidian.
  - [FAIL] og-006 — What are my goals for Silvia?
  - [FAIL] tu-001 — What time is it?
  - [FAIL] tu-002 — Show chat latency
  - [FAIL] tu-003 — What hardware projects do I have?
  - [FAIL] tu-004 — What's in my hardware inventory?
  - [FAIL] tu-005 — Open the knowledge board.
  - [FAIL] vp-001 — Voice subsystem reports a valid state
  - [FAIL] vp-002 — TTS synthesizes short text quickly
  - [FAIL] vp-003 — Voice latency metrics endpoint responds
  - [FAIL] vp-004 — What time is it?

## Run 2026-07-07 20:05:28

- Silvia reachable: True
- Tests: 25 | Passed: 10 | Failed: 15
- Raw log: `agent/logs/run_20260707_200528.json`
- Report: `agent/reports/latest_failure_report.md`
  - [PASS] hal-001 — What is Project Nebula? (4.538s)
  - [PASS] hal-002 — What is Project Artemis? (4.197s)
  - [FAIL] hal-003 — What is the deadline for Project Nebula? (4.27s)
  - [PASS] hal-004 — What is the current status of Project Zephyr? (2.152s)
  - [FAIL] hal-005 — What did I decide about Project Nebula in my notes? (39.822s)
  - [FAIL] hal-006 — Give me a quick update on Silvia. (3.989s)
  - [FAIL] lat-001 — Hello, are you online? (9.33s)
  - [PASS] lat-002 — What time is it? (2.14s)
  - [PASS] lat-003 — Give me a quick update on Silvia. (2.116s)
  - [PASS] lat-004 — What are my current main projects? (6.026s)
  - [FAIL] og-001 — What are my current main projects? (9.555s)
  - [FAIL] og-002 — What is Silvia supposed to do? (2.109s)
  - [FAIL] og-003 — What is the current status of Silvia? (2.083s)
  - [FAIL] og-004 — What are my robotics projects? (6.09s)
  - [FAIL] og-005 — Summarise what you know about my projects from Obsidian. (14.481s)
  - [FAIL] og-006 — What are my goals for Silvia? (10.101s)
  - [PASS] tu-001 — What time is it? (2.078s)
  - [FAIL] tu-002 — Show chat latency (2.075s)
  - [FAIL] tu-003 — What hardware projects do I have? (5.307s)
  - [FAIL] tu-004 — What's in my hardware inventory? (9.548s)
  - [PASS] tu-005 — Open the knowledge board. (2.124s)
  - [FAIL] vp-001 — Voice subsystem reports a valid state
  - [FAIL] vp-002 — TTS synthesizes short text quickly
  - [PASS] vp-003 — Voice latency metrics endpoint responds
  - [PASS] vp-004 — What time is it? (2.096s)

## Run 2026-07-07 20:06:02

- Silvia reachable: True
- Tests: 1 | Passed: 1 | Failed: 0
- Raw log: `agent/logs/run_20260707_200602.json`
- Report: `agent/reports/latest_failure_report.md`
  - [PASS] vp-001 — Voice subsystem reports a valid state

## Run 2026-07-07 20:09:15

- Silvia reachable: True
- Tests: 25 | Passed: 12 | Failed: 13
- Raw log: `agent/logs/run_20260707_200915.json`
- Report: `agent/reports/latest_failure_report.md`
  - [PASS] hal-001 — What is Project Nebula? (5.79s)
  - [PASS] hal-002 — What is Project Artemis? (9.402s)
  - [FAIL] hal-003 — What is the deadline for Project Nebula? (14.339s)
  - [PASS] hal-004 — What is the current status of Project Zephyr? (2.132s)
  - [FAIL] hal-005 — What did I decide about Project Nebula in my notes? (29.206s)
  - [FAIL] hal-006 — Give me a quick update on Silvia. (2.113s)
  - [FAIL] lat-001 — Hello, are you online? (14.045s)
  - [PASS] lat-002 — What time is it? (2.085s)
  - [PASS] lat-003 — Give me a quick update on Silvia. (2.155s)
  - [PASS] lat-004 — What are my current main projects? (6.088s)
  - [FAIL] og-001 — What are my current main projects? (9.534s)
  - [FAIL] og-002 — What is Silvia supposed to do? (2.167s)
  - [FAIL] og-003 — What is the current status of Silvia? (2.114s)
  - [FAIL] og-004 — What are my robotics projects? (11.226s)
  - [FAIL] og-005 — Summarise what you know about my projects from Obsidian. (14.527s)
  - [FAIL] og-006 — What are my goals for Silvia? (14.716s)
  - [PASS] tu-001 — What time is it? (2.128s)
  - [FAIL] tu-002 — Show chat latency (2.107s)
  - [FAIL] tu-003 — What hardware projects do I have? (10.433s)
  - [FAIL] tu-004 — What's in my hardware inventory? (9.203s)
  - [PASS] tu-005 — Open the knowledge board. (2.098s)
  - [PASS] vp-001 — Voice subsystem reports a valid state
  - [PASS] vp-002 — TTS synthesizes short text quickly
  - [PASS] vp-003 — Voice latency metrics endpoint responds
  - [PASS] vp-004 — What time is it? (2.12s)

## Run 2026-07-07 20:10:12

- Silvia reachable: True
- Tests: 1 | Passed: 1 | Failed: 0
- Raw log: `agent/logs/run_20260707_201012.json`
- Report: `agent/reports/latest_failure_report.md`
  - [PASS] hal-003 — What is the deadline for Project Nebula? (10.749s)

## Run 2026-07-07 20:10:16

- Silvia reachable: True
- Tests: 1 | Passed: 1 | Failed: 0
- Raw log: `agent/logs/run_20260707_201016.json`
- Report: `agent/reports/latest_failure_report.md`
  - [PASS] tu-002 — Show chat latency (2.112s)

## Run 2026-07-07 20:13:18

- Silvia reachable: True
- Tests: 25 | Passed: 14 | Failed: 11
- Raw log: `agent/logs/run_20260707_201318.json`
- Report: `agent/reports/latest_failure_report.md`
  - [PASS] hal-001 — What is Project Nebula? (5.924s)
  - [PASS] hal-002 — What is Project Artemis? (9.455s)
  - [PASS] hal-003 — What is the deadline for Project Nebula? (9.544s)
  - [PASS] hal-004 — What is the current status of Project Zephyr? (2.148s)
  - [FAIL] hal-005 — What did I decide about Project Nebula in my notes? (30.228s)
  - [FAIL] hal-006 — Give me a quick update on Silvia. (2.351s)
  - [FAIL] lat-001 — Hello, are you online? (14.102s)
  - [PASS] lat-002 — What time is it? (2.109s)
  - [PASS] lat-003 — Give me a quick update on Silvia. (2.13s)
  - [PASS] lat-004 — What are my current main projects? (6.296s)
  - [FAIL] og-001 — What are my current main projects? (9.45s)
  - [FAIL] og-002 — What is Silvia supposed to do? (2.122s)
  - [FAIL] og-003 — What is the current status of Silvia? (2.116s)
  - [FAIL] og-004 — What are my robotics projects? (10.561s)
  - [FAIL] og-005 — Summarise what you know about my projects from Obsidian. (9.627s)
  - [FAIL] og-006 — What are my goals for Silvia? (14.598s)
  - [PASS] tu-001 — What time is it? (2.103s)
  - [PASS] tu-002 — Show chat latency (2.1s)
  - [FAIL] tu-003 — What hardware projects do I have? (5.257s)
  - [FAIL] tu-004 — What's in my hardware inventory? (14.235s)
  - [PASS] tu-005 — Open the knowledge board. (2.061s)
  - [PASS] vp-001 — Voice subsystem reports a valid state
  - [PASS] vp-002 — TTS synthesizes short text quickly
  - [PASS] vp-003 — Voice latency metrics endpoint responds
  - [PASS] vp-004 — What time is it? (2.07s)

## Run 2026-07-07 20:24:40

- Silvia reachable: True
- Tests: 25 | Passed: 14 | Failed: 11
- Raw log: `agent/logs/run_20260707_202440.json`
- Report: `agent/reports/latest_failure_report.md`
  - [PASS] hal-001 — What is Project Nebula? (5.528s)
  - [PASS] hal-002 — What is Project Artemis? (9.196s)
  - [PASS] hal-003 — What is the deadline for Project Nebula? (9.395s)
  - [PASS] hal-004 — What is the current status of Project Zephyr? (2.084s)
  - [FAIL] hal-005 — What did I decide about Project Nebula in my notes? (31.536s)
  - [FAIL] hal-006 — Give me a quick update on Silvia. (2.233s)
  - [FAIL] lat-001 — Hello, are you online? (9.753s)
  - [PASS] lat-002 — What time is it? (2.108s)
  - [PASS] lat-003 — Give me a quick update on Silvia. (2.067s)
  - [PASS] lat-004 — What are my current main projects? (10.827s)
  - [FAIL] og-001 — What are my current main projects? (10.004s)
  - [FAIL] og-002 — What is Silvia supposed to do? (2.102s)
  - [FAIL] og-003 — What is the current status of Silvia? (2.057s)
  - [FAIL] og-004 — What are my robotics projects? (6.037s)
  - [FAIL] og-005 — Summarise what you know about my projects from Obsidian. (9.583s)
  - [FAIL] og-006 — What are my goals for Silvia? (15.067s)
  - [PASS] tu-001 — What time is it? (2.064s)
  - [PASS] tu-002 — Show chat latency (2.066s)
  - [FAIL] tu-003 — What hardware projects do I have? (5.25s)
  - [FAIL] tu-004 — What's in my hardware inventory? (9.478s)
  - [PASS] tu-005 — Open the knowledge board. (2.059s)
  - [PASS] vp-001 — Voice subsystem reports a valid state
  - [PASS] vp-002 — TTS synthesizes short text quickly
  - [PASS] vp-003 — Voice latency metrics endpoint responds
  - [PASS] vp-004 — What time is it? (2.08s)

## Run 2026-07-07 20:39:15

- Silvia reachable: True
- Tests: 25 | Passed: 14 | Failed: 11
- Raw log: `agent/logs/run_20260707_203915.json`
- Report: `agent/reports/latest_failure_report.md`
  - [PASS] hal-001 — What is Project Nebula? (6.917s)
  - [PASS] hal-002 — What is Project Artemis? (14.131s)
  - [PASS] hal-003 — What is the deadline for Project Nebula? (9.18s)
  - [PASS] hal-004 — What is the current status of Project Zephyr? (2.067s)
  - [FAIL] hal-005 — What did I decide about Project Nebula in my notes? (34.78s)
  - [FAIL] hal-006 — Give me a quick update on Silvia. (2.188s)
  - [FAIL] lat-001 — Hello, are you online? (9.803s)
  - [PASS] lat-002 — What time is it? (2.108s)
  - [PASS] lat-003 — Give me a quick update on Silvia. (2.084s)
  - [PASS] lat-004 — What are my current main projects? (6.097s)
  - [FAIL] og-001 — What are my current main projects? (14.393s)
  - [FAIL] og-002 — What is Silvia supposed to do? (2.095s)
  - [FAIL] og-003 — What is the current status of Silvia? (2.105s)
  - [FAIL] og-004 — What are my robotics projects? (5.982s)
  - [FAIL] og-005 — Summarise what you know about my projects from Obsidian. (9.737s)
  - [FAIL] og-006 — What are my goals for Silvia? (9.719s)
  - [PASS] tu-001 — What time is it? (2.046s)
  - [PASS] tu-002 — Show chat latency (2.066s)
  - [FAIL] tu-003 — What hardware projects do I have? (5.53s)
  - [FAIL] tu-004 — What's in my hardware inventory? (14.306s)
  - [PASS] tu-005 — Open the knowledge board. (2.184s)
  - [PASS] vp-001 — Voice subsystem reports a valid state
  - [PASS] vp-002 — TTS synthesizes short text quickly
  - [PASS] vp-003 — Voice latency metrics endpoint responds
  - [PASS] vp-004 — What time is it? (2.071s)

## Autopilot run 2026-07-07 20:35:49

- Mode: report-only | Start: 14/25 passed, 11 failed, 7 critical, 7 hallucination, 0 grounded | End: 14/25 passed, 11 failed, 7 critical, 7 hallucination, 0 grounded
- Iterations: 0 | Kept: 0 | Stop: Report-only mode (no repair attempted).
- Report: `agent/reports/autopilot_latest.md`

## Run 2026-07-07 20:43:07

- Silvia reachable: True
- Tests: 25 | Passed: 14 | Failed: 11
- Raw log: `agent/logs/run_20260707_204307.json`
- Report: `agent/reports/latest_failure_report.md`
  - [PASS] hal-001 — What is Project Nebula? (11.47s)
  - [PASS] hal-002 — What is Project Artemis? (9.165s)
  - [PASS] hal-003 — What is the deadline for Project Nebula? (9.332s)
  - [PASS] hal-004 — What is the current status of Project Zephyr? (2.073s)
  - [FAIL] hal-005 — What did I decide about Project Nebula in my notes? (32.166s)
  - [FAIL] hal-006 — Give me a quick update on Silvia. (2.191s)
  - [FAIL] lat-001 — Hello, are you online? (9.514s)
  - [PASS] lat-002 — What time is it? (2.057s)
  - [PASS] lat-003 — Give me a quick update on Silvia. (2.067s)
  - [PASS] lat-004 — What are my current main projects? (6.189s)
  - [FAIL] og-001 — What are my current main projects? (14.467s)
  - [FAIL] og-002 — What is Silvia supposed to do? (2.093s)
  - [FAIL] og-003 — What is the current status of Silvia? (2.124s)
  - [FAIL] og-004 — What are my robotics projects? (5.723s)
  - [FAIL] og-005 — Summarise what you know about my projects from Obsidian. (9.418s)
  - [FAIL] og-006 — What are my goals for Silvia? (14.435s)
  - [PASS] tu-001 — What time is it? (2.091s)
  - [PASS] tu-002 — Show chat latency (2.057s)
  - [FAIL] tu-003 — What hardware projects do I have? (10.217s)
  - [FAIL] tu-004 — What's in my hardware inventory? (9.407s)
  - [PASS] tu-005 — Open the knowledge board. (2.087s)
  - [PASS] vp-001 — Voice subsystem reports a valid state
  - [PASS] vp-002 — TTS synthesizes short text quickly
  - [PASS] vp-003 — Voice latency metrics endpoint responds
  - [PASS] vp-004 — What time is it? (2.073s)

## Autopilot run 2026-07-07 20:39:40

- Mode: auto-repair | Start: 14/25 passed, 11 failed, 7 critical, 7 hallucination, 0 grounded | End: 14/25 passed, 11 failed, 7 critical, 7 hallucination, 0 grounded
- Iterations: 1 | Kept: 0 | Stop: 
- Report: `agent/reports/autopilot_latest.md`

## Run 2026-07-07 21:05:48

- Silvia reachable: True
- Tests: 25 | Passed: 20 | Failed: 5
- Raw log: `agent/logs/run_20260707_210548.json`
- Report: `agent/reports/latest_failure_report.md`
  - [PASS] hal-001 — What is Project Nebula? (6.761s)
  - [PASS] hal-002 — What is Project Artemis? (9.105s)
  - [PASS] hal-003 — What is the deadline for Project Nebula? (9.079s)
  - [PASS] hal-004 — What is the current status of Project Zephyr? (2.079s)
  - [FAIL] hal-005 — What did I decide about Project Nebula in my notes? (31.945s)
  - [PASS] hal-006 — Give me a quick update on Silvia. (2.216s)
  - [PASS] lat-001 — Hello, are you online? (2.058s)
  - [PASS] lat-002 — What time is it? (2.106s)
  - [PASS] lat-003 — Give me a quick update on Silvia. (2.114s)
  - [PASS] lat-004 — What are my current main projects? (10.336s)
  - [FAIL] og-001 — What are my current main projects? (9.483s)
  - [PASS] og-002 — What is Silvia supposed to do? (2.095s)
  - [PASS] og-003 — What is the current status of Silvia? (2.111s)
  - [PASS] og-004 — What are my robotics projects? (2.111s)
  - [FAIL] og-005 — Summarise what you know about my projects from Obsidian. (2.12s)
  - [PASS] og-006 — What are my goals for Silvia? (10.813s)
  - [PASS] tu-001 — What time is it? (2.092s)
  - [PASS] tu-002 — Show chat latency (2.074s)
  - [FAIL] tu-003 — What hardware projects do I have? (10.217s)
  - [FAIL] tu-004 — What's in my hardware inventory? (2.141s)
  - [PASS] tu-005 — Open the knowledge board. (2.106s)
  - [PASS] vp-001 — Voice subsystem reports a valid state
  - [PASS] vp-002 — TTS synthesizes short text quickly
  - [PASS] vp-003 — Voice latency metrics endpoint responds
  - [PASS] vp-004 — What time is it? (2.078s)
