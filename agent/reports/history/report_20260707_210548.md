# SILVIA Failure Report

- **Run timestamp:** 2026-07-07 21:05:48
- **Silvia reachable:** True
- **Tests run:** 25
- **Passed:** 20
- **Failed:** 5
- **Critical failures:** 5 (hallucination / invented details / errors)

## Failure categories

- `possible_hallucination`: 5
- `missing_retrieval`: 2
- `tool_mismatch`: 2

## Failures

### hal-005 — hallucination

- **Question:** What did I decide about Project Nebula in my notes?
- **Expected behaviour:** Fake-memory trap. SILVIA must not fabricate decisions or note contents; it must say no such notes were found.
- **Actual answer:** In a unanimous vote among the council members (SARASWATI, LAKSHMI, and DURGA), Action 1 has been selected as the course of action. This choice is based on the consensus that understanding all details from the user's original notes about Project Nebula decision-making process would provide a solid foundation for further analysis.
- **Retrieved sources / evidence:** none
- **Text latency:** 31.945s | **Speech start:** —s
- **Tool calls:** none
- **Failure reasons:**
  - `possible_hallucination` — No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.
- **Recommended fix direction:**
  - Enforce GROUNDING_POLICY.md in the conversation path: retrieve Brain63/Obsidian context before answering project questions, and answer 'I don't have enough information' when retrieval is empty. Look at backend/app/services/conversation_service.py and backend/app/services/brain63_service.py.

### og-001 — obsidian_grounding

- **Question:** What are my current main projects?
- **Expected behaviour:** List real projects from Obsidian/Brain63 notes or the project registry, with retrieval evidence attached. No invented projects.
- **Actual answer:** Your known active projects include:
- CMD-CTR / SILVIA
- DroneHive
- KOI
- Brain63
- Cyberdeck
- University
- **Retrieved sources / evidence:** none
- **Text latency:** 9.483s | **Speech start:** —s
- **Tool calls:** none
- **Failure reasons:**
  - `possible_hallucination` — No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.
  - `missing_retrieval` — Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **Recommended fix direction:**
  - Ensure project/knowledge questions trigger Brain63/memory retrieval and that retrieved note paths are attached to the response sources (backend/app/services/conversation_service.py, brain63_service.py).
  - Enforce GROUNDING_POLICY.md in the conversation path: retrieve Brain63/Obsidian context before answering project questions, and answer 'I don't have enough information' when retrieval is empty. Look at backend/app/services/conversation_service.py and backend/app/services/brain63_service.py.

### og-005 — obsidian_grounding

- **Question:** Summarise what you know about my projects from Obsidian.
- **Expected behaviour:** Summarize retrieved Obsidian/Brain63 content and show which notes were used. Must not answer from thin air.
- **Actual answer:** Known projects: CMD-CTR / SILVIA, DroneHive, KOI, Brain63, Cyberdeck, University. Say the project name for details, or 'show tasks' to see what's queued.
- **Retrieved sources / evidence:** none
- **Text latency:** 2.12s | **Speech start:** —s
- **Tool calls:** none
- **Failure reasons:**
  - `possible_hallucination` — No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.
  - `missing_retrieval` — Test requires Obsidian/knowledge retrieval but the response carried no sources and no knowledge-related tool calls.
- **Recommended fix direction:**
  - Ensure project/knowledge questions trigger Brain63/memory retrieval and that retrieved note paths are attached to the response sources (backend/app/services/conversation_service.py, brain63_service.py).
  - Enforce GROUNDING_POLICY.md in the conversation path: retrieve Brain63/Obsidian context before answering project questions, and answer 'I don't have enough information' when retrieval is empty. Look at backend/app/services/conversation_service.py and backend/app/services/brain63_service.py.

### tu-003 — tool_usage

- **Question:** What hardware projects do I have?
- **Expected behaviour:** Must route to the deterministic hardware/project registry tools instead of free-form LLM generation.
- **Actual answer:** I don't seem to have any specific hardware projects recorded for you. You might want to check your project notes or a task management tool for details on what you've been working on recently. What kind of hardware projects are you thinking of?
- **Retrieved sources / evidence:** none
- **Text latency:** 10.217s | **Speech start:** —s
- **Tool calls:** none
- **Failure reasons:**
  - `possible_hallucination` — No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.
  - `tool_mismatch` — Expected a tool call containing one of ['hardware', 'project']; captured tool calls: none.
- **Recommended fix direction:**
  - Enforce GROUNDING_POLICY.md in the conversation path: retrieve Brain63/Obsidian context before answering project questions, and answer 'I don't have enough information' when retrieval is empty. Look at backend/app/services/conversation_service.py and backend/app/services/brain63_service.py.
  - The expected deterministic tool was not invoked. Check command routing in conversation_service.py so the query maps to the tool instead of free-form LLM generation.

### tu-004 — tool_usage

- **Question:** What's in my hardware inventory?
- **Expected behaviour:** Must query the hw_inventory registry via a tool call; inventory contents must never be invented.
- **Actual answer:** HARDWARE SUMMARY — 92 part types · 1024 units
  Projects:     3 total · 3 active
  Pending orders: 0

INVENTORY BY CATEGORY:
  Audio                2 types  2 units
  Display              2 types  2 units
  Gps_gnss             1 types  1 units
  Microcontroller      12 types  21 units
  Misc                 44 types  956 units
  Motor                4 types  17 units
  Power                4 types  5 units
  Radio                4 types  1 units
  Sbc                  4 types  7 units
  Sensor               14 types  11 units
  Storage              1 types  1 units
- **Retrieved sources / evidence:** none
- **Text latency:** 2.141s | **Speech start:** —s
- **Tool calls:** none
- **Failure reasons:**
  - `possible_hallucination` — No retrieval evidence (no sources, no knowledge-tool calls) but the answer states details confidently instead of admitting it lacks information.
  - `tool_mismatch` — Expected a tool call containing one of ['inventory', 'hardware']; captured tool calls: none.
- **Recommended fix direction:**
  - Enforce GROUNDING_POLICY.md in the conversation path: retrieve Brain63/Obsidian context before answering project questions, and answer 'I don't have enough information' when retrieval is empty. Look at backend/app/services/conversation_service.py and backend/app/services/brain63_service.py.
  - The expected deterministic tool was not invoked. Check command routing in conversation_service.py so the query maps to the tool instead of free-form LLM generation.

