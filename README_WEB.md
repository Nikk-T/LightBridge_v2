# LightBridge Web Interface

Two independent Flask apps — dashboard control on port 5000, XLS import tool on port 5001.

## Project Structure

```
LightBridgeWEB/
├── app.py                        ← Dashboard (port 5000)
├── bridge_service.py             ← WebSocket bridge (existing)
├── serialdriver.py               ← SLS960 serial driver (existing)
├── mdp_protocol.py               ← MDP packet builder (existing)
├── maps.yaml                     ← Shared config (read by both apps)
├── templates/
│   └── index.html                ← Dashboard UI
├── import_app/
│   ├── import_app.py             ← Import tool (port 5001)
│   └── templates/
│       └── import.html           ← Import UI
└── requirements.txt
```

## Setup

```bash
pip install -r requirements.txt
```

## Running

Three services, three terminals (or use a process manager):

**Terminal 1 — WebSocket bridge:**
```bash
python bridge_service.py
```

**Terminal 2 — Dashboard (port 5000):**
```bash
python app.py
# → http://<pi-ip>:5000
```

**Terminal 3 — Import tool (port 5001):**
```bash
python import_app/import_app.py
# → http://<pi-ip>:5001
```

## Apps

### Dashboard — port 5000
- Unit grid with status control (paginated, 100 units per page)
- Floor highlight, scene control, direct channel RGB
- Live ONLINE/OFFLINE badge with bridge uptime

### Import Tool — port 5001
- Drag-and-drop XLS / XLSX / CSV
- Auto-detects Unit ID, Channels, Floor, Status columns
- Preview table + column mapper
- Generates and previews maps.yaml before saving
- Auto-backup of existing maps.yaml on save

## Running as Services (optional)

`/etc/systemd/system/lightbridge-dashboard.service`:
```ini
[Unit]
Description=LightBridge Dashboard
After=network.target

[Service]
WorkingDirectory=/home/pi/LightBridgeWEB
ExecStart=/usr/bin/python3 app.py
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/lightbridge-import.service`:
```ini
[Unit]
Description=LightBridge Import Tool
After=network.target

[Service]
WorkingDirectory=/home/pi/LightBridgeWEB/import_app
ExecStart=/usr/bin/python3 import_app.py
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable lightbridge-dashboard lightbridge-import
sudo systemctl start lightbridge-dashboard lightbridge-import
```
