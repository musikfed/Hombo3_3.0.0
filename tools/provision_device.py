"""Hombo3 one-time USB provisioner for ESP32-S3 N16R8.
Separates FLASH/bootloader COM from MicroPython RUNTIME/REPL COM.
"""
from __future__ import annotations
import argparse, subprocess, sys, time, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DEVICE=ROOT/'firmware'/'hombowifi_s3_micropython'/'device'
CACHE=ROOT/'firmware'/'cache'; CACHE.mkdir(parents=True,exist_ok=True)
URL='https://micropython.org/resources/firmware/ESP32_GENERIC_S3-SPIRAM_OCT-20260406-v1.28.0.bin'
BIN=CACHE/'ESP32_GENERIC_S3-SPIRAM_OCT-20260406-v1.28.0.bin'
UPLOAD_ORDER=['board_config.py','motion.py','vl53l0x.py','sensors.py','audio_service.py','power.py','ota_runtime.py','ota_core.py','secrets.py','wifi_manager.py','server.py','boot.py','main.py']

def run(*args, capture=False, check=True):
    print('+',' '.join(map(str,args)))
    return subprocess.run(list(map(str,args)),check=check,text=True,capture_output=capture)

def ports():
    try:
        from serial.tools import list_ports
        return [p.device for p in list_ports.comports()]
    except Exception: return []

def repl_ok(port):
    try:
        r=run(sys.executable,'-m','mpremote','connect',port,'exec',"print('__HOMBO_REPL__')",capture=True,check=False)
        return r.returncode==0 and '__HOMBO_REPL__' in (r.stdout or '')
    except Exception: return False

def wait_runtime(preferred, timeout=35):
    deadline=time.time()+timeout
    while time.time()<deadline:
        candidates=[]
        if preferred and preferred.lower()!='auto': candidates.append(preferred)
        for p in ports():
            if p not in candidates: candidates.append(p)
        for p in candidates:
            if repl_ok(p):
                print('MicroPython REPL:',p); return p
        time.sleep(1)
    raise RuntimeError('MicroPython REPL not found. Press EN once, rescan COM ports, and use --runtime-port COMx.')

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--flash-port',help='esptool/bootloader port, e.g. COM4')
    ap.add_argument('--runtime-port',default='auto',help='MicroPython REPL port, e.g. COM5 or auto')
    ap.add_argument('--skip-erase',action='store_true')
    ap.add_argument('--skip-flash',action='store_true',help='Upload runtime only; MicroPython must already be installed')
    ns=ap.parse_args()
    if not ns.skip_flash:
        if not ns.flash_port: ap.error('--flash-port is required unless --skip-flash is used')
        if not BIN.exists():
            print('Downloading official MicroPython ESP32_GENERIC_S3 SPIRAM_OCT v1.28.0...')
            urllib.request.urlretrieve(URL,BIN)
        if not ns.skip_erase: run(sys.executable,'-m','esptool','--chip','esp32s3','--port',ns.flash_port,'erase_flash')
        run(sys.executable,'-m','esptool','--chip','esp32s3','--port',ns.flash_port,'--baud','460800','write_flash','0',BIN)
        print('Flash complete. Waiting for the independent MicroPython REPL port...')
        time.sleep(2)
    runtime=wait_runtime(ns.runtime_port)
    # Verify exact family before copying robot files.
    r=run(sys.executable,'-m','mpremote','connect',runtime,'exec',"import os;print('__MACHINE__='+os.uname().machine)",capture=True)
    machine=(r.stdout or '')
    if 'ESP32S3' not in machine.upper().replace('-',''):
        raise RuntimeError('Runtime port does not report ESP32-S3: '+machine.strip())
    for name in UPLOAD_ORDER:
        p=DEVICE/name
        if not p.exists(): raise FileNotFoundError(p)
        run(sys.executable,'-m','mpremote','connect',runtime,'fs','cp',p,':'+name)
    run(sys.executable,'-m','mpremote','connect',runtime,'fs','ls')
    run(sys.executable,'-m','mpremote','connect',runtime,'reset')
    print('DONE. Flash port and runtime port were treated independently.')
    print('Future Hombo3 application updates: Wi-Fi OTA. USB remains recovery only.')
if __name__=='__main__': main()
