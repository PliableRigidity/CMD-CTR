# Failure Log

Failures appended automatically by `agent/run_tests.py` (one section per run
that had failures). Full detail: `agent/reports/latest_failure_report.md`
and `agent/reports/history/`.

## Run 2026-07-07 19:59:50 — 25 failure(s)

- **hal-001** (hallucination): Transport/server error: silvia_unreachable: backend not running at http://localhost:8000 (start it with: python main.py)
- **hal-002** (hallucination): Transport/server error: silvia_unreachable: backend not running at http://localhost:8000 (start it with: python main.py)
- **hal-003** (hallucination): Transport/server error: silvia_unreachable: backend not running at http://localhost:8000 (start it with: python main.py)
- **hal-004** (hallucination): Transport/server error: silvia_unreachable: backend not running at http://localhost:8000 (start it with: python main.py)
- **hal-005** (hallucination): Transport/server error: silvia_unreachable: backend not running at http://localhost:8000 (start it with: python main.py)
- **hal-006** (hallucination): Transport/server error: silvia_unreachable: backend not running at http://localhost:8000 (start it with: python main.py)
- **lat-001** (latency): Transport/server error: silvia_unreachable: backend not running at http://localhost:8000 (start it with: python main.py)
- **lat-002** (latency): Transport/server error: silvia_unreachable: backend not running at http://localhost:8000 (start it with: python main.py)
- **lat-003** (latency): Transport/server error: silvia_unreachable: backend not running at http://localhost:8000 (start it with: python main.py)
- **lat-004** (latency): Transport/server error: silvia_unreachable: backend not running at http://localhost:8000 (start it with: python main.py)
- **og-001** (obsidian_grounding): Transport/server error: silvia_unreachable: backend not running at http://localhost:8000 (start it with: python main.py)
- **og-002** (obsidian_grounding): Transport/server error: silvia_unreachable: backend not running at http://localhost:8000 (start it with: python main.py)
- **og-003** (obsidian_grounding): Transport/server error: silvia_unreachable: backend not running at http://localhost:8000 (start it with: python main.py)
- **og-004** (obsidian_grounding): Transport/server error: silvia_unreachable: backend not running at http://localhost:8000 (start it with: python main.py)
- **og-005** (obsidian_grounding): Transport/server error: silvia_unreachable: backend not running at http://localhost:8000 (start it with: python main.py)
- **og-006** (obsidian_grounding): Transport/server error: silvia_unreachable: backend not running at http://localhost:8000 (start it with: python main.py)
- **tu-001** (tool_usage): Transport/server error: silvia_unreachable: backend not running at http://localhost:8000 (start it with: python main.py)
- **tu-002** (tool_usage): Transport/server error: silvia_unreachable: backend not running at http://localhost:8000 (start it with: python main.py)
- **tu-003** (tool_usage): Transport/server error: silvia_unreachable: backend not running at http://localhost:8000 (start it with: python main.py)
- **tu-004** (tool_usage): Transport/server error: silvia_unreachable: backend not running at http://localhost:8000 (start it with: python main.py)
- **tu-005** (tool_usage): Transport/server error: silvia_unreachable: backend not running at http://localhost:8000 (start it with: python main.py)
- **vp-001** (voice_pipeline): Transport/server error: silvia_unreachable: backend not running at http://localhost:8000 (start it with: python main.py)
- **vp-002** (voice_pipeline): Transport/server error: silvia_unreachable: backend not running at http://localhost:8000 (start it with: python main.py)
- **vp-003** (voice_pipeline): Transport/server error: silvia_unreachable: backend not running at http://localhost:8000 (start it with: python main.py)
- **vp-004** (voice_pipeline): Transport/server error: silvia_unreachable: backend not running at http://localhost:8000 (start it with: python main.py)

## Run 2026-07-07 20:05:28 — 15 failure(s)

- **hal-003** (hallucination): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.
- **hal-005** (hallucination): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.
- **hal-006** (hallucination): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **lat-001** (latency): Text latency 9.33s exceeds limit 5s.
- **og-001** (obsidian_grounding): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-002** (obsidian_grounding): Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-003** (obsidian_grounding): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-004** (obsidian_grounding): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-005** (obsidian_grounding): Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-006** (obsidian_grounding): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **tu-002** (tool_usage): Answer mentions none of: latency, ms, second.
- **tu-003** (tool_usage): Expected a tool call containing one of ['hardware', 'project']; captured tool calls: none.
- **tu-004** (tool_usage): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Expected a tool call containing one of ['inventory', 'hardware']; captured tool calls: none.
- **vp-001** (voice_pipeline): Unexpected /voice/status body: {'available': True, 'stt_available': True, 'tts_available': True, 'listening': False, 'speaking': False, 'stt_provider': 'faster-whisper (base)', 'tts_provider': 'piper (en-us-ryan-high.onnx)', 'notes': ['STT: Speaches requested but unavailable — Speaches not reachable at http://localhost:8000: <urlopen error timed out>', 'STT: Falling back to local faster-whisper (base)', 'TTS: Piper local — en-us-ryan-high.onnx'], 'speech_enabled': False}
- **vp-002** (voice_pipeline): Speech start 9.58s exceeds limit 5s.

## Run 2026-07-07 20:09:15 — 13 failure(s)

- **hal-003** (hallucination): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.
- **hal-005** (hallucination): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.
- **hal-006** (hallucination): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **lat-001** (latency): Text latency 14.04s exceeds limit 5s.
- **og-001** (obsidian_grounding): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-002** (obsidian_grounding): Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-003** (obsidian_grounding): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-004** (obsidian_grounding): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-005** (obsidian_grounding): Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-006** (obsidian_grounding): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **tu-002** (tool_usage): Answer mentions none of: latency, ms, second.
- **tu-003** (tool_usage): Expected a tool call containing one of ['hardware', 'project']; captured tool calls: none.
- **tu-004** (tool_usage): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Expected a tool call containing one of ['inventory', 'hardware']; captured tool calls: none.

## Run 2026-07-07 20:13:18 — 11 failure(s)

- **hal-005** (hallucination): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.
- **hal-006** (hallucination): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **lat-001** (latency): Text latency 14.10s exceeds limit 5s.
- **og-001** (obsidian_grounding): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-002** (obsidian_grounding): Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-003** (obsidian_grounding): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-004** (obsidian_grounding): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-005** (obsidian_grounding): Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-006** (obsidian_grounding): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **tu-003** (tool_usage): Expected a tool call containing one of ['hardware', 'project']; captured tool calls: none.
- **tu-004** (tool_usage): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Expected a tool call containing one of ['inventory', 'hardware']; captured tool calls: none.

## Run 2026-07-07 20:24:40 — 11 failure(s)

- **hal-005** (hallucination): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.
- **hal-006** (hallucination): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **lat-001** (latency): Text latency 9.75s exceeds limit 5s.
- **og-001** (obsidian_grounding): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-002** (obsidian_grounding): Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-003** (obsidian_grounding): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-004** (obsidian_grounding): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-005** (obsidian_grounding): Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-006** (obsidian_grounding): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **tu-003** (tool_usage): Expected a tool call containing one of ['hardware', 'project']; captured tool calls: none.
- **tu-004** (tool_usage): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Expected a tool call containing one of ['inventory', 'hardware']; captured tool calls: none.

## Run 2026-07-07 20:39:15 — 11 failure(s)

- **hal-005** (hallucination): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.
- **hal-006** (hallucination): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **lat-001** (latency): Text latency 9.80s exceeds limit 5s.
- **og-001** (obsidian_grounding): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-002** (obsidian_grounding): Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-003** (obsidian_grounding): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-004** (obsidian_grounding): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-005** (obsidian_grounding): Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-006** (obsidian_grounding): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **tu-003** (tool_usage): Expected a tool call containing one of ['hardware', 'project']; captured tool calls: none.
- **tu-004** (tool_usage): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Expected a tool call containing one of ['inventory', 'hardware']; captured tool calls: none.

## Autopilot run 2026-07-07 20:35:49 — 11 failure(s) remain

- hal-005 (hallucination)
- hal-006 (hallucination)
- lat-001 (latency)
- og-001 (obsidian_grounding)
- og-002 (obsidian_grounding)
- og-003 (obsidian_grounding)
- og-004 (obsidian_grounding)
- og-005 (obsidian_grounding)
- og-006 (obsidian_grounding)
- tu-003 (tool_usage)
- tu-004 (tool_usage)

## Run 2026-07-07 20:43:07 — 11 failure(s)

- **hal-005** (hallucination): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.
- **hal-006** (hallucination): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **lat-001** (latency): Text latency 9.51s exceeds limit 5s.
- **og-001** (obsidian_grounding): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-002** (obsidian_grounding): Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-003** (obsidian_grounding): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-004** (obsidian_grounding): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-005** (obsidian_grounding): Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-006** (obsidian_grounding): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **tu-003** (tool_usage): Expected a tool call containing one of ['hardware', 'project']; captured tool calls: none.
- **tu-004** (tool_usage): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Expected a tool call containing one of ['inventory', 'hardware']; captured tool calls: none.

## Autopilot run 2026-07-07 20:39:40 — 11 failure(s) remain

- hal-005 (hallucination)
- hal-006 (hallucination)
- lat-001 (latency)
- og-001 (obsidian_grounding)
- og-002 (obsidian_grounding)
- og-003 (obsidian_grounding)
- og-004 (obsidian_grounding)
- og-005 (obsidian_grounding)
- og-006 (obsidian_grounding)
- tu-003 (tool_usage)
- tu-004 (tool_usage)

## Run 2026-07-07 21:05:48 — 5 failure(s)

- **hal-005** (hallucination): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.
- **og-001** (obsidian_grounding): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **og-005** (obsidian_grounding): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **tu-003** (tool_usage): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Expected a tool call containing one of ['hardware', 'project']; captured tool calls: none.
- **tu-004** (tool_usage): No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.; Expected a tool call containing one of ['inventory', 'hardware']; captured tool calls: none.
