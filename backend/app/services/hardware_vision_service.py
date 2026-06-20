"""Vision-assisted hardware component detection (Phase 12F).

Providers
---------
  ollama    — local Ollama vision model (default)
  anthropic — Claude Vision via API key + SDK

Ollama model fallback chain (tried in order)
--------------------------------------------
  1. VISION_MODEL         (default: gemma4:e4b)
  2. VISION_FALLBACK_MODEL (default: gemma4:e2b)
  3. VISION_LEGACY_FALLBACK (default: llava:latest)

Image preprocessing
-------------------
  Pillow normalises uploads to JPEG, strips metadata, and resizes oversized images
  so local models don't hit context-window limits.  If Pillow is not installed the
  raw bytes are forwarded as-is and a warning is logged.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import re
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ── Optional dependencies ─────────────────────────────────────────────────────

try:
    from PIL import Image as _PilImage
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False
    logger.warning("[Vision] Pillow not installed — image preprocessing disabled. "
                   "Run: pip install Pillow>=10.0.0")

try:
    import anthropic as _anthropic_sdk
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

from backend.app.services.hardware_category_classifier import classify_component, should_apply_classification
from backend.app.services.hardware_service import HardwareService, _status_for_quantity

# ── Prompt ────────────────────────────────────────────────────────────────────
#
# Evidence-first design: force the model to describe what it sees BEFORE naming
# anything.  This prevents it from copying placeholder text or hallucinating
# model names it cannot actually read in the image.
#
_VISION_PROMPT = """You are an electronics inventory vision classifier.
Analyze the image carefully.

Step 1: Describe only visible evidence (colours, shapes, markings, package style).
Step 2: Identify the broad component type based solely on that evidence.
Step 3: Identify a specific model only if readable markings or unmistakable board layout prove it.
Step 4: Return strict JSON only — no prose, no markdown fences.

Rules:
- Never guess exact model names.
- Never copy text from these instructions into the output.
- Never output "ESP32-S3" unless the image clearly shows an ESP32-S3 module/board with readable ESP32-S3 marking.
- For resistors, capacitors, LEDs, switches, wires, connectors, headers, and small passive parts: use generic names (e.g. "axial resistor", "ceramic capacitor") unless markings are visible.
- If uncertain about type, return component_name "unknown_component" with confidence 0.1.
- Do not include markdown code blocks.

Output format — replace all values with actual observations:
{
  "items": [
    {
      "component_name": "",
      "component_type": "resistor|capacitor|led|switch|connector|wire|microcontroller|sbc|sensor|display|radio|motor|power|storage|pcb|module|misc|unknown",
      "category": "passive_component|microcontroller|sbc|sensor|display|radio|motor|power|audio|storage|pcb|module|misc",
      "quantity": 1,
      "confidence": 0.0,
      "visual_evidence": "",
      "specific_model_visible": false
    }
  ],
  "scene_description": "",
  "image_quality": "good|poor|unclear"
}"""

# ── Placeholder / hallucination detection ────────────────────────────────────

_PLACEHOLDER_PATTERNS = [
    "e.g.",
    "specific model name",
    "generic or specific name",
    "replace all values",
    "example",
    "fill in",
    "your component",
    "component_name",   # raw field name leaked into value
    "visual_evidence",
    "<string>",
    "<number>",
]

# Evidence keywords for classification guards
_PASSIVE_EVIDENCE_KW = frozenset({
    "colour band", "color band", "axial lead", "axial body",
    "striped band", "banded ring", "cylindrical body",
    "ceramic disc", "electrolytic", "bipolar", "diode body",
    "resistor", "capacitor", "inductor",
})
_MCU_EVIDENCE_KW = frozenset({
    "pcb", "esp", "stm32", "arduino", "usb port", "usb-c", "micro usb",
    "pin header", "marking", "silkscreen", "smd ic", "qfp", "sot-23",
    "dip package", "ic chip", "antenna", "module board",
})

# Map model's component_type → our inventory category when category field is absent/wrong
_TYPE_TO_CATEGORY: dict[str, str] = {
    "resistor":       "passive_component",
    "capacitor":      "passive_component",
    "led":            "passive_component",
    "switch":         "passive_component",
    "connector":      "misc",
    "wire":           "misc",
    "microcontroller": "microcontroller",
    "sbc":            "sbc",
    "sensor":         "sensor",
    "display":        "display",
    "radio":          "radio",
    "motor":          "motor",
    "power":          "power",
    "audio":          "audio",
    "storage":        "storage",
    "pcb":            "pcb",
    "module":         "module",
    "misc":           "misc",
    "unknown":        "misc",
}


class HardwareVisionService:
    """Vision-assisted inventory analysis via Gemma 4 / llava / Claude Vision."""

    def __init__(self, hardware: HardwareService | None = None) -> None:
        self.hardware = hardware or HardwareService()

    # ── Public API ─────────────────────────────────────────────────────────────

    def analyze_image(self, image_bytes: bytes, media_type: str = "image/jpeg",
                      filename: str = "") -> dict:
        """Analyze an uploaded image and return detected components."""
        from backend.config import (
            ANTHROPIC_API_KEY, VISION_MODEL_OLLAMA, VISION_MODEL_ANTHROPIC,
            VISION_PROVIDER, VISION_CONFIDENCE_THRESHOLD,
        )

        logger.info(
            "[Vision] analyze_image: filename=%r mime=%s size=%d bytes",
            filename or "(no name)", media_type, len(image_bytes),
        )

        if not image_bytes:
            return self._error("No image data received from upload")

        # ── Preprocess ──
        image_bytes, media_type = self._preprocess_image(image_bytes, media_type)

        # ── Base64 ──
        try:
            image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
            logger.info("[Vision] base64 encoded OK: %d chars", len(image_b64))
        except Exception as exc:
            logger.error("[Vision] base64 encoding failed: %s", exc)
            return self._error(f"Image encoding failed: {exc}")

        provider = self._resolve_provider(VISION_PROVIDER, ANTHROPIC_API_KEY)
        logger.info("[Vision] provider=%s", provider)

        # ── Call provider ──
        if provider == "anthropic":
            if not _ANTHROPIC_AVAILABLE:
                return self._error(
                    "Anthropic SDK not installed. Run: pip install anthropic>=0.50.0",
                    hint="pip install anthropic>=0.50.0",
                )
            if not ANTHROPIC_API_KEY:
                return self._error(
                    "ANTHROPIC_API_KEY not set in .env",
                    hint="Add ANTHROPIC_API_KEY=sk-ant-... to .env",
                )
            raw = self._call_anthropic(image_b64, media_type, ANTHROPIC_API_KEY,
                                       VISION_MODEL_ANTHROPIC)
        else:
            raw = self._call_ollama(image_b64)

        if not raw.get("ok"):
            logger.warning("[Vision] provider call failed: %s", raw.get("error"))
            return raw

        model_used = raw.get("model_used", VISION_MODEL_OLLAMA)
        logger.info("[Vision] model_used=%s endpoint=%s", model_used, raw.get("endpoint", "?"))

        detections = self._parse_detections(raw.get("text", ""))
        logger.info("[Vision] parsed %d valid detections after guards", len(detections))
        detections = self._enrich_detections(detections)

        threshold = VISION_CONFIDENCE_THRESHOLD
        high = [d for d in detections if d["confidence"] >= threshold]
        low  = [d for d in detections if d["confidence"] < threshold]

        return {
            "ok": True,
            "provider": provider,
            "model_used": model_used,
            "detections": detections,
            "high_confidence": high,
            "low_confidence": low,
            "confidence_threshold": threshold,
            "scene_description": raw.get("scene_description", ""),
            "image_quality": raw.get("image_quality", "good"),
            "total_detected": len(detections),
        }

    def apply_detections(self, detections: list[dict]) -> list[dict]:
        """Commit approved detections to inventory."""
        results = []
        for det in detections:
            name      = str(det.get("name", "")).strip()
            qty       = max(1, int(det.get("quantity", 1)))
            category  = str(det.get("category", "misc")).lower()
            sub       = str(det.get("subcategory", "")).lower()
            notes     = str(det.get("notes", ""))

            if not name:
                continue

            existing = self.hardware.find_part_smart(name)
            if existing:
                new_qty = int(existing["quantity"]) + qty
                updated = self.hardware.update_part(
                    existing["id"],
                    quantity=new_qty,
                    status=_status_for_quantity(new_qty),
                ) or existing
                results.append({
                    "action": "updated",
                    "name": name,
                    "quantity_added": qty,
                    "previous_qty": int(existing["quantity"]),
                    "new_qty": new_qty,
                    "part": updated,
                })
            else:
                created = self.hardware.add_part(
                    name, quantity=qty, category=category, subcategory=sub,
                    notes=f"Added via SILVIA Vision{(': ' + notes) if notes else ''}",
                    status=_status_for_quantity(qty),
                )
                results.append({
                    "action": "created",
                    "name": name,
                    "quantity_added": qty,
                    "previous_qty": 0,
                    "new_qty": qty,
                    "part": created,
                })
        return results

    def status(self) -> dict:
        from backend.config import (
            ANTHROPIC_API_KEY, VISION_PROVIDER, VISION_MODEL_OLLAMA,
            VISION_MODEL_ANTHROPIC, VISION_FALLBACK_MODEL, VISION_LEGACY_FALLBACK,
            VISION_CONFIDENCE_THRESHOLD,
        )
        provider = self._resolve_provider(VISION_PROVIDER, ANTHROPIC_API_KEY)
        return {
            "configured_provider": VISION_PROVIDER,
            "active_provider": provider,
            "anthropic_sdk_installed": _ANTHROPIC_AVAILABLE,
            "anthropic_api_key_set": bool(ANTHROPIC_API_KEY),
            "anthropic_model": VISION_MODEL_ANTHROPIC,
            "ollama_model": VISION_MODEL_OLLAMA,
            "ollama_fallback_model": VISION_FALLBACK_MODEL,
            "ollama_legacy_fallback": VISION_LEGACY_FALLBACK,
            "pillow_available": _PIL_AVAILABLE,
            "confidence_threshold": VISION_CONFIDENCE_THRESHOLD,
            "ready": (
                (provider == "anthropic" and _ANTHROPIC_AVAILABLE and bool(ANTHROPIC_API_KEY))
                or provider == "ollama"
            ),
        }

    # ── Image preprocessing ───────────────────────────────────────────────────

    @staticmethod
    def _preprocess_image(image_bytes: bytes, media_type: str) -> tuple[bytes, str]:
        """
        Normalise image to JPEG: converts WEBP/PNG/etc., strips EXIF metadata,
        and resizes to max 1024 px on the longest side.  Returns (bytes, mime).
        Falls back to raw bytes if Pillow is unavailable.
        """
        if not _PIL_AVAILABLE:
            logger.debug("[Vision] Pillow unavailable — forwarding raw image")
            return image_bytes, media_type

        try:
            img = _PilImage.open(io.BytesIO(image_bytes))
            original_format = img.format or "UNKNOWN"

            # Convert to RGB (drops alpha channel, ensures JPEG compatibility)
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGB")
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # Resize: keep within 1024 px to avoid context overflow on local models
            max_side = 1024
            w, h = img.size
            if max(w, h) > max_side:
                scale = max_side / max(w, h)
                img = img.resize((int(w * scale), int(h * scale)), _PilImage.LANCZOS)
                logger.info("[Vision] Resized %dx%d → %dx%d", w, h, img.size[0], img.size[1])

            out = io.BytesIO()
            img.save(out, format="JPEG", quality=88, optimize=True)
            processed = out.getvalue()

            logger.info(
                "[Vision] Preprocessing: %s (%s) → JPEG  %d → %d bytes",
                original_format, media_type, len(image_bytes), len(processed),
            )
            return processed, "image/jpeg"

        except Exception as exc:
            logger.warning("[Vision] Preprocessing failed (%s) — using raw bytes", exc)
            return image_bytes, media_type

    # ── Provider resolution ───────────────────────────────────────────────────

    @staticmethod
    def _resolve_provider(vision_provider: str, api_key: str) -> str:
        if vision_provider == "auto":
            return "anthropic" if (_ANTHROPIC_AVAILABLE and api_key) else "ollama"
        return vision_provider

    # ── Anthropic call ────────────────────────────────────────────────────────

    def _call_anthropic(self, image_b64: str, media_type: str, api_key: str,
                        model: str) -> dict:
        logger.info("[Vision] Calling Anthropic: model=%s", model)
        try:
            client = _anthropic_sdk.Anthropic(api_key=api_key)
            resp = client.messages.create(
                model=model, max_tokens=1024,
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": media_type, "data": image_b64,
                    }},
                    {"type": "text", "text": _VISION_PROMPT},
                ]}],
            )
            text = resp.content[0].text
            logger.info("[Vision] Anthropic OK: response_len=%d", len(text))
            parsed = self._extract_json(text) or {}
            return {
                "ok": True, "text": text, "model_used": model, "endpoint": "anthropic",
                "scene_description": parsed.get("scene_description", ""),
                "image_quality": parsed.get("image_quality", "good"),
            }
        except Exception as exc:
            logger.error("[Vision] Anthropic error: %s", exc)
            return self._error(f"Anthropic vision error: {exc}")

    # ── Ollama call (with model fallback chain) ───────────────────────────────

    def _call_ollama(self, image_b64: str) -> dict:
        from backend.config import (
            VISION_MODEL_OLLAMA, VISION_FALLBACK_MODEL, VISION_LEGACY_FALLBACK,
        )

        # Deduplicated model chain preserving priority order
        seen: set[str] = set()
        chain = [
            m for m in (VISION_MODEL_OLLAMA, VISION_FALLBACK_MODEL, VISION_LEGACY_FALLBACK)
            if m and not (m in seen or seen.add(m))  # type: ignore[func-returns-value]
        ]
        logger.info("[Vision] Ollama model chain: %s", " → ".join(chain))

        last_error: dict = self._error("No Ollama vision models available")
        for model in chain:
            result = self._try_single_model(image_b64, model)
            if result.get("ok"):
                # Validate: check the response actually parsed and isn't empty
                parsed = self._extract_json(result.get("text", ""))
                items = parsed.get("items", parsed.get("detections", [])) if parsed else []
                if items or parsed:   # accept if we got any JSON at all
                    logger.info("[Vision] Model %s succeeded", model)
                    parsed = parsed or {}
                    result["scene_description"] = parsed.get("scene_description", "")
                    result["image_quality"] = parsed.get("image_quality", "good")
                    return result
                # Model responded but returned no items — treat as soft failure
                logger.warning("[Vision] Model %s responded but returned empty items — trying next", model)
                last_error = self._error(
                    f"Model '{model}' responded but detected nothing. "
                    f"Try a better image or different model.",
                    error_code="empty_response",
                )
                continue

            error_code = result.get("error_code", "")
            last_error = result
            if error_code == "model_not_found":
                logger.info("[Vision] Model %s not found — skipping to next in chain", model)
                continue
            if error_code == "connection_refused":
                return result   # Ollama down — no point trying other models
            logger.warning("[Vision] Model %s failed (%s) — trying next", model, error_code)

        return last_error

    def _try_single_model(self, image_b64: str, model: str) -> dict:
        """Try one model. Returns {ok, text, model_used, endpoint} or {ok: False, error_code}."""
        from backend.config import OLLAMA_BASE_URL

        logger.info("[Vision] Trying model=%s  base_url=%s  b64_len=%d",
                    model, OLLAMA_BASE_URL, len(image_b64))

        # ── Attempt 1: /api/generate ─────────────────────────────────────────
        try:
            resp = requests.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={"model": model, "prompt": _VISION_PROMPT,
                      "images": [image_b64], "stream": False},
                timeout=120,
            )
            logger.info("[Vision] %s /api/generate → HTTP %d", model, resp.status_code)

            if resp.status_code == 200:
                text = resp.json().get("response", "")
                logger.info("[Vision] /api/generate OK  response_len=%d", len(text))
                return {"ok": True, "text": text, "model_used": model, "endpoint": "/api/generate"}

            if resp.status_code == 404:
                return {"ok": False, "error_code": "model_not_found",
                        "error": f"Model '{model}' not found in Ollama. Run: ollama pull {model}"}

            gen_status = resp.status_code
            gen_body   = resp.text
            logger.warning("[Vision] /api/generate failed: HTTP %d  %s", gen_status, gen_body[:300])

        except requests.exceptions.ConnectionError:
            from backend.config import OLLAMA_BASE_URL as _url
            return {"ok": False, "error_code": "connection_refused",
                    "error": f"Cannot connect to Ollama at {_url}. Run: ollama serve"}
        except Exception as exc:
            gen_status, gen_body = 0, str(exc)

        # ── Attempt 2: /api/chat (modern models / gemma4 / moondream) ────────
        try:
            resp2 = requests.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json={"model": model,
                      "messages": [{"role": "user", "content": _VISION_PROMPT,
                                    "images": [image_b64]}],
                      "stream": False},
                timeout=120,
            )
            logger.info("[Vision] %s /api/chat → HTTP %d", model, resp2.status_code)

            if resp2.status_code == 200:
                data = resp2.json()
                text = (data.get("message") or {}).get("content", "") or data.get("response", "")
                logger.info("[Vision] /api/chat OK  response_len=%d", len(text))
                return {"ok": True, "text": text, "model_used": model, "endpoint": "/api/chat"}

            if resp2.status_code == 404:
                return {"ok": False, "error_code": "model_not_found",
                        "error": f"Model '{model}' not found in Ollama. Run: ollama pull {model}"}

            chat_body = resp2.text
        except requests.exceptions.ConnectionError:
            from backend.config import OLLAMA_BASE_URL as _url
            return {"ok": False, "error_code": "connection_refused",
                    "error": f"Cannot connect to Ollama at {_url}. Run: ollama serve"}
        except Exception as exc:
            chat_body = str(exc)

        # ── Classify the combined failure ─────────────────────────────────────
        combined = (gen_body + chat_body).lower()
        logger.error("[Vision] Both endpoints failed for %s. gen:%d %s | chat:%d %s",
                     model, gen_status, gen_body[:150], resp2.status_code, chat_body[:150])

        if "failed to load image" in combined or "invalid image" in combined:
            return {"ok": False, "error_code": "image_load_failed",
                    "error": (f"Model '{model}' could not decode the image.\n"
                              f"Image may be in an unsupported format.\n"
                              f"Tip: ensure Pillow is installed (pip install Pillow>=10.0.0)")}

        if "does not support" in combined or "no vision" in combined:
            return {"ok": False, "error_code": "model_no_vision",
                    "error": f"Model '{model}' does not support image input. Use a vision model."}

        return {"ok": False, "error_code": "api_error",
                "error": (f"Ollama request failed for model '{model}'.\n"
                          f"/api/generate HTTP {gen_status}: {gen_body[:200]}\n"
                          f"/api/chat HTTP {getattr(resp2, 'status_code', '?')}: {chat_body[:200]}")}

    # ── Parsing & validation ──────────────────────────────────────────────────

    @staticmethod
    def _error(msg: str, **extra) -> dict:
        return {"ok": False, "error": msg,
                "detections": [], "high_confidence": [], "low_confidence": [], **extra}

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        """Extract first valid JSON object from model output."""
        # Strip markdown fences
        text = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```", "", text).strip()
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            pass
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    @staticmethod
    def _is_placeholder(value: str) -> bool:
        """Return True if the string looks like un-filled template text."""
        v = value.lower().strip()
        return any(p in v for p in _PLACEHOLDER_PATTERNS) or not v

    def _parse_detections(self, text: str) -> list[dict]:
        """Parse model output into validated, normalised detection dicts."""
        parsed = self._extract_json(text)
        if not parsed:
            logger.warning("[Vision] No JSON found in model response: %s", text[:400])
            return []

        # Support both new schema ("items") and old schema ("detections")
        raw_items = parsed.get("items") or parsed.get("detections") or []
        result = []

        for item in raw_items:
            name = str(item.get("component_name") or item.get("name", "")).strip()

            # ── Guard: reject placeholder / template leakage ──────────────────
            if self._is_placeholder(name):
                logger.warning("[Vision] Rejected placeholder detection: %r", name)
                continue

            visual_evidence = str(item.get("visual_evidence") or item.get("notes", "")).strip()
            if self._is_placeholder(visual_evidence):
                visual_evidence = ""

            raw_conf = item.get("confidence", 0.5)
            try:
                conf = min(1.0, max(0.0, float(raw_conf)))
            except (TypeError, ValueError):
                conf = 0.5

            qty = 1
            try:
                qty = max(1, int(item.get("quantity", 1)))
            except (TypeError, ValueError):
                pass

            # ── Category resolution: prefer category field, use component_type as hint ──
            component_type = str(item.get("component_type", "misc")).lower().strip()
            raw_category   = str(item.get("category", "")).lower().strip()

            if raw_category and raw_category not in ("unknown", ""):
                category = raw_category
            elif component_type in _TYPE_TO_CATEGORY:
                category = _TYPE_TO_CATEGORY[component_type]
            else:
                category = "misc"

            # Skip items still reporting as unknown with zero confidence
            if name.lower() in ("unknown", "unknown_component") and conf < 0.15:
                logger.debug("[Vision] Skipping very low-confidence unknown: conf=%.2f", conf)
                continue

            det = {
                "name":            name,
                "quantity":        qty,
                "category":        category,
                "subcategory":     str(item.get("subcategory", "")).lower().strip(),
                "confidence":      conf,
                "notes":           visual_evidence,
                # Private fields used for classification guards (stripped before return)
                "_component_type": component_type,
                "_specific_model_visible": bool(item.get("specific_model_visible", False)),
            }

            det = self._apply_classification_guards(det)
            result.append(det)

        return result

    @staticmethod
    def _apply_classification_guards(det: dict) -> dict:
        """Adjust confidence and category based on evidence quality."""
        evidence       = det.get("notes", "").lower()
        component_type = det.get("_component_type", "").lower()
        specific_vis   = det.get("_specific_model_visible", False)

        # 1. Passive-component evidence → override MCU/unknown category
        has_passive_evidence = any(kw in evidence for kw in _PASSIVE_EVIDENCE_KW)
        if has_passive_evidence and component_type in ("microcontroller", "sbc", "unknown"):
            logger.info("[Vision] Guard: passive evidence overrides category %s → passive_component",
                        component_type)
            det["category"] = "passive_component"
            det["confidence"] = min(det["confidence"], 0.7)

        # 2. MCU claimed without MCU evidence → lower confidence
        if component_type == "microcontroller":
            has_mcu_evidence = any(kw in evidence for kw in _MCU_EVIDENCE_KW)
            if not has_mcu_evidence:
                logger.info("[Vision] Guard: MCU claimed without evidence, capping confidence 0.35")
                det["confidence"] = min(det["confidence"], 0.35)

        # 3. Confidence > 0.9 only when specific model visually confirmed
        if not specific_vis and det["confidence"] > 0.9:
            det["confidence"] = 0.88

        # Remove internal guard fields before the detection is returned
        det.pop("_component_type", None)
        det.pop("_specific_model_visible", None)

        return det

    def _enrich_detections(self, detections: list[dict]) -> list[dict]:
        """Add current inventory context; auto-classify items still tagged misc."""
        enriched = []
        for det in detections:
            existing = self.hardware.find_part_smart(det["name"])
            det["existing_part_id"] = existing["id"] if existing else None
            det["current_qty"]      = int(existing["quantity"]) if existing else 0
            det["new_total"]        = det["current_qty"] + det["quantity"]
            det["is_new_part"]      = existing is None

            if (det.get("category") or "misc") == "misc":
                classification = classify_component(det["name"])
                if should_apply_classification(classification):
                    det["category"] = classification.category
                    if classification.subcategory:
                        det["subcategory"] = classification.subcategory

            enriched.append(det)
        return enriched
