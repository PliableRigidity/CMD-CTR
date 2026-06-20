# Application Registry

The application registry lets SILVIA discover and launch local workstation applications safely.

Phase 11C no longer depends only on manually coded app aliases. SILVIA scans Windows application sources, persists discovered entries, generates aliases, and launches through a resolver chain.

## Data Model

The `app_registry` table stores:

- `name`
- `normalized_name`
- `executable`
- `executable_path`
- `shortcut_path`
- `launch_command`
- `aliases`
- `category`
- `description`
- `source`
- `launch_type`
- `confidence`
- `last_seen`

Availability is checked at read time by verifying a shortcut, executable path, command on `PATH`, URI protocol, or web fallback.

## Discovery Sources

`scan installed apps` / `rescan apps` reads:

- Start Menu shortcuts in `C:\ProgramData\Microsoft\Windows\Start Menu\Programs`
- User Start Menu shortcuts in `%APPDATA%\Microsoft\Windows\Start Menu\Programs`
- User and Public Desktop shortcuts
- Windows uninstall registry keys under HKLM, HKCU, and WOW6432Node
- Bounded common install path scans in Program Files and AppData

Microsoft Store app discovery is best-effort through shortcuts when Store apps expose Start Menu entries.

## Alias Generation

Aliases are generated from normalized names, compact names, acronyms, vendor-stripped names, and common workstation naming patterns.

Examples:

- `OBS Studio` -> `obs studio`, `obs`
- `Unity Hub` -> `unity hub`, `unity`
- `Autodesk Fusion 360` -> `fusion 360`, `fusion360`, `fusion`
- `Visual Studio Code` -> `visual studio code`, `vs code`, `vscode`, `code`

Manual entries can still be added through `POST /api/desktop/apps` or:

`add Blender app at C:\Program Files\Blender Foundation\Blender\blender.exe`

## Launch Rules

SILVIA searches the registry by exact name, alias, prefix, and partial match. If multiple exact matches exist, it asks the user to choose.

Launch methods are attempted in this order:

1. Shortcut launch
2. Executable path launch
3. URI protocol launch
4. Web URL fallback
5. Structured failure with searched registry details

Seeded entries remain for core workstation tools:

- VS Code
- Fusion 360
- Chrome
- KiCad
- Explorer
- Notepad

The registry should not fabricate apps. If an app is not discovered or manually registered, SILVIA reports that nothing was found and suggests `rescan apps`.
