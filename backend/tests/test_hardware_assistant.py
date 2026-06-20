import pytest


@pytest.fixture
def assistant(tmp_path, monkeypatch):
    db_file = tmp_path / "hardware_assistant.db"
    import backend.app.services.hardware_service as hw_mod
    monkeypatch.setattr(hw_mod, "DB_PATH", db_file, raising=False)
    from backend.app.services.hardware_assistant_service import HardwareAssistantService
    return HardwareAssistantService()


def confirm(assistant, text):
    preview = assistant.handle(text)
    assert preview["pending_action"], preview["reply"]
    result = assistant.handle("confirm", preview["pending_action"])
    assert result["committed"], result["reply"]
    return result


def test_bulk_add_and_remove_inventory(assistant):
    confirm(assistant, "I bought:\n5 ESP32-S3\n2 MPU6050\n1 NEO-M8N")
    info = assistant.handle("how many ESP32 do I own")
    assert "ESP32-S3 qty:5" in info["reply"]

    preview = assistant.handle("Remove:\n2 ESP32-S3")
    assert "5 → 3" in preview["reply"]
    assistant.handle("confirm", preview["pending_action"])
    info = assistant.handle("how many ESP32 do I own")
    assert "ESP32-S3 qty:3" in info["reply"]


def test_project_assign_missing_and_readiness(assistant):
    confirm(assistant, "Add:\n1 ESP32-S3")
    confirm(assistant, "create project Rover")
    confirm(assistant, "assign ESP32-S3 to Rover")
    project = assistant.handle("show components for Rover")
    assert "ESP32-S3" in project["reply"]
    readiness = assistant.handle("can I build Rover")
    assert "100% ready" in readiness["reply"]


def test_order_log_and_delivery(assistant):
    preview = assistant.handle("Log order:\n5 ESP32-S3\nVendor:\nAliExpress")
    assert "AliExpress" in preview["reply"]
    assistant.handle("confirm", preview["pending_action"])
    orders = assistant.handle("show pending orders")
    assert "ESP32-S3" in orders["reply"]
    delivered = assistant.handle("mark order delivered")
    assert delivered["pending_action"]
    result = assistant.handle("confirm", delivered["pending_action"])
    assert "delivered" in result["reply"]
    recent = assistant.handle("show recent deliveries")
    assert "delivered" in recent["reply"]


def test_import_bom_and_query(assistant, tmp_path):
    bom = tmp_path / "Tiny_BOM.csv"
    bom.write_text("Reference,Value,Qty\nU1,VL53L0X,1\n", encoding="utf-8")
    preview = assistant.handle(f"import bom {bom}")
    assert preview["pending_action"]
    result = assistant.handle("confirm", preview["pending_action"])
    assert "Imported BOM" in result["reply"]
    imports = assistant.handle("show imported BOMs")
    assert "Tiny" in imports["reply"]
    impact = assistant.handle("what inventory will be consumed for Tiny")
    assert "VL53L0X" in impact["reply"]


def test_bulk_add_classifies_electronics_categories(assistant):
    confirm(
        assistant,
        """I bought:
1 Arduino Mega
1 STM32 Bluepill
1 ESP8266
1 ESP32 WROOM
1 ESP32 Wemos D1
1 ESP32 Wemos S2
1 Raspberry Pi 3 4GB
1 Raspberry Pi 4 4GB
1 Raspberry Pi 5 8GB
1 Raspberry Pi Pico
1 Raspberry Pi Zero
1 Seeed XIAO Sense ESP32S3
1 LILYGO TTGO T3 LoRa32
1 NEO-M8N GPS module
1 TFT display""",
    )

    expected = {
        "Arduino Mega": "microcontroller",
        "STM32 Bluepill": "microcontroller",
        "ESP8266": "microcontroller",
        "ESP32 WROOM": "microcontroller",
        "ESP32 Wemos D1": "microcontroller",
        "ESP32 Wemos S2": "microcontroller",
        "Raspberry Pi 3 4GB": "sbc",
        "Raspberry Pi 4 4GB": "sbc",
        "Raspberry Pi 5 8GB": "sbc",
        "Raspberry Pi Pico": "microcontroller",
        "Raspberry Pi Zero": "sbc",
        "Seeed XIAO Sense ESP32S3": "microcontroller",
        "LILYGO TTGO T3 LoRa32": "radio",
        "NEO-M8N GPS module": "gps_gnss",
        "TFT display": "display",
    }
    for name, category in expected.items():
        part = assistant.hardware.find_part_smart(name)
        assert part, name
        assert part["category"] == category, name

    obvious_microcontrollers = [
        "Arduino Mega",
        "STM32 Bluepill",
        "ESP8266",
        "ESP32 WROOM",
        "ESP32 Wemos D1",
        "ESP32 Wemos S2",
        "Raspberry Pi Pico",
        "Seeed XIAO Sense ESP32S3",
    ]
    assert all(assistant.hardware.find_part_smart(name)["category"] != "misc" for name in obvious_microcontrollers)


def test_clean_inventory_categories_recategorizes_existing_misc(assistant):
    part = assistant.hardware.add_part("Arduino Mega", category="uncategorized", quantity=1)
    assistant.hardware.update_part(part["id"], category="misc")

    preview = assistant.handle("clean inventory categories")
    assert preview["pending_action"], preview["reply"]
    assert "Arduino Mega" in preview["reply"]
    assert "microcontroller" in preview["reply"]

    result = assistant.handle("confirm", preview["pending_action"])
    assert result["committed"], result["reply"]
    updated = assistant.hardware.find_part_smart("Arduino Mega")
    assert updated["category"] == "microcontroller"


def test_module_classifier_assigns_subcategories_and_non_sensor_modules(assistant):
    confirm(
        assistant,
        """I bought:
1 ADS1115
1 BMP180
1 KY-033 line following sensor
1 KY-037 sound sensor
1 LM75BD temperature sensor
1 TC34725 RGB sensor
1 Water level sensor
1 MAX98356A audio amplifier
1 microSD module""",
    )

    expected = {
        "ADS1115": ("sensor", "adc"),
        "BMP180": ("sensor", "environment"),
        "KY-033 line following sensor": ("sensor", "line"),
        "KY-037 sound sensor": ("sensor", "audio"),
        "LM75BD temperature sensor": ("sensor", "temperature"),
        "TC34725 RGB sensor": ("sensor", "color"),
        "Water level sensor": ("sensor", "liquid"),
        "MAX98356A audio amplifier": ("audio", "amplifier"),
        "microSD module": ("storage", "microsd"),
    }
    for name, (category, subcategory) in expected.items():
        part = assistant.hardware.find_part_smart(name)
        assert part, name
        assert part["category"] == category, name
        assert part["subcategory"] == subcategory, name
        assert part["category"] != "misc", name


def test_clean_inventory_categories_handles_module_examples(assistant):
    names = [
        "ADS1115",
        "BMP180",
        "KY-033",
        "KY-037",
        "LM75BD",
        "TCS34725 color sensor",
        "Water level sensor",
        "MAX98357A amplifier",
        "SD card module",
    ]
    for name in names:
        part = assistant.hardware.add_part(name, category="uncategorized", quantity=1)
        assistant.hardware.update_part(part["id"], category="misc", subcategory="")

    preview = assistant.handle("recategorize inventory")
    assert preview["pending_action"], preview["reply"]
    for name in names:
        assert name in preview["reply"]

    result = assistant.handle("confirm", preview["pending_action"])
    assert result["committed"], result["reply"]
    assert not assistant.hardware.list_parts(category="misc")
    assert assistant.hardware.find_part_smart("MAX98357A amplifier")["category"] == "audio"
    assert assistant.hardware.find_part_smart("SD card module")["category"] == "storage"


def test_project_requirements_drive_missing_and_build_readiness(assistant):
    confirm(assistant, "create project DroneHive")
    confirm(assistant, "Add:\n1 ESP32-C3\n1 MPU6050")
    confirm(
        assistant,
        """DroneHive requires:
1 ESP32-C3
1 MPU6050
1 VL53L0X""",
    )

    blocked = assistant.handle("can I build DroneHive?")
    assert "No." in blocked["reply"]
    assert "VL53L0X" in blocked["reply"]
    assert "×1" in blocked["reply"]

    missing = assistant.handle("what am I missing for DroneHive")
    assert "VL53L0X" in missing["reply"]
    assert missing["data"][0]["shortfall"] == 1

    confirm(assistant, "Add:\n1 VL53L0X")
    ready = assistant.handle("can I build DroneHive?")
    assert "Yes." in ready["reply"]
    assert ready["data"]["status"] == "ready"


def test_inventory_impact_and_buildable_project_queries(assistant):
    confirm(assistant, "Add:\n1 ESP32-C3\n1 MPU6050\n1 VL53L0X")
    confirm(assistant, "DroneHive requires:\n1 ESP32-C3\n1 MPU6050\n1 VL53L0X")
    confirm(assistant, "GroundBot requires:\n1 ESP32-C3\n1 AO3400A")

    impact = assistant.handle("what parts would DroneHive use?")
    assert "ESP32-C3" in impact["reply"]
    assert "MPU6050" in impact["reply"]
    assert "VL53L0X" in impact["reply"]

    buildable = assistant.handle("which projects can I build right now?")
    assert "DroneHive" in buildable["reply"]
    assert "GroundBot" not in buildable["reply"]

    blocked = assistant.handle("which projects are blocked?")
    assert "GroundBot" in blocked["reply"]
    assert "AO3400A" in blocked["reply"]


def test_no_requirements_are_reported_as_unknown_not_ready(assistant):
    confirm(assistant, "create project EmptyRig")
    answer = assistant.handle("can I build EmptyRig?")
    assert "do not have requirements recorded" in answer["reply"]
    assert "import a BOM" in answer["reply"]


def test_bom_import_populates_requirements_for_assistant_readiness(assistant, tmp_path):
    bom = tmp_path / "DroneHive_BOM.csv"
    bom.write_text(
        "Reference,Value,Qty\n"
        "U1,ESP32-C3,1\n"
        "U2,MPU6050,1\n",
        encoding="utf-8",
    )
    confirm(assistant, "Add:\n1 ESP32-C3\n1 MPU6050")
    result = confirm(assistant, f"import bom {bom}")
    assert result["data"]["summary"]["linked_parts"] == 2

    ready = assistant.handle("can I build DroneHive?")
    assert "Yes." in ready["reply"]
    detail = assistant.hardware.get_project_with_parts(ready["data"]["project_id"])
    assert {part["source"] for part in detail["parts"]} == {"BOM import"}


def test_requirement_substitutes_are_explicit_only(assistant):
    confirm(assistant, "Add:\n1 ESP32-S3")
    confirm(assistant, "add ESP32-C3 as required part for SubRig quantity 1 substitute ESP32-S3")

    ready = assistant.handle("can I build SubRig?")
    assert "Yes." in ready["reply"]
    assert ready["data"]["required_parts"][0]["substitute_matches"][0]["name"] == "ESP32-S3"
