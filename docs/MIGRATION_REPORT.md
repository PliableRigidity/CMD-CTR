# Migration Report

## Summary

This repository was migrated from a MAGI-first decision demo into a modular personal assistant platform with:

- a new primary frontend command-center shell in `frontend/`
- a new modular backend under `backend/app/`
- the preserved MAGI pipeline reframed as the Decision Engine
- separated Conversation Mode and Decision Mode
- scaffolded devices, actions, world, maps, and voice services

## New Default Entrypoints

- Backend: `backend/app/main.py`
- Compatibility backend entrypoint: `backend/main.py`
- Root launcher: `main.py`
- Frontend: `frontend/src/main.jsx`

## Reused Files

These were preserved and integrated into Decision Mode:

- `backend/modes/decision/action_generator.py`
- `backend/modes/decision/debate.py`
- `backend/modes/decision/models.py`
- `backend/modes/decision/orchestrator.py`
- `backend/modes/decision/schemas.py`
- `backend/modes/decision/voting.py`
- `backend/modes/decision/world_model.py`
- `backend/modes/decision/prompts/*`
- `backend/config.py`
- `backend/utils/errors.py`
- `backend/utils/logger.py`

## Refactored Files

- `main.py`
- `backend/main.py`
- `frontend/src/App.jsx`
- `frontend/src/main.jsx`
- `frontend/src/styles.css`

## Replaced As Primary UI

These remain in the repo as legacy reference components but are no longer the main app shell:

- `frontend/src/components/DecisionForm.jsx`
- `frontend/src/components/BrainPanel.jsx`
- `frontend/src/components/ActionsList.jsx`
- `frontend/src/components/FinalDecisionCard.jsx`
- `frontend/src/components/SituationCard.jsx`

## Deprecated

- `magi_ui/` as a primary frontend
- the old decision-first `frontend/` root experience
- the monolithic backend shape centered around `backend/main.py`

## New Files Created

### Backend

- `backend/app/__init__.py`
- `backend/app/main.py`
- `backend/app/core/__init__.py`
- `backend/app/core/application.py`
- `backend/app/api/__init__.py`
- `backend/app/api/deps.py`
- `backend/app/api/assistant.py`
- `backend/app/api/decision.py`
- `backend/app/api/mode.py`
- `backend/app/api/actions.py`
- `backend/app/api/devices.py`
- `backend/app/api/world.py`
- `backend/app/api/maps.py`
- `backend/app/api/voice.py`
- `backend/app/models/__init__.py`
- `backend/app/models/assistant.py`
- `backend/app/models/actions.py`
- `backend/app/models/devices.py`
- `backend/app/models/world.py`
- `backend/app/models/maps.py`
- `backend/app/models/voice.py`
- `backend/app/orchestration/__init__.py`
- `backend/app/orchestration/assistant_router.py`
- `backend/app/services/__init__.py`
- `backend/app/services/conversation_service.py`
- `backend/app/services/decision_service.py`
- `backend/app/services/action_service.py`
- `backend/app/services/device_manager.py`
- `backend/app/services/world_events_service.py`
- `backend/app/services/maps_service.py`
- `backend/app/services/voice_service.py`

### Frontend

- `frontend/src/lib/api.js`
- `frontend/src/hooks/useCommandCenterData.js`
- `frontend/src/pages/CommandCenterPage.jsx`
- `frontend/src/app/AppShell.jsx`
- `frontend/src/components/shell/TopBar.jsx`
- `frontend/src/components/chat/ConversationPanel.jsx`
- `frontend/src/components/agents/DecisionEnginePanel.jsx`
- `frontend/src/components/dashboard/EventsStreamPanel.jsx`
- `frontend/src/components/world/WorldEventsPanel.jsx`
- `frontend/src/components/maps/NavigationPanel.jsx`
- `frontend/src/components/devices/DevicesPanel.jsx`
- `frontend/src/components/actions/ActionShortcutsPanel.jsx`
- `frontend/src/components/voice/VoiceStatusPill.jsx`

## Backend Route Inventory

- `POST /api/chat`
- `POST /api/decision`
- `GET /api/mode`
- `POST /api/mode`
- `GET /api/actions`
- `POST /api/actions/open-app`
- `POST /api/actions/open-url`
- `GET /api/devices`
- `GET /api/world/events`
- `POST /api/maps/route`
- `GET /api/voice/status`

## Architecture Outcome

### Conversation Mode

- routed through `ConversationService`
- direct single-model path with local fallback behavior

### Decision Mode

- routed through `DecisionService`
- preserves the old MAGI debate pipeline
- exposed as a subsystem rather than the whole product

### Shared Assistant Platform

- `AssistantPlatformRouter` selects or applies mode
- device, action, world, map, and voice services are available through separate route modules

## Verification Targets

The intended verification is:

- backend imports and starts via `backend.app.main:app`
- frontend builds from `frontend/`
- the main frontend route now renders the command center shell
- `magi_ui/` is not needed for the primary app path
