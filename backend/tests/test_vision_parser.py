"""Regression tests for the vision parser and classification guards.

NOTE: Phase 12F (Vision-Assisted Inventory) is currently paused. These tests cover
experimental code in hardware_vision_service.py that is disabled at runtime
(ENABLE_VISION_INVENTORY=false). Keep them so re-enabling the feature stays safe.

Run with: pytest backend/tests/test_vision_parser.py -v
"""
import json
import pytest


@pytest.fixture
def svc(tmp_path, monkeypatch):
    import backend.app.services.hardware_service as hw_mod
    monkeypatch.setattr(hw_mod, "DB_PATH", tmp_path / "hw.db", raising=False)
    from backend.app.services.hardware_vision_service import HardwareVisionService
    return HardwareVisionService()


# ── helpers ───────────────────────────────────────────────────────────────────

def _fake_response(items, scene="test scene", quality="good"):
    """Build a JSON string in the new schema format."""
    return json.dumps({"items": items, "scene_description": scene, "image_quality": quality})


def _det(name, component_type, category, confidence, evidence, specific_model=False, qty=1):
    return {
        "component_name": name,
        "component_type": component_type,
        "category": category,
        "quantity": qty,
        "confidence": confidence,
        "visual_evidence": evidence,
        "specific_model_visible": specific_model,
    }


# ── Placeholder rejection ─────────────────────────────────────────────────────

def test_rejects_placeholder_name(svc):
    """Parser must never return placeholder text as a component name."""
    text = _fake_response([
        _det("specific model name e.g. ESP32-S3", "microcontroller", "microcontroller", 0.9,
             "circuit board with chips"),
    ])
    result = svc._parse_detections(text)
    assert result == [], f"Expected empty detections, got: {result}"


def test_rejects_eg_in_name(svc):
    text = _fake_response([
        _det("e.g. ESP32-S3", "microcontroller", "microcontroller", 0.8, "green pcb"),
    ])
    assert svc._parse_detections(text) == []


def test_rejects_generic_or_specific_name(svc):
    text = _fake_response([
        _det("generic or specific name", "misc", "misc", 0.5, "something"),
    ])
    assert svc._parse_detections(text) == []


def test_rejects_example_keyword(svc):
    text = _fake_response([
        _det("example component", "misc", "misc", 0.6, "image shows example component"),
    ])
    assert svc._parse_detections(text) == []


def test_rejects_empty_name(svc):
    text = _fake_response([_det("", "misc", "misc", 0.5, "unclear")])
    assert svc._parse_detections(text) == []


# ── Resistor detection (the bug that prompted this refactor) ──────────────────

def test_resistor_detected_correctly(svc):
    """
    Regression: an axial resistor image must yield a resistor detection,
    NOT "ESP32-S3" or any placeholder.
    """
    text = _fake_response([
        _det(
            name="axial resistor",
            component_type="resistor",
            category="passive_component",
            confidence=0.82,
            evidence="cylindrical body with four colour bands and two axial leads",
            specific_model=False,
            qty=1,
        )
    ])
    detections = svc._parse_detections(text)
    assert len(detections) == 1

    det = detections[0]
    assert det["name"] == "axial resistor"
    assert det["category"] == "passive_component"
    assert 0.5 <= det["confidence"] <= 1.0
    assert "colour band" in det["notes"] or "axial lead" in det["notes"]
    # Must not be confused with microcontrollers
    assert det["category"] != "microcontroller"


def test_resistor_with_mcu_type_override(svc):
    """
    Classification guard: model claims 'microcontroller' but evidence describes
    colour bands and axial leads → guard must override to passive_component and
    cap confidence.
    """
    text = _fake_response([
        _det(
            name="resistor",
            component_type="microcontroller",   # wrong — model hallucinated MCU type
            category="microcontroller",
            confidence=0.92,
            evidence="two axial leads, four colour bands, cylindrical body",
            specific_model=False,
        )
    ])
    detections = svc._parse_detections(text)
    assert len(detections) == 1

    det = detections[0]
    assert det["category"] == "passive_component", (
        f"Guard failed: category should be passive_component, got '{det['category']}'"
    )
    assert det["confidence"] <= 0.7, (
        f"Guard failed: confidence should be capped ≤0.7 for MCU-but-passive, got {det['confidence']}"
    )


def test_mcu_without_evidence_confidence_capped(svc):
    """
    Classification guard: microcontroller claimed with no MCU evidence in visual_evidence
    → confidence must be capped at 0.35.
    """
    text = _fake_response([
        _det(
            name="some chip",
            component_type="microcontroller",
            category="microcontroller",
            confidence=0.88,
            evidence="small black rectangular object",   # no pcb/esp/marking keywords
            specific_model=False,
        )
    ])
    detections = svc._parse_detections(text)
    assert len(detections) == 1
    assert detections[0]["confidence"] <= 0.35


def test_confidence_capped_without_specific_model_visible(svc):
    """
    If specific_model_visible is False, confidence must not exceed 0.88.
    """
    text = _fake_response([
        _det(
            name="ESP32-S3",
            component_type="microcontroller",
            category="microcontroller",
            confidence=0.97,
            evidence="green pcb with esp32 chip visible and silkscreen marking",
            specific_model=False,   # marking not clearly readable
        )
    ])
    detections = svc._parse_detections(text)
    assert detections[0]["confidence"] <= 0.88


def test_specific_model_visible_allows_high_confidence(svc):
    """
    When specific_model_visible is True, high confidence (≤0.9 cap is not applied).
    """
    text = _fake_response([
        _det(
            name="ESP32-S3",
            component_type="microcontroller",
            category="microcontroller",
            confidence=0.95,
            evidence="green pcb with ESP32-S3 silkscreen marking clearly readable",
            specific_model=True,
        )
    ])
    detections = svc._parse_detections(text)
    # confidence 0.95 is allowed when specific_model_visible=True
    assert detections[0]["confidence"] >= 0.90


# ── Schema compatibility ───────────────────────────────────────────────────────

def test_legacy_detections_schema_still_works(svc):
    """Parser must still handle the old 'detections' key (llava responses)."""
    text = json.dumps({
        "detections": [{"name": "ESP32", "quantity": 2, "category": "microcontroller",
                        "confidence": 0.8, "notes": "green pcb with esp32 chip and usb port"}],
        "scene_description": "PCB photo",
        "image_quality": "good",
    })
    detections = svc._parse_detections(text)
    assert len(detections) == 1
    assert detections[0]["name"] == "ESP32"


def test_json_wrapped_in_markdown_fence(svc):
    """Parser must handle ```json fences from models that ignore the no-markdown rule."""
    text = '```json\n' + _fake_response([
        _det("ceramic capacitor", "capacitor", "passive_component", 0.75,
             "small ceramic disc capacitor, yellow body")
    ]) + '\n```'
    detections = svc._parse_detections(text)
    assert len(detections) == 1
    assert detections[0]["name"] == "ceramic capacitor"


def test_is_placeholder_helper(svc):
    """Unit test the _is_placeholder guard directly."""
    assert svc._is_placeholder("specific model name e.g. ESP32-S3")
    assert svc._is_placeholder("e.g.")
    assert svc._is_placeholder("example")
    assert svc._is_placeholder("generic or specific name")
    assert svc._is_placeholder("")
    assert not svc._is_placeholder("axial resistor")
    assert not svc._is_placeholder("ESP32-S3")
    assert not svc._is_placeholder("MPU6050")
