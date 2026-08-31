"""EN: Wi-Fi runtime/core updater and device-network configuration.
RU: Обновление runtime/ядра по Wi-Fi и настройка сетей контроллера.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
from .config import ROOT_DIR
from .database import log_event

DEVICE_SRC=ROOT_DIR/'firmware'/'hombowifi_s3_micropython'/'device'
CORE_DIR=ROOT_DIR/'firmware'/'core'
RUNTIME_FILES=['main.py','board_config.py','wifi_manager.py','motion.py','sensors.py','vl53l0x.py','audio_service.py','power.py','ota_runtime.py','ota_core.py','server.py']

class DeviceUpdater:
    def __init__(self,robot): self.robot=robot
    async def status(self):
        r=await self.robot.request('GET','/api/update/status');r.raise_for_status();return r.json()
    async def wifi_status(self):
        return await self.robot.wifi_status()
    async def wifi_configure(self,networks):
        result=await self.robot.wifi_configure(networks)
        log_event('WARNING','network','ESP32 Wi-Fi network list changed',{'networks':[{'ssid':x.get('ssid',''),'priority':x.get('priority',0)} for x in networks]})
        return result
    async def runtime(self):
        await self.robot.stop('runtime update')
        r=await self.robot.request('POST','/api/update/runtime/begin');r.raise_for_status()
        uploaded=[]
        for name in RUNTIME_FILES:
            data=(DEVICE_SRC/name).read_bytes();sha=hashlib.sha256(data).hexdigest()
            r=await self.robot.request('PUT',f'/api/update/runtime/file?path={name}&sha256={sha}',content=data,headers={'Content-Type':'application/octet-stream'});r.raise_for_status();uploaded.append(name)
        r=await self.robot.request('POST','/api/update/runtime/commit',json={'files':uploaded});r.raise_for_status()
        log_event('INFO','ota','MicroPython application runtime updated over Wi-Fi',{'files':uploaded})
        return {'ok':True,'files':uploaded,'rebooting':True}
    async def rollback(self):
        r=await self.robot.request('POST','/api/update/runtime/rollback');r.raise_for_status();return r.json()
    def core_files(self):
        CORE_DIR.mkdir(parents=True,exist_ok=True);return [p.name for p in sorted(CORE_DIR.glob('*.app-bin'))]
    async def core(self,filename):
        path=(CORE_DIR/filename).resolve()
        if path.parent!=CORE_DIR.resolve() or not path.exists() or path.suffix!='.app-bin':raise ValueError('app-bin not found')
        data_size=path.stat().st_size;sha=hashlib.sha256(path.read_bytes()).hexdigest()
        await self.robot.stop('core OTA')
        st=(await self.status())
        if not st.get('core_ota_available'):raise RuntimeError('Core OTA unavailable: '+str(st.get('reason','dual OTA partitions required')))
        r=await self.robot.request('POST','/api/update/core/begin',json={'size':data_size,'sha256':sha});r.raise_for_status()
        with path.open('rb') as f:
            block=0
            while True:
                chunk=f.read(4096)
                if not chunk:break
                if len(chunk)<4096:chunk+=b'\xff'*(4096-len(chunk))
                r=await self.robot.request('PUT',f'/api/update/core/chunk?block={block}',content=chunk,headers={'Content-Type':'application/octet-stream'});r.raise_for_status();block+=1
        r=await self.robot.request('POST','/api/update/core/finish');r.raise_for_status();verify=r.json()
        await self.robot.request('POST','/api/update/core/reboot')
        log_event('WARNING','ota','MicroPython core OTA completed',{'file':filename,'sha256':sha})
        return {'ok':True,'file':filename,'sha256':sha,'verify':verify,'rebooting':True}
