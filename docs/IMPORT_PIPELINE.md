# Import Pipeline

Phase 12C adds data-driven hardware imports so SILVIA can learn inventory and project requirements from files.

## Supported Sources

- KiCad-style CSV BOM files
- Generic CSV inventory files
- Excel `.xlsx` / `.xlsm` inventory or BOM files when `openpyxl` is installed
- KiCad `.kicad_sch` schematic files
- KiCad `.kicad_pro` project files by reading sibling schematics
- Markdown / text component lists

## Flow

1. Resolve the provided filename or path.
2. Parse rows into normalized component records.
3. Match existing inventory by manufacturer + part number, part number, normalized name, or alias.
4. Upsert inventory records.
5. For BOM imports, create the project if needed and link required parts.
6. Record import history and validation warnings.
7. Recompute build readiness from real inventory and project-part links.

## Commands

- `import bom Widget_BOM.csv`
- `import bom Widget_BOM.csv for Widget`
- `import inventory inventory.csv`
- `show imported components`
- `show imported projects`
- `show bom status`
- `show project readiness`
- `show inventory impact for Widget`
- `import bom Controller.kicad_sch`
- `import bom Controller.kicad_pro`

No stock is fabricated during BOM imports. If a BOM requires a part that is not in inventory, SILVIA creates a zero-stock inventory record and reports the project as missing that part.
