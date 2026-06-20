# Desktop Control

Phase 11 gives SILVIA workstation awareness without granting destructive control.

## Safety Contract

Allowed:

- Resolve trusted folder names and aliases.
- Open folders in File Explorer.
- Discover and launch registered applications.
- Search indexed files inside trusted locations.
- Report missing paths or missing applications honestly.

Not allowed in this phase:

- Delete files.
- Rename files.
- Move files.
- Overwrite files.
- Click or type inside applications autonomously.

## Commands

| Command | Tool |
|---|---|
| `open CMD-CTR folder` | `open_location` |
| `where is Brain63` | `open_location` |
| `show trusted locations` | `list_locations` |
| `find STL files` | `find_files` |
| `find python files in CMD-CTR` | `find_files` |
| `show recent files` | `recent_files` |
| `open VS Code` | `open_app` |
| `open obs` | `open_app` |
| `open unity hub` | `open_app` |
| `show installed apps` | `list_apps` |
| `scan installed apps` | `scan_apps` |
| `show app blender` | `show_app` |

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/desktop/locations` | List trusted locations |
| `POST /api/desktop/locations` | Register or update a trusted location |
| `GET /api/desktop/files` | Search indexed files |
| `GET /api/desktop/recent-files` | Show newest indexed files |
| `POST /api/desktop/open/location` | Open a trusted folder |
| `GET /api/desktop/apps` | List registered applications |
| `POST /api/desktop/apps/scan` | Rescan installed applications |
| `GET /api/desktop/apps/{name}` | Show application matches |
| `POST /api/desktop/apps` | Register or update an application |
| `POST /api/desktop/open/app` | Launch a registered application |

## App Launch Resolution

Application-aware commands route through the discovered registry before legacy action aliases. The resolver attempts shortcuts, executable paths, URI protocols, and web URLs in order, and only reports success after a launch handoff succeeds.

## UI

The Command Center right rail includes a Files & Applications section with:

- Folders
- Recent files
- Apps
- Search results
