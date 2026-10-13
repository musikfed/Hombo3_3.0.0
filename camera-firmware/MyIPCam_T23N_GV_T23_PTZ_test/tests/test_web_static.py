#!/usr/bin/env python3
"""Static regression checks for MyIPCam Stage2."""
from pathlib import Path
import sys
root=Path(sys.argv[1] if len(sys.argv)>1 else Path(__file__).parents[1]/"web")
index=(root/"index.html").read_text(encoding="utf-8")
boot=(root/"boot.js").read_text(encoding="utf-8")
app=(root/"app.js").read_text(encoding="utf-8")
checks={
 "branding":"MyIPCam OS 3.1" in index,
 "login gate":'id="loginGate"' in index,
 "camera page":'data-view="camera"' in index,
 "video page":'data-view="video"' in index,
 "audio page":'data-view="audio"' in index,
 "vpn page":'data-view="vpn"' in index,
 "session login":"/x/login.cgi" in boot,
 "session status":"/x/session-status.cgi" in boot,
 "same-origin cookies":'credentials:"same-origin"' in boot and 'credentials:"same-origin"' in app,
 "PTZ endpoint":"/x/json-motor.cgi" in app,
 "hardware H264":"H264" in app,
 "no Tuya cloud URL":"tuya" not in (index+boot+app).lower(),
}
bad=[k for k,v in checks.items() if not v]
for k,v in checks.items(): print(("PASS" if v else "FAIL")+": "+k)
if bad: raise SystemExit("Static web tests failed: "+", ".join(bad))
