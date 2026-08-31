# Hombo3 stable boot guard. Normal Wi-Fi OTA NEVER replaces this file.
# EN: motor-safe boot + automatic rollback of an unconfirmed runtime transaction.
# RU: безопасная загрузка моторов + автооткат неподтверждённого runtime OTA.
import os, json
from machine import Pin

# Fixed Hombo3 3.0 soldering contract. Keep this independent of board_config.py so
# a broken OTA board_config can still be rolled back before application imports.
_STBY=40; _LEFT_IN1=18; _LEFT_IN2=17; _RIGHT_IN1=21; _RIGHT_IN2=10
_PENDING='/ota_pending.json'; _LAST_FAILURE='/ota_last_failure.json'

def _exists(p):
    try: os.stat(p); return True
    except OSError: return False

def _write_json(path,data):
    tmp=path+'.tmp'
    with open(tmp,'w') as f: json.dump(data,f)
    try: os.remove(path)
    except OSError: pass
    os.rename(tmp,path)

def _motor_safe():
    for gpio in (_STBY,_LEFT_IN1,_LEFT_IN2,_RIGHT_IN1,_RIGHT_IN2):
        try: Pin(gpio,Pin.OUT,value=0)
        except Exception as exc: print('boot pin safety',gpio,exc)

def _ota_guard():
    if not _exists(_PENDING): return
    try:
        with open(_PENDING,'r') as f: data=json.load(f)
    except Exception as exc:
        print('OTA marker unreadable:',exc); return
    attempts=int(data.get('attempts',0) or 0)
    files=list(data.get('files',[]) or [])
    if attempts <= 0:
        data['attempts']=1
        _write_json(_PENDING,data)
        print('Hombo3 OTA: first boot, awaiting main.py confirmation')
        return
    restored=[]
    for name in files:
        # Simple basename defense; marker is generated locally by ota_runtime.py.
        if '/' in name or '\\' in name or name in ('boot.py','secrets.py'): continue
        current='/'+name; previous=current+'.prev'
        try:
            if _exists(previous):
                if _exists(current): os.remove(current)
                os.rename(previous,current); restored.append(name)
        except Exception as exc: print('OTA rollback file',name,exc)
    failure={'rolled_back':True,'files':restored,'error':str(data.get('error','')),'attempts':attempts}
    try: _write_json(_LAST_FAILURE,failure)
    except Exception: pass
    try: os.remove(_PENDING)
    except OSError: pass
    print('Hombo3 OTA AUTO-ROLLBACK:',restored)

_motor_safe()
_ota_guard()

# MicroPython core/partition rollback confirmation, when a dual-OTA core is used.
try:
    import esp32
    esp32.Partition.mark_app_valid_cancel_rollback()
except Exception:
    pass
