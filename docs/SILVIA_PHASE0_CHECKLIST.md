# SILVIA Phase 0 Stabilization Checklist

Use this checklist as the implementation tracker for the Phase 0 audit.

## Safety and Runtime Boundaries

- [x] Bind backend launchers to localhost by default
- [x] Restrict default CORS origins to local development hosts
- [ ] Add explicit auth/capability gating for action and system-control routes
- [ ] Add environment-based production hardening flags

## Core Product Reliability

- [x] Turn the audit report into a tracked stabilization checklist
- [x] Fix decision mode artificial timeout threshold
- [ ] Verify decision mode returns real results across multiple prompts
- [x] Make world events truthful by default instead of returning an empty list
- [ ] Remove or clearly label simulation-only intel in the Intel Board
- [ ] Persist operational event logs if they are part of the product promise

## Conversation Quality

- [x] Route live web/news requests through a conversational answer path
- [x] Make search tool use news providers for news-style queries
- [ ] Audit and refine remaining raw/robotic responses across all tool paths
- [ ] Add regression checks for weather, time, news, and memory phrasing

## Voice Stabilization

- [x] Keep backend TTS/STT round trip operational
- [x] Verify microphone capture to playback in the real browser UI
- [ ] Reduce first-use Whisper latency or preload behavior
- [x] Add clearer user-facing error states for voice failures
- [x] Auto-submit push-to-talk voice input instead of only filling the text box
- [x] Add STT diagnostics for audio size, MIME type, duration, speech detection, raw output, and fallback behavior
- [x] Suppress silence / short hallucination transcripts with a visible `No speech detected` result

## Infrastructure and Data

- [x] Keep node CRUD real and persisted
- [ ] Add schema versioning / migrations for SQLite
- [ ] Separate cosmetic infrastructure panels from live telemetry
- [ ] Implement Tailscale discovery only after trust boundaries are defined
- [x] Add node reachability probes with hostname validation, latency, and last-seen updates

## Frontend Consistency

- [x] Remove direct hardcoded mission API fetch and use shared API client
- [ ] Remove or archive dead frontend modules not used by the main shell
- [ ] Normalize SILVIA naming across visible UI
- [ ] Clean up encoding artifacts in user-visible strings

## Codebase Cleanup

- [ ] Archive or remove legacy `backend/core/`
- [ ] Archive or remove legacy `magi_ui/`
- [ ] Refresh stale migration documentation
- [ ] Produce a final post-stabilization feature status matrix
