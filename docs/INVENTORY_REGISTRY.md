# Inventory Registry

The inventory registry stores physical components in `hw_inventory`.

## Core Fields

- `name`
- `normalized_name`
- `aliases`
- `category`
- `quantity`
- `status`
- `manufacturer`
- `part_number`
- `location`
- `notes`
- `datasheet_url`

## Import Behavior

Inventory imports update real stock quantities from CSV/XLSX files. BOM imports do not add stock; they only create missing zero-stock component records so readiness can report shortages honestly.

Build readiness compares `hw_inventory.quantity` against `hw_project_parts.quantity_required`.

When imports or assistant entries do not provide an explicit category, SILVIA runs the hardware category classifier. Confident matches are applied automatically; low-confidence records remain `misc` and are surfaced in previews so the user can confirm or later clean them up.

## Hardware Assistant

The Hardware Assistant can bulk-add or bulk-remove inventory from multi-line messages. It previews stock transitions such as `12 → 7` before committing changes.

The assistant also supports `recategorize inventory` / `clean inventory categories`, which scans existing `misc` parts, previews confident category fixes, and applies them only after confirmation.
