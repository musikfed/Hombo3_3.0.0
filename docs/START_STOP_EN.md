# Hombo3 — safe project start and stop, Linux and Windows

The existing launchers `START_HOMBO3_LINUX.sh`,
`START_HOMBOWIFI_LINUX.sh`, `START_HOMBO3.cmd` and
`START_HOMBOWIFI.cmd` are retained unchanged.

Linux: `bash start.sh` (foreground), `bash stop.sh` (second terminal).
Windows PowerShell: `.\start.ps1`, `.\stop.ps1` (second terminal).
Setup first using the existing project setup launcher.

A stop sends `POST /api/stop` to the local Hombo3 server (robot motor
STOP relayed to ESP32), confirms HTTP success, and ONLY THEN stops this
checkout's backend process. If the robot STOP request fails, the backend
is **not** terminated — physically secure the robot first. Other Python
projects, camera firmware, board and VPN/SSH are not modified.

Hombo3 Robot Control Center is distinct from the T23N camera WIFICAM
web UI on port 8090 and the YadroKreator firmware factory on port 62404.
