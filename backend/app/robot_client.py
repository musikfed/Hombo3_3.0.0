"""HTTP/raw-TCP client for Hombo3 ESP32-S3 with LAN discovery fallback."""
from __future__ import annotations
import asyncio, json, socket, struct, time
from typing import Any
import httpx
from .config import settings
from .database import log_event
from .models import DriveCommand, DriveTuningSettings, ManualVector, PwmTestCommand

DISCOVERY_PORT=32320

class RobotClient:
    def __init__(self)->None:
        self._seq=0
        self._http=httpx.AsyncClient(timeout=settings.esp32_request_timeout_s,trust_env=False)
        self._base_url=settings.esp32_base_url.rstrip('/')
        self._audio_host=settings.esp32_audio_host
        self._last_pwm_log_signature=None; self._last_pwm_log_at=0.0
    @property
    def base_url(self): return self._base_url
    @property
    def audio_host(self): return self._audio_host
    async def close(self): await self._http.aclose()

    def _discover_blocking(self):
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1); s.settimeout(.7)
        try:
            s.bind(('',0)); s.sendto(b'HOMBOWIFI_DISCOVER',('255.255.255.255',DISCOVERY_PORT))
            data,addr=s.recvfrom(2048); info=json.loads(data.decode()); return info,addr[0]
        finally:s.close()
    async def discover(self):
        try:
            info,host=await asyncio.to_thread(self._discover_blocking)
            self._base_url=f"http://{host}:{int(info.get('http_port',80))}"; self._audio_host=host
            log_event('INFO','network','Hombo3 ESP32 discovered',{'host':host,'board':info.get('board'),'version':info.get('version')})
            return info
        except Exception:return None

    async def _request(self,method,path,**kwargs):
        headers=dict(kwargs.pop('headers',{}) or {})
        if settings.esp32_api_token:
            headers.setdefault('X-API-Token',settings.esp32_api_token)
        try:return await self._http.request(method,self._base_url+path,headers=headers,**kwargs)
        except (httpx.ConnectError,httpx.ConnectTimeout,httpx.ReadTimeout):
            if await self.discover(): return await self._http.request(method,self._base_url+path,headers=headers,**kwargs)
            raise
    async def request(self,method,path,**kwargs):
        return await self._request(method,path,**kwargs)
    async def wifi_status(self):
        r=await self._request('GET','/api/wifi/status');r.raise_for_status();return r.json()
    async def wifi_configure(self,networks):
        r=await self._request('POST','/api/wifi/config',json={'networks':networks});r.raise_for_status();return r.json()
    async def telemetry(self): r=await self._request('GET','/api/telemetry');r.raise_for_status();return r.json()
    async def drive(self,command:DriveCommand):
        self._seq+=1;payload={'left':command.left,'right':command.right,'ttl_ms':command.ttl_ms,'seq':self._seq};r=await self._request('POST','/api/command',json=payload);r.raise_for_status();data=r.json();log_event('INFO','drive',f'Drive command from {command.source}',{**payload,'reply':data});return data
    async def vector(self,vector:ManualVector,source='web'):
        return await self.drive(DriveCommand(left=max(-100,min(100,vector.throttle+vector.turn)),right=max(-100,min(100,vector.throttle-vector.turn)),ttl_ms=vector.ttl_ms,source=source))
    async def pwm_test(self,command:PwmTestCommand):
        self._seq+=1;payload={'left_pwm':command.left_pwm,'right_pwm':command.right_pwm,'sensor_safety':command.sensor_safety,'ttl_ms':command.ttl_ms,'seq':self._seq};r=await self._request('POST','/api/test/pwm',json=payload);r.raise_for_status();data=r.json();sig=(int(command.left_pwm),int(command.right_pwm),bool(command.sensor_safety));now=time.monotonic()
        if sig!=self._last_pwm_log_signature or now-self._last_pwm_log_at>=2.0:log_event('INFO','pwm_test',f'Raw PWM test from {command.source}',{**payload,'reply':data});self._last_pwm_log_signature=sig;self._last_pwm_log_at=now
        return data
    async def apply_tuning(self,profile:DriveTuningSettings):
        payload={'ramp_step_pwm':profile.ramp_step_pwm,'ramp_period_ms':profile.ramp_period_ms,'max_pwm':profile.max_pwm,'front_stop_cm':profile.front_stop_cm,'rear_stop_cm':profile.rear_stop_cm,'tof_stop_mm':profile.tof_stop_mm,'sensor_safety_default':profile.sensor_safety_default};r=await self._request('POST','/api/tuning',json=payload);r.raise_for_status();data=r.json();log_event('INFO','tuning','Runtime tuning pushed to ESP32',{**payload,'reply':data});return data
    async def stop(self,source='web'):
        r=await self._request('POST','/api/stop');r.raise_for_status();data=r.json();log_event('WARNING','drive',f'STOP from {source}',data);return data
    async def send_pcm(self,pcm:bytes,sample_rate=16000):
        if not pcm:return
        if sample_rate<8000 or sample_rate>48000:raise ValueError('sample_rate must be 8000..48000')
        header=b'PCM1'+struct.pack('<II',sample_rate,len(pcm))
        try:reader,writer=await asyncio.wait_for(asyncio.open_connection(self._audio_host,settings.esp32_audio_port),timeout=3.0)
        except Exception:
            await self.discover();reader,writer=await asyncio.wait_for(asyncio.open_connection(self._audio_host,settings.esp32_audio_port),timeout=3.0)
        del reader;writer.write(header);await writer.drain()
        for off in range(0,len(pcm),4096):writer.write(pcm[off:off+4096]);await writer.drain()
        writer.close();await writer.wait_closed();log_event('INFO','audio','PCM sent to ESP32',{'bytes':len(pcm),'sample_rate':sample_rate})
