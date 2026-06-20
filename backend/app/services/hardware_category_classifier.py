"""Reusable electronics component category classifier.

The classifier is intentionally deterministic: it uses category rules with
aliases/keywords and returns a confidence score so callers can decide whether
to apply a category automatically or ask the user.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class CategoryClassification:
    category: str
    confidence: float
    subcategory: str = ""
    matched: tuple[str, ...] = ()
    reason: str = ""


_CATEGORY_RULES: tuple[tuple[str, str, float, tuple[str, ...]], ...] = (
    (
        "audio",
        "amplifier",
        0.96,
        (
            r"\bmax9835[67]a\b",
            r"\baudio\s*amp(?:lifier)?\b",
            r"\bamplifier\b",
        ),
    ),
    (
        "storage",
        "microsd",
        0.95,
        (
            r"\bmicro\s*sd\b",
            r"\bmicrosd\b",
            r"\bsd\s*card\s*module\b",
            r"\bsd\s*module\b",
        ),
    ),
    (
        "gps_gnss",
        "",
        0.96,
        (
            r"\bneo[-\s]?m8n\b",
            r"\bneo[-\s]?m9n\b",
            r"\bublox\b",
            r"\bgps\b",
            r"\bgnss\b",
        ),
    ),
    (
        "radio",
        "",
        0.94,
        (
            r"\blora(?:32)?\b",
            r"\blilygo\b",
            r"\bttgo\b",
            r"\bsx127[68]\b",
            r"\bsx126[28]\b",
            r"\bnrf24(?:l01)?\b",
            r"\belrs\b",
            r"\bexpresslrs\b",
            r"\brf\b",
        ),
    ),
    (
        "microcontroller",
        "",
        0.95,
        (
            r"\braspberry\s*pi\s*pico\b",
            r"\brp2040\b",
            r"\besp32(?:[-\s]?(?:s2|s3|c3|c6|wroom|wrover))?\b",
            r"\besp8266\b",
            r"\barduino\b",
            r"\bstm32\b",
            r"\bblue\s*pill\b",
            r"\bbluepill\b",
            r"\bwemos\b",
            r"\bnode\s*mcu\b",
            r"\bnodemcu\b",
            r"\bxiao\b",
            r"\bteensy\b",
            r"\batmega\d*\b",
            r"\battiny\d*\b",
        ),
    ),
    (
        "sbc",
        "",
        0.94,
        (
            r"\braspberry\s*pi\s*(?:zero|[345])\b",
            r"\brpi\s*(?:zero|[345])\b",
            r"\bjetson\b",
            r"\borange\s*pi\b",
            r"\bbanana\s*pi\b",
            r"\bbeagle\s*bone\b",
            r"\bbeaglebone\b",
        ),
    ),
    (
        "sensor",
        "adc",
        0.95,
        (
            r"\bads1115\b",
            r"\badc\b",
            r"\banalog\s*(?:to|-)?\s*digital\b",
        ),
    ),
    (
        "sensor",
        "environment",
        0.94,
        (
            r"\bbmp180\b",
            r"\bbmp280\b",
            r"\bbme280\b",
            r"\bbarometer\b",
            r"\benvironment(?:al)?\b",
        ),
    ),
    (
        "sensor",
        "line",
        0.94,
        (
            r"\bky[-\s]?033\b",
            r"\bline\s*(?:following|follower|tracking|tracker)\b",
        ),
    ),
    (
        "sensor",
        "audio",
        0.93,
        (
            r"\bky[-\s]?037\b",
            r"\bsound\s*sensor\b",
            r"\bmicrophone\s*sensor\b",
        ),
    ),
    (
        "sensor",
        "temperature",
        0.92,
        (
            r"\blm75(?:bd)?\b",
            r"\btemperature\b",
            r"\btemp\s*sensor\b",
        ),
    ),
    (
        "sensor",
        "color",
        0.94,
        (
            r"\btcs?34725\b",
            r"\brgb\s*sensor\b",
            r"\bcolo[u]?r\s*sensor\b",
        ),
    ),
    (
        "sensor",
        "liquid",
        0.92,
        (
            r"\bwater\s*level\b",
            r"\bliquid\s*level\b",
            r"\blevel\s*sensor\b",
        ),
    ),
    (
        "sensor",
        "",
        0.92,
        (
            r"\bmpu[-\s]?6050\b",
            r"\bbme280\b",
            r"\bbmp280\b",
            r"\bbmp180\b",
            r"\bvl53l0x\b",
            r"\bhc[-\s]?sr04\b",
            r"\bdht22\b",
            r"\bdht11\b",
            r"\bimu\b",
            r"\baccelerometer\b",
            r"\bgyro(?:scope)?\b",
            r"\bbarometer\b",
            r"\btof\b",
        ),
    ),
    (
        "display",
        "",
        0.9,
        (
            r"\btft\b",
            r"\boled\b",
            r"\blcd\b",
            r"\bili9341\b",
            r"\bst7789\b",
            r"\bssd1306\b",
            r"\bdisplay\b",
            r"\bscreen\b",
        ),
    ),
    (
        "power",
        "",
        0.86,
        (
            r"\bbec\b",
            r"\bregulator\b",
            r"\blipo\b",
            r"\bli[-\s]?ion\b",
            r"\bcharger\b",
            r"\bcapacitor\b",
            r"\bbattery\b",
            r"\bbuck\b",
            r"\bboost\b",
            r"\bpower\b",
        ),
    ),
    (
        "motor",
        "",
        0.86,
        (
            r"\bmotor\b",
            r"\bservo\b",
            r"\bstepper\b",
            r"\besc\b",
            r"\bactuator\b",
        ),
    ),
)


_DISPLAY_NAMES = {
    "gps_gnss": "GPS/GNSS",
    "sbc": "single-board computer",
}


def classify_component(
    name: str,
    *,
    manufacturer: str = "",
    part_number: str = "",
    notes: str = "",
) -> CategoryClassification:
    """Return the best category classification for a component-like record."""
    haystack = " ".join(
        item.strip() for item in (name or "", manufacturer or "", part_number or "", notes or "") if item
    ).lower()
    if not haystack:
        return CategoryClassification("misc", 0.0, reason="No component text supplied.")

    best = CategoryClassification("misc", 0.0, reason="No category rule matched.")
    for category, subcategory, confidence, patterns in _CATEGORY_RULES:
        matched: list[str] = []
        for pattern in patterns:
            if re.search(pattern, haystack, re.I):
                matched.append(_pattern_label(pattern))
        if matched and confidence > best.confidence:
            display = _DISPLAY_NAMES.get(category, category)
            subcategory_text = f" / {subcategory}" if subcategory else ""
            best = CategoryClassification(
                category=category,
                confidence=confidence,
                subcategory=subcategory,
                matched=tuple(sorted(set(matched))),
                reason=f"Matched {display}{subcategory_text} keyword(s): {', '.join(sorted(set(matched)))}",
            )
    return best


def should_apply_classification(classification: CategoryClassification, threshold: float = 0.65) -> bool:
    return classification.category != "misc" and classification.confidence >= threshold


def _pattern_label(pattern: str) -> str:
    label = pattern
    label = re.sub(r"\\b", "", label)
    label = re.sub(r"\(\?:|\)|\[|\]|\?|\+|\*|\{.*?\}", "", label)
    label = label.replace("\\s", " ").replace("\\-", "-").replace("\\", "")
    label = label.replace("|", "/")
    label = re.sub(r"\s+", " ", label)
    return label.strip() or pattern
