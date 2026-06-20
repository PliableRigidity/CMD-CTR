# Hardware Assistant

Phase 12D adds a restricted assistant inside the Hardware Board.

## Scope

The assistant can only use hardware registries:

- Inventory Registry
- Hardware Project Registry
- Orders Registry
- BOM/import history

It does not expose web search, MAGI, desktop control, infrastructure, node control, services, Watch Officer, or main SILVIA memory.

## Preview Mode

Mutating actions return a preview and require confirmation:

- Bulk inventory add
- Bulk inventory removal
- Project creation
- Part assignment
- Order logging
- Order delivery updates
- BOM / inventory import

The user must reply `confirm` before changes are applied.

## Supported Examples

- `I bought:\n5 ESP32-S3\n2 MPU6050`
- `Remove:\n2 VL53L0X`
- `show all sensors`
- `clean inventory categories`
- `create project Rover`
- `assign ESP32-S3 to Rover`
- `DroneHive requires:\n1 ESP32-C3\n1 MPU6050\n1 VL53L0X`
- `add ESP32-C3 as required part for DroneHive quantity 1 substitute ESP32-S3`
- `can I build Rover`
- `which projects can I build right now`
- `which projects are blocked`
- `what parts am I missing for DroneHive`
- `log order:\n5 ESP32-S3\nVendor:\nAliExpress`
- `mark order delivered`
- `show imported BOMs`
- `what inventory will be consumed for Rover`

The implementation is deterministic and registry-driven. It does not call MAGI or the general SILVIA planner.

## Build Readiness

Build readiness is computed only from recorded project requirements in the Hardware Project Registry. The assistant never infers requirements from a project name.

If a project has no required parts, the assistant responds:

`I do not have requirements recorded for this project yet. Add requirements manually or import a BOM.`

Supported readiness commands include:

- `can I build DroneHive?`
- `what am I missing for DroneHive?`
- `what parts would DroneHive use?`
- `if I build DroneHive, what inventory remains?`
- `which projects can I build right now?`
- `which projects are blocked?`

Recorded requirements store quantity, source, notes, and acceptable substitutes. Substitutes are only used when explicitly recorded, such as `add ESP32-C3 as required part for DroneHive quantity 1 substitute ESP32-S3`.

BOM imports populate project requirements with source `BOM import`, so readiness queries after an import compare the BOM requirements against actual inventory.

## Category Classification

When inventory is added without an explicit category, the assistant uses the shared hardware category classifier before committing. The preview shows the proposed category and confidence where a rule matches, or warns that the category is unclear and will remain `misc` unless confirmed.

The classifier is alias/keyword driven rather than project-specific. It recognizes common electronics families such as microcontrollers, single-board computers, sensors, GPS/GNSS modules, radios, displays, audio modules, storage modules, power components, and motors/actuators. Examples include ESP32/ESP8266, Arduino, STM32, Raspberry Pi Pico, Raspberry Pi 3/4/5/Zero, NEO-M8N, LoRa/TTGO/LILYGO, TFT/OLED/LCD displays, regulators, batteries, motors, servos, audio amplifiers, and microSD modules.

Some categories also receive subcategories:

- `sensor / adc` for ADS1115 and ADC modules
- `sensor / environment` for BMP180/BMP280/BME280
- `sensor / line`, `sensor / audio`, `sensor / temperature`, `sensor / color`, or `sensor / liquid`
- `audio / amplifier` for MAX98356A/MAX98357A and amplifier modules
- `storage / microsd` for microSD and SD card modules

Existing `misc` entries can be audited with:

- `recategorize inventory`
- `clean inventory categories`

The cleanup flow previews each suggested change with confidence and requires `confirm` before updating the registry.
