import pytest


@pytest.fixture
def isolated_hardware_db(tmp_path, monkeypatch):
    db_file = tmp_path / "hardware.db"
    import backend.app.services.hardware_service as hw_mod
    monkeypatch.setattr(hw_mod, "DB_PATH", db_file, raising=False)
    import backend.app.tools.hardware_tool as tool_mod
    tool_mod._svc = None
    return db_file


def test_inventory_import_creates_stock_and_dedupes_names(isolated_hardware_db, tmp_path):
    inventory = tmp_path / "inventory.csv"
    inventory.write_text(
        "Part,Quantity,Manufacturer,Part Number\n"
        "ESP32-S3,5,Espressif,ESP32S3\n",
        encoding="utf-8",
    )

    bom = tmp_path / "Widget_BOM.csv"
    bom.write_text(
        "Reference,Value,Qty,Footprint,Manufacturer,MPN\n"
        "U1,ESP32S3,2,Module:ESP32,Espressif,ESP32S3\n",
        encoding="utf-8",
    )

    from backend.app.services.hardware_import_service import HardwareImportService
    from backend.app.services.hardware_service import HardwareService

    hardware = HardwareService()
    importer = HardwareImportService(hardware)

    inv = importer.import_file(str(inventory), source_type="inventory")
    assert inv["summary"]["created_parts"] == 1

    result = importer.import_file(str(bom), source_type="bom")
    assert result["project"]["name"] == "Widget"
    assert result["summary"]["created_parts"] == 0
    assert result["summary"]["linked_parts"] == 1

    parts = hardware.list_parts(search="ESP32")
    assert len(parts) == 1
    assert parts[0]["quantity"] == 5

    readiness = hardware.get_build_readiness(result["project"]["id"])
    assert readiness["status"] == "ready"
    impact = hardware.get_inventory_impact(result["project"]["id"])
    assert impact["parts"][0]["remaining_after_build"] == 3


def test_bom_import_detects_missing_parts(isolated_hardware_db, tmp_path):
    inventory = tmp_path / "inventory.csv"
    inventory.write_text(
        "Name,Quantity\n"
        "MPU6050,1\n",
        encoding="utf-8",
    )
    bom = tmp_path / "SensorRig_BOM.csv"
    bom.write_text(
        "Reference,Value,Qty\n"
        "U1,MPU6050,1\n"
        "U2,VL53L0X,1\n",
        encoding="utf-8",
    )

    from backend.app.services.hardware_import_service import HardwareImportService
    from backend.app.services.hardware_service import HardwareService

    hardware = HardwareService()
    importer = HardwareImportService(hardware)
    importer.import_file(str(inventory), source_type="inventory")
    result = importer.import_file(str(bom), source_type="bom")

    readiness = hardware.get_build_readiness(result["project"]["id"])
    assert readiness["status"] == "partially_ready"
    assert readiness["readiness_pct"] == 50
    assert readiness["missing"][0]["name"] == "VL53L0X"


def test_kicad_schematic_import_links_project(isolated_hardware_db, tmp_path):
    schematic = tmp_path / "Controller.kicad_sch"
    schematic.write_text(
        '(kicad_sch\n'
        '  (symbol (property "Reference" "U1") (property "Value" "ATmega328P") (property "Footprint" "Package_DIP:DIP-28"))\n'
        '  (symbol (property "Reference" "U2") (property "Value" "ATmega328P") (property "Footprint" "Package_DIP:DIP-28"))\n'
        ')\n',
        encoding="utf-8",
    )
    from backend.app.services.hardware_import_service import HardwareImportService
    from backend.app.services.hardware_service import HardwareService
    hardware = HardwareService()
    result = HardwareImportService(hardware).import_file(str(schematic), source_type="auto")
    assert result["summary"]["source_type"] == "bom"
    assert result["summary"]["linked_parts"] == 1
    parts = hardware.get_project_parts(result["project"]["id"])
    assert parts[0]["quantity_required"] == 2


def test_markdown_component_list_import(isolated_hardware_db, tmp_path):
    notes = tmp_path / "Notes.md"
    notes.write_text("- 3x JST Connector\n- VL53L0X\n", encoding="utf-8")
    from backend.app.services.hardware_import_service import HardwareImportService
    from backend.app.services.hardware_service import HardwareService
    hardware = HardwareService()
    result = HardwareImportService(hardware).import_file(str(notes), source_type="auto", project_name="Notes Project")
    assert result["summary"]["imported_count"] == 2
    assert len(hardware.get_project_parts(result["project"]["id"])) == 2


@pytest.mark.parametrize("command,tool", [
    ("import bom Widget_BOM.csv", "import_bom"),
    ("import inventory inventory.csv", "import_inventory"),
    ("show imported components", "show_imported_components"),
    ("show imported projects", "show_imported_projects"),
    ("show bom status", "list_imports"),
    ("show project readiness", "show_project_readiness"),
    ("show inventory impact for Widget", "show_inventory_impact"),
])
def test_planner_hardware_import_routes(command, tool):
    from backend.app.tools.planner import _regex_fallback
    result = _regex_fallback(command)
    assert result["action"] == "call_tool"
    assert result["name"] == tool
