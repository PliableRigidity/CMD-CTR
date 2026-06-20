# Troubleshooting Guide

Common issues, diagnosis steps, and fixes for SILVIA.

---

## Table of Contents

1. [Backend Won't Start](#backend-wont-start)
2. [Frontend Won't Load](#frontend-wont-load)
3. [App Won't Launch (Desktop Awareness)](#app-wont-launch-desktop-awareness)
4. [App Won't Close](#app-wont-close)
5. [Node Shows Offline](#node-shows-offline)
6. [Wake Word Not Triggering](#wake-word-not-triggering)
7. [Voice: STT Returns Garbled Text](#voice-stt-returns-garbled-text)
8. [Voice: No TTS Audio](#voice-no-tts-audio)
9. [Speaches Port Conflict](#speaches-port-conflict)
10. [Inventory Mismatch](#inventory-mismatch)
11. [Project Build Readiness Wrong](#project-build-readiness-wrong)
12. [BOM Import Failures](#bom-import-failures)
13. [Hardware Assistant Routing Issues](#hardware-assistant-routing-issues)
14. [Vision Analysis Not Working](#vision-analysis-not-working)
15. [Ollama Not Available](#ollama-not-available)
16. [Watch Alerts Not Firing](#watch-alerts-not-firing)
17. [SSH Terminal Not Opening](#ssh-terminal-not-opening)

---

## Backend Won't Start

### Symptoms
- `python -m uvicorn backend.main:app` crashes immediately
- `ModuleNotFoundError` or `ImportError`

### Diagnosis

```bash
# Check Python version (need 3.11+)
python --version

# Check all dependencies installed
pip install -r backend/requirements.txt

# Try importing the app
python -c "from backend.main import app; print('OK')"
```

### Common Fixes

**Port 8000 already in use:**
```bash
# Windows
netstat -ano | findstr :8000
taskkill /PID <pid> /F

# Or use a different port
python -m uvicorn backend.main:app --port 8001
```

**Missing `.env` file:**
```bash
cp .env.example .env
# Edit .env with your values
```

**Piper model not found (non-fatal but logged):**
Set `PIPER_MODEL_PATH` in `.env` to a valid `.onnx` file, or leave voice unused.

**Speaches trying to connect to wrong port:**
Set `SPEACHES_URL=http://localhost:9000` (or whatever port Speaches is on).

---

## Frontend Won't Load

### Symptoms
- `http://localhost:5173` shows blank or error
- `npm run dev` fails

### Diagnosis

```bash
cd frontend
node --version   # Need 18+
npm install      # Ensure dependencies are installed
npm run dev      # Look at the output carefully
```

### Common Fixes

**API requests failing (CORS):**
Check `CORS_ALLOW_ORIGINS` in `.env` includes your frontend URL:
```env
CORS_ALLOW_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

**Backend not running:**
The frontend depends on the backend. Start `uvicorn` first.

**Old build artifacts:**
```bash
rm -rf frontend/dist frontend/node_modules/.vite
npm install && npm run dev
```

---

## App Won't Launch (Desktop Awareness)

### Symptoms
- `open VS Code` — "App not found"
- App exists but SILVIA can't find it

### Diagnosis

```
scan installed apps          # Re-scan app registry
show app vs code             # Check what SILVIA has registered
list apps                    # See all discovered apps
```

### Common Fixes

**App not discovered by scan:**

Register it manually:
```
add app VS Code at C:\Users\YourName\AppData\Local\Programs\Microsoft VS Code\Code.exe
```

**Wrong launch candidate:**
```
show app spotify             # See all candidates
prefer spotify web           # or: prefer spotify desktop
```

**App uses different executable:**
```
add app Spotify Desktop at C:\Users\YourName\AppData\Roaming\Spotify\Spotify.exe aliases spotify desktop
```

**Scan didn't pick up custom install location:**
```
add location MySoftware at C:\MyCustomApps
scan installed apps
```

---

## App Won't Close

### Symptoms
- `close VS Code` — "App closed" but it's still visible
- Process terminates but window stays open

### Diagnosis

```
app status VS Code           # Check if process still running
show running apps            # See all running registered apps
```

### Common Fixes

SILVIA sends `WM_CLOSE` (graceful close) and waits 5 seconds. If the app has unsaved changes, it may show a save dialog — SILVIA doesn't handle that.

- **Unsaved files:** Save first, then close
- **App ignores WM_CLOSE:** Some apps (games, media players) need manual close or use `run_command taskkill /IM appname.exe`
- **Multiple instances:** Close all instances manually first

---

## Node Shows Offline

### Symptoms
- Node status = `offline` in Infrastructure Panel
- `status of nighthawk` → offline

### Diagnosis

```
# Check what verification method last worked
status of nighthawk

# Try a fresh verification
verify nighthawk

# Try direct ping
ping <hostname>

# Check if agent is running (if applicable)
curl http://<hostname>:7700/health
```

### Common Fixes

**IP address changed (DHCP):**
```
update nighthawk IP to 192.168.1.55
```
Or configure a static IP / DHCP reservation.

**silvia-agent not running:**
SSH into the node and start silvia-agent.

**Firewall blocking:**
- Allow inbound connections on agent port (default 7700)
- Allow ICMP (ping) if using ping-based verification

**Node on different network:**
For Tailscale networks, ensure SILVIA's machine is also in the Tailscale network.

**Wrong hostname:**
```
update nighthawk IP to nighthawk.local     # mDNS
update nighthawk IP to 100.64.1.5          # Tailscale IP
```

---

## Wake Word Not Triggering

### Symptoms
- Saying "Hey SILVIA" does nothing
- Voice indicator in UI never activates

### Diagnosis

```bash
# Check voice system status
curl http://localhost:8000/api/voice/diagnostics

# Check VAD is loaded
curl http://localhost:8000/api/voice/status
```

### Common Fixes

**No microphone / wrong device:**
- Check Windows sound settings → Recording devices
- Set correct microphone as default
- Restart the backend after changing audio device

**Wake word model not loaded:**
Check startup logs for `WakeWordDetector ready` line. If missing, check `backend/voice/wakeword/` directory exists.

**Background noise too high:**
Wake word has threshold 0.50. High background noise can mask it. Move to a quieter environment or speak more clearly.

**VAD is filtering voice frames:**
If VAD confidence is too aggressive, it may filter your speech before it reaches the wake word detector. Check diagnostics output.

---

## Voice: STT Returns Garbled Text

### Symptoms
- Transcription is wrong or nonsensical
- Commands not recognized after speaking

### Diagnosis

```bash
# Check which STT is active
curl http://localhost:8000/api/voice/status
# → { "stt_provider": "speaches" | "local" }
```

### Common Fixes

**Using local Whisper — try a larger model:**
```env
WHISPER_MODEL_SIZE=small   # or medium, large
```
Restart backend after changing.

**Using Speaches — check it's working:**
```bash
curl http://localhost:9000/v1/models
```
If Speaches is unreachable, SILVIA falls back to local Whisper automatically.

**Microphone gain too low:**
Increase microphone volume in Windows Sound settings.

**Non-English speech:**
By default, Whisper uses `language=None` (auto-detect). If using a language-specific Speaches model, it may not handle your language.

---

## Voice: No TTS Audio

### Symptoms
- SILVIA responds in text but no audio plays
- "Audio unavailable" in UI

### Diagnosis

```bash
# Check TTS provider
curl http://localhost:8000/api/voice/status
# → { "tts_provider": "speaches" | "piper" }
```

### Common Fixes

**Speakers not connected / wrong output device:**
Check Windows sound settings → Playback devices.

**Piper model file missing:**
```env
PIPER_MODEL_PATH=C:\Piper\models\en-us-ryan-high.onnx
```
Download from [Piper releases](https://github.com/rhasspy/piper/releases).

**Speaches TTS not loaded:**
Check Speaches logs — the TTS model may have failed to load.

**Browser blocking audio autoplay:**
The frontend plays TTS via HTML Audio element. Some browsers block autoplay. Click anywhere in the page first to unblock audio context.

---

## Speaches Port Conflict

### Symptoms
- Backend fails to start on port 8000
- "Address already in use"
- Or: Speaches failing to start because SILVIA is on 8000

### Fix

Speaches defaults to port 8000 (same as SILVIA). Change Speaches to use port 9000:

In your Speaches `docker-compose.yml`:
```yaml
services:
  speaches:
    ports:
      - "9000:8000"   # Host:Container
```

Then configure SILVIA:
```env
SPEACHES_URL=http://localhost:9000
```

---

## Inventory Mismatch

### Symptoms
- Part quantity doesn't match what you actually have
- `show ESP32-S3` shows wrong count

### Diagnosis

```
show ESP32-S3
how many ESP32-S3 do I have
show inventory
```

### Common Fixes

**Received order but inventory not updated:**
```
mark order ESP32-S3 delivered
```
Or use the ✓ button in the Procurement → Active Orders panel.

**Added to wrong part entry (fuzzy match hit wrong part):**
Check inventory for duplicate/similar entries:
```
show all microcontrollers
```
If there's a duplicate, remove 1 ESP32-S3 from the wrong entry:
```
remove 5 ESP32-S3           # adjust down if over-counted
```

**Manual quantity correction:**
Use the edit button in the Inventory panel to directly set quantity.

---

## Project Build Readiness Wrong

### Symptoms
- `can I build DroneHive` says missing parts that you have in stock
- Readiness shows 0% despite having all parts

### Diagnosis

```
show project DroneHive          # See what parts are linked
show DroneHive requirements     # See required quantities
show inventory                  # See what you actually have
```

### Common Fixes

**Part name in project requirements doesn't match inventory name:**

Example: project requires "ESP32-S3-DevKitC-1" but inventory has "ESP32-S3".

The fuzzy matcher should catch this, but if it doesn't, fix by ensuring names are consistent. Either:
- Edit the part name in inventory to match
- Or re-add the requirement using the exact inventory name

**No requirements set:**
```
DroneHive requires:
3 ESP32-S3
2 MPU6050
```

**Part in requirements is not linked to any inventory entry:**
The `_show_project` output will show `have: 0` for the part. This means no inventory part was matched. Check part naming.

---

## BOM Import Failures

### Symptoms
- `import BOM /path/to/bom.csv` → error
- Parts imported with wrong quantities

### Diagnosis

```
show imports          # See recent import history
```

### Common Fixes

**File not found:**
Use absolute path:
```
import BOM C:\Users\YourName\Projects\DroneHive\bom.csv
```

**CSV format not recognized:**
SILVIA auto-detects columns. If detection fails, ensure the CSV has at least one of:
- `Quantity` or `Qty` column
- `Part`, `Component`, or `Designator` column
- `Manufacturer Part Number` or `MPN` column

**All quantities imported as 1:**
The CSV may be a reference BOM (one entry per component type) rather than a quantity BOM. Edit the `quantity_required` on the project-part links after import.

**UTF-8 encoding issues:**
Save the CSV as UTF-8 (Excel: Save As → CSV UTF-8).

---

## Hardware Assistant Routing Issues

### Symptoms
- "show projects" returns inventory results
- "can I build rover" returns help message
- Commands routed to wrong handler

### Diagnosis

The Hardware Assistant uses regex routing. If a command is misrouted, the pattern didn't match.

Try more explicit phrasing:
```
list all hardware projects       # instead of "show projects"
can I build the rover project    # more explicit
hardware requirements for rover  # explicit "requirements for" prefix
```

### Common Fixes

**"show projects" hits inventory search:**
This was a known Phase 12D bug — should be fixed. If it recurs, the catch-all `^show\s+` pattern fired before the project listing route. Check `handle()` in `hardware_assistant_service.py` — project routes must appear before the catch-all.

**New command not routing:**
Add a new route pattern to `handle()` before the `^show\s+` catch-all. See [DeveloperGuide.md](DeveloperGuide.md#adding-a-hardware-assistant-command).

**Confirm/cancel loop stuck:**
If you're stuck in a pending action, type `cancel` to clear it.

---

## Vision Analysis Not Working

### Symptoms
- `vision status` shows "NOT READY"
- Image upload returns error
- Detections are empty

### Diagnosis

```
vision status          # In Hardware Assistant chat
```

Or check the API:
```bash
curl http://localhost:8000/api/hardware/vision/status
```

### Common Fixes

**Provider: anthropic — SDK not installed:**
```bash
pip install anthropic>=0.50.0
```
Then restart the backend.

**Provider: anthropic — no API key:**
```env
ANTHROPIC_API_KEY=sk-ant-your-key-here
```
Restart backend.

**Provider: ollama — model not pulled:**
```bash
ollama pull llava
```
Then retry. The first pull can take a few minutes.

**Ollama not running:**
```bash
ollama serve
```

**Low confidence detections:**
All detections were below the 0.65 threshold. Try:
- Better lighting in the photo
- Closer shot showing component markings clearly
- Different angle to reduce glare

**Image too large:**
Maximum 20 MB. Resize the image before uploading.

**Provider auto-selection picking Ollama instead of Anthropic:**
Check that `ANTHROPIC_API_KEY` is set in `.env` AND `anthropic` SDK is installed:
```bash
python -c "import anthropic; print('OK')"
```
If this fails, install the SDK.

---

## Ollama Not Available

### Symptoms
- All SILVIA responses are empty or timeout
- "Ollama connection refused" in logs

### Fix

```bash
# Start Ollama
ollama serve

# Verify it's running
curl http://localhost:11434/api/tags
```

If Ollama crashes repeatedly, check:
- Available RAM (phi4-mini-reasoning needs ~4GB, gemma3:4b ~4GB)
- Disk space for model files
- CUDA driver version if using GPU

SILVIA degrades gracefully when Ollama is down — tool routing still works via regex fallback, but LLM responses won't be generated.

---

## Watch Alerts Not Firing

### Symptoms
- CPU is at 95% on a node but no alert appears

### Diagnosis

```
show alerts              # Any active alerts?
watch officer status     # Same
```

### Common Fixes

**Node has no silvia-agent:**
Passive nodes don't send telemetry. Watch rules only fire on telemetry-bearing nodes (agent nodes).

**Telemetry not updating:**
Check the backend is polling the agent:
```bash
curl http://localhost:8000/api/nodes
# → check last_seen timestamp
```

If `last_seen` is stale, the background poll loop may have stopped. Restart the backend.

**Severity below notification threshold:**
Alerts are shown in the UI regardless of `NOTIFICATION_MIN_SEVERITY`. If you expect a Discord notification but it's not arriving, check `NOTIFICATION_MIN_SEVERITY` and `NOTIFICATION_WEBHOOK_URL` in `.env`.

---

## SSH Terminal Not Opening

### Symptoms
- `connect carrera` — no terminal opens
- Windows Terminal doesn't launch

### Diagnosis

```bash
# Check wt.exe is available
where wt
# Should return: C:\Windows\System32\wt.exe (or similar)
```

### Common Fixes

**Windows Terminal not installed:**
Install from Microsoft Store: `Windows Terminal`.

**No hostname/IP on the node:**
```
update carrera IP to 192.168.1.50
```

**No SSH profile set:**
SILVIA will ask for username on first connect. Or pre-configure:
```
set ssh username for carrera to ishaan
```

**SSH not configured on the target machine:**
Ensure the target has an SSH server running (OpenSSH on Linux/Windows).

**Key-based auth failing:**
```
set carrera ssh key to C:\Users\YourName\.ssh\id_ed25519
```
Ensure the public key is in `~/.ssh/authorized_keys` on the target.

---

## Still Stuck?

1. Check backend logs — the most verbose diagnostics are there
2. Check browser console for frontend errors (`F12 → Console`)
3. Restart the backend (`Ctrl+C`, then re-run uvicorn)
4. Check `.env` is correctly configured and loaded (add `print(os.getenv("YOUR_VAR"))` temporarily in `config.py`)

---

## Related Documentation

- [VoiceSystem.md](VoiceSystem.md) — Voice pipeline details
- [Infrastructure.md](Infrastructure.md) — Node and telemetry details
- [HardwareAssistant.md](HardwareAssistant.md) — Hardware Assistant routing
- [DeveloperGuide.md](DeveloperGuide.md) — How to extend and debug
