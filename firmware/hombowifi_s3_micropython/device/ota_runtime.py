# EN: Transactional Hombo3 application OTA with automatic boot rollback.
# RU: Транзакционное обновление Hombo3 с автоматическим откатом при неуспешной загрузке.
import os, hashlib, binascii, json

STAGE='/.hombo3_ota'
PENDING='/ota_pending.json'
LAST_FAILURE='/ota_last_failure.json'
# boot.py and secrets.py are intentionally immutable during normal Wi-Fi OTA.
ALLOWED={
 'main.py','board_config.py','wifi_manager.py','motion.py','sensors.py','vl53l0x.py',
 'audio_service.py','power.py','ota_runtime.py','ota_core.py','server.py'
}

def _exists(path):
    try: os.stat(path); return True
    except OSError: return False

def _mkdir(path):
    if not _exists(path):
        try: os.mkdir(path)
        except OSError: pass

def _write_json(path,data):
    tmp=path+'.tmp'
    with open(tmp,'w') as f: json.dump(data,f)
    try: os.remove(path)
    except OSError: pass
    os.rename(tmp,path)

def _read_json(path):
    try:
        with open(path,'r') as f: return json.load(f)
    except Exception: return None

def begin():
    _mkdir(STAGE)
    for name in ALLOWED:
        p=STAGE+'/'+name
        if _exists(p):
            try: os.remove(p)
            except OSError: pass
    return {'ok':True,'stage':STAGE,'allowed':sorted(ALLOWED)}

def stage_file(name,data,expected_sha=''):
    if name not in ALLOWED: raise ValueError('file not allowed')
    digest=binascii.hexlify(hashlib.sha256(data).digest()).decode()
    if expected_sha and digest.lower()!=expected_sha.lower(): raise ValueError('sha256 mismatch')
    _mkdir(STAGE)
    with open(STAGE+'/'+name,'wb') as f: f.write(data)
    return {'ok':True,'file':name,'bytes':len(data),'sha256':digest}

def commit(files):
    names=[]
    for name in files:
        if name not in ALLOWED: raise ValueError('file not allowed: '+name)
        if name not in names: names.append(name)
    if 'main.py' not in names: raise ValueError('main.py must be part of a runtime OTA transaction')
    for name in names:
        if not _exists(STAGE+'/'+name): raise ValueError('missing staged file: '+name)
    changed=[]
    try:
        for name in names:
            staged=STAGE+'/'+name; current='/'+name; previous=current+'.prev'
            if _exists(previous): os.remove(previous)
            if _exists(current): os.rename(current,previous)
            os.rename(staged,current); changed.append(name)
        _write_json(PENDING,{'state':'pending','attempts':0,'files':changed,'error':''})
        return {'ok':True,'updated':changed,'rollback_available':True,'boot_confirmation_required':True}
    except Exception:
        # Immediate rollback if the transaction itself failed before reboot.
        for name in reversed(changed):
            current='/'+name; previous=current+'.prev'
            try:
                if _exists(current): os.remove(current)
                if _exists(previous): os.rename(previous,current)
            except Exception: pass
        try: os.remove(PENDING)
        except OSError: pass
        raise

def has_pending():
    return _exists(PENDING)

def record_boot_error(message):
    data=_read_json(PENDING) or {'state':'pending','attempts':1,'files':[]}
    data['error']=str(message)[:300]
    _write_json(PENDING,data)

def mark_boot_ok():
    data=_read_json(PENDING)
    if data:
        data['state']='confirmed'
        try: os.remove(PENDING)
        except OSError: pass
    return {'ok':True,'confirmed':bool(data)}

def rollback():
    restored=[]
    # Prefer the last transaction list, otherwise scan the whitelist.
    data=_read_json(PENDING) or {}
    names=data.get('files') or list(ALLOWED)
    for name in names:
        if name not in ALLOWED: continue
        current='/'+name; previous=current+'.prev'
        if _exists(previous):
            if _exists(current): os.remove(current)
            os.rename(previous,current); restored.append(name)
    try: os.remove(PENDING)
    except OSError: pass
    return {'ok':True,'restored':restored}

def status():
    return {
        'pending':_read_json(PENDING),
        'last_failure':_read_json(LAST_FAILURE),
        'allowed':sorted(ALLOWED),
        'boot_file_ota':False,
    }
