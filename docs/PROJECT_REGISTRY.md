# Hardware Project Registry

Hardware projects live in `hw_projects` and are linked to required parts through `hw_project_parts`.

Project-part links store:

- `quantity_required`
- `is_required`
- `acceptable_substitutes`
- `source`
- `notes`

## Project Creation

Projects can be created manually or automatically from BOM imports.

Example:

`DroneHive_BOM.csv` creates or reuses the project `DroneHive`.

## Build Readiness

Readiness is computed from real linked parts:

- `ready`: all required parts are in stock
- `partially_ready`: at least half of required part types are available
- `missing_parts`: some required part types are available
- `blocked`: no required part types are available

No readiness result is guessed from project names or notes.

If no required parts are recorded, readiness returns `no_required_parts`; Hardware Assistant surfaces this as an unknown state and offers to add requirements manually or import a BOM.

Acceptable substitutes are explicit only. For example, ESP32-S3 can satisfy an ESP32-C3 requirement only if the requirement lists ESP32-S3 as an acceptable substitute.

## Hardware Assistant

The Hardware Assistant can create projects, record required parts, assign parts to projects, show project parts, and answer build-readiness or missing-parts questions through registry lookups.
