# BOM Processing

SILVIA parses BOM rows into:

- Part name
- Quantity
- Value
- Footprint
- Manufacturer
- Manufacturer part number
- Project

## Column Matching

The importer recognizes common BOM headers:

- Quantity: `Qty`, `Quantity`, `Count`
- Value: `Value`
- Name: `Part`, `Part Name`, `Component`, `Description`
- Footprint: `Footprint`, `Package`
- Manufacturer: `Manufacturer`, `MFG`, `MFR`
- Part number: `MPN`, `Part Number`, `Manufacturer Part Number`
- References: `Reference`, `References`, `Designator`

If no quantity is present, references are counted. If neither exists, quantity defaults to `1`.

## Project Linking

For `Widget_BOM.csv`, the default project name is `Widget`. A command can override this:

`import bom exported.csv for Sensor Rig`

BOM imports create or reuse a hardware project, then link imported components through `hw_project_parts`.

## KiCad Project Files

`.kicad_sch` files are parsed for symbol `Reference`, `Value`, and `Footprint` properties. Matching values and footprints are merged into a single required component with the combined quantity.

`.kicad_pro` imports read sibling `.kicad_sch` files in the same folder. KiCad CSV BOM exports remain the most reliable source because they can include manufacturer and part-number fields.

## Markdown Lists

Markdown imports support simple component-list rows such as:

- `- 3x JST Connector`
- `- VL53L0X`
- `| ESP32-S3 | 2 |`

## Deduplication

Components are matched in this order:

1. Manufacturer + exact part number
2. Exact part number
3. Normalized name
4. Existing aliases

Normalization removes punctuation and spacing, so names such as `ESP32-S3`, `ESP32 S3`, and `ESP32S3` collapse to the same key.
