# Voice System

SILVIA's voice pipeline turns spoken words into actions and speaks responses back — entirely locally. No audio ever leaves your machine.

---

## Table of Contents

1. [Pipeline Overview](#pipeline-overview)
2. [Wake Word Detection](#wake-word-detection)
3. [Speech-to-Text (STT)](#speech-to-text-stt)
4. [Text-to-Speech (TTS)](#text-to-speech-tts)
5. [Voice Activity Detection (VAD)](#voice-activity-detection-vad)
6. [Provider Configuration](#provider-configuration)
7. [Voice Commands](#voice-commands)
8. [WebSocket Protocol](#websocket-protocol)
9. [Troubleshooting](#troubleshooting)

---

## Pipeline Overview

```
Microphone
    │
    ▼
┌──────────────────┐
│  Wake Word       │  "Hey SILVIA" detected
│  Detector        │  (Silero VAD + custom model)
└────────┬─────────┘
         │ wakeword event
         ▼
┌──────────────────┐
│  VAD             │  Detect speech start and end
│  (Silero)        │  Buffer audio frames
└────────┬─────────┘
         │ audio buffer (WAV)
         ▼
┌──────────────────┐
│  STT             │  Transcribe speech to text
│  Whisper/Speaches│
└────────┬─────────┘
         │ transcript
         ▼
┌──────────────────┐
│  SILVIA          │  Process command, call tools
│  (gemma3:4b)     │
└────────┬─────────┘
         │ response text
         ▼
┌──────────────────┐
│  TTS             │  Synthesize speech
│  Kokoro/Piper    │
└────────┬─────────┘
         │ audio stream
         ▼
    Speakers
```

Total latency: typically 1.5–4 seconds from end of speech to first spoken word of response.

---

## Wake Word Detection

Wake word: **"Hey SILVIA"**

### How It Works

1. Continuous audio monitoring via `sounddevice`
2. Silero VAD filters non-speech frames
3. Custom wake word model (`hey_silvia`) classifies speech frames
4. Detection threshold: 0.50 (configurable)
5. On detection: emits `wake_word_detected` event → frontend activates listening indicator

### Wake Word Files

- Model: `backend/voice/wakeword/` directory
- Powered by OpenWakeWord or custom ONNX model
- Pre-warmed at startup to avoid first-detection latency

### Configuration

```env
# No env var needed — wake word is always "Hey SILVIA"
# Threshold can be adjusted in config.py:
# WAKE_WORD_THRESHOLD = 0.50
```

---

## Speech-to-Text (STT)

Two providers supported, selected automatically:

### Speaches (Preferred)

[Speaches](https://github.com/speaches-ai/speaches) is an OpenAI-compatible local STT/TTS server. When `SPEACHES_URL` is configured and reachable, SILVIA uses it.

```env
SPEACHES_URL=http://localhost:9000
SPEACHES_STT_MODEL=rtlingo/mobiuslabsgmbh-faster-whisper-large-v3-turbo
```

**Port note:** Speaches defaults to port 8000, which conflicts with SILVIA. Configure Speaches docker-compose to expose on port 9000: `"9000:8000"`.

### Local Whisper (Fallback)

If Speaches is unreachable, SILVIA falls back to local [faster-whisper](https://github.com/guillaumekln/faster-whisper):

```env
WHISPER_MODEL_SIZE=base  # tiny | base | small | medium | large
```

Supported models: `tiny`, `base`, `small`, `medium`, `large-v2`, `large-v3`

**Accuracy vs speed trade-off:**
- `tiny`: ~1s transcription, lower accuracy
- `base`: ~2s, good for clear speech
- `small`: ~3s, better accuracy
- `large-v3`: ~8s, best accuracy

---

## Text-to-Speech (TTS)

Two providers supported:

### Speaches / Kokoro (Preferred)

When Speaches is configured, SILVIA uses [Kokoro-82M](https://github.com/remsky/Kokoro-FastAPI) via the OpenAI-compatible TTS API.

```env
SPEACHES_TTS_MODEL=speaches-ai/Kokoro-82M-v1.0-ONNX
SPEACHES_TTS_VOICE=af_aoede
```

Available voices include: `af_aoede`, `af_bella`, `am_adam`, and more.

### Local Piper (Fallback)

If Speaches is unreachable, SILVIA uses [Piper TTS](https://github.com/rhasspy/piper):

```env
PIPER_MODEL_PATH=C:\Piper\models\en-us-ryan-high.onnx
PIPER_CONFIG_PATH=   # Auto-detected from model path if empty
PIPER_USE_CUDA=false
```

Install Piper: download binary from [Piper releases](https://github.com/rhasspy/piper/releases) or `pip install piper-tts`.

---

## Voice Activity Detection (VAD)

SILVIA uses **Silero VAD** (ONNX model) to:

1. Filter silence and background noise before wake word detection
2. Detect start of speech after wake word fires
3. Detect end of speech (pause detection) to know when the user has finished

```env
# No special config needed — Silero VAD is always active
# Model is included in the backend/voice/ directory
```

VAD parameters (in code, not `.env`):
- Sample rate: 16000 Hz
- Frame size: 512 samples
- Threshold: 0.5 (speech / silence boundary)

---

## Provider Configuration

SILVIA selects providers at startup:

```
1. Check SPEACHES_URL is set
2. Try GET {SPEACHES_URL}/v1/models with timeout 5s
3. If reachable → use Speaches for STT + TTS
4. If not reachable → use local Whisper (STT) + Piper (TTS)
```

Check current provider status:

```bash
curl http://localhost:8000/api/voice/status
```

Response:
```json
{
  "stt_provider": "speaches",
  "tts_provider": "speaches",
  "stt_available": true,
  "tts_available": true,
  "speaches_url": "http://localhost:9000",
  "whisper_model": "base",
  "piper_model": "C:\\Piper\\models\\en-us-ryan-high.onnx"
}
```

---

## Voice Commands

Every SILVIA command works by voice. Speak naturally after "Hey SILVIA":

```
Hey SILVIA, what time is it?
Hey SILVIA, what's the weather in London?
Hey SILVIA, show nighthawk telemetry
Hey SILVIA, open VS Code
Hey SILVIA, add task finish DroneHive PCB
Hey SILVIA, morning briefing
```

### Voice Loop Flow

```
Hey SILVIA         → wake word detected
[listening tone]   → VAD starts buffering
"what time is it?" → VAD detects end of speech
[processing...]    → STT transcribes → LLM responds → TTS synthesizes
"It's 3:24 PM IST" → audio plays through speakers
```

### Stop / Interrupt

There is no hardcoded stop command. The VAD will time out after ~2 seconds of silence. To interrupt a long response, navigate away from the voice interface in the frontend.

---

## WebSocket Protocol

The frontend communicates with the voice pipeline via WebSocket at `ws://HOST:8000/api/ws/events`.

Relevant voice events:

```json
// Wake word detected
{"type": "wake_word_detected", "timestamp": "..."}

// Transcription complete
{"type": "voice_transcript", "text": "what time is it", "timestamp": "..."}

// Assistant response ready
{"type": "voice_response", "text": "It is 3:24 PM IST", "timestamp": "..."}

// TTS audio ready (streamed or URL)
{"type": "voice_audio", "audio_url": "/api/voice/audio/abc123.wav"}
```

The wake word WebSocket is at `ws://HOST:8000/api/ws/wake` and streams wake detection events separately.

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `GET /api/voice/status` | GET | Provider status and availability |
| `GET /api/voice/diagnostics` | GET | Detailed STT/TTS diagnostics |
| `POST /api/voice/transcribe` | POST | Transcribe audio file (multipart) |
| `POST /api/voice/synthesize` | POST | Synthesize text to audio |
| `WebSocket /api/ws/events` | WS | Main event stream |
| `WebSocket /api/ws/wake` | WS | Wake word event stream |

---

## Troubleshooting

### Wake word not triggering

1. Check microphone is set as default audio input
2. Check Silero VAD is available: `GET /api/voice/diagnostics` → `vad_available: true`
3. Speak more clearly — wake word model requires reasonably clear pronunciation
4. Reduce background noise

### STT returns garbled text

1. If using Speaches: check `SPEACHES_URL` is reachable: `curl http://localhost:9000/v1/models`
2. If using local Whisper: try a larger model (`WHISPER_MODEL_SIZE=small`)
3. Ensure sample rate matches (16 kHz expected)

### TTS not playing

1. Check speakers/headphones are connected and set as default audio output
2. If using Speaches: verify it's running and TTS model is loaded
3. If using Piper: verify `PIPER_MODEL_PATH` points to a valid `.onnx` file
4. Check frontend audio permissions (browser must allow audio playback)

### Speaches port conflict

Speaches defaults to port 8000. SILVIA also uses 8000. Fix in Speaches `docker-compose.yml`:
```yaml
ports:
  - "9000:8000"    # Expose on 9000 instead
```
Then set `SPEACHES_URL=http://localhost:9000`.

---

## Related Documentation

- [Troubleshooting.md](Troubleshooting.md) — Voice-specific issue fixes
- [Architecture.md](ARCHITECTURE.md) — System overview
