# EN: Async robot HTTP API: drive/sensors/audio telemetry, OTA, Wi-Fi failover and token auth.
# RU: Асинхронный API робота: движение/датчики/звук, OTA, резервный Wi-Fi и токен.
import asyncio, json, time, socket, machine, gc
from board_config import *
import ota_runtime, ota_core

_REASON={200:"OK",400:"Bad Request",401:"Unauthorized",404:"Not Found",405:"Method Not Allowed",413:"Payload Too Large",422:"Unprocessable Entity",500:"Internal Server Error",503:"Service Unavailable"}


def _query(path):
    if "?" not in path:return path,{}
    p,q=path.split("?",1); out={}
    for item in q.split("&"):
        if "=" in item:
            k,v=item.split("=",1); out[k]=v.replace("%2F","/").replace("%2E",".").replace("%20"," ")
    return p,out


async def _read_exact(reader,n):
    data=bytearray()
    while len(data)<n:
        chunk=await reader.read(n-len(data))
        if not chunk: break
        data.extend(chunk)
    return bytes(data)


async def _request(reader):
    line=await reader.readline()
    if not line:return None
    parts=line.decode().strip().split()
    if len(parts)<2:return None
    method,path=parts[0],parts[1]; headers={}
    while True:
        line=await reader.readline()
        if not line or line in (b"\r\n",b"\n"):break
        text=line.decode().strip()
        if ":" in text:
            k,v=text.split(":",1); headers[k.lower().strip()]=v.strip()
    length=int(headers.get("content-length","0") or 0)
    if length>2*1024*1024: raise ValueError("payload too large")
    body=await _read_exact(reader,length) if length else b""
    return method,path,headers,body


async def _send(writer,code,payload,content_type="application/json; charset=utf-8"):
    body=payload if isinstance(payload,(bytes,bytearray)) else json.dumps(payload).encode()
    header=("HTTP/1.1 %d %s\r\nConnection: close\r\nCache-Control: no-store\r\nContent-Type: %s\r\nContent-Length: %d\r\n\r\n" % (code,_REASON.get(code,""),content_type,len(body))).encode()
    writer.write(header); await writer.drain()
    if body: writer.write(body); await writer.drain()


class RobotServer:
    def __init__(self,wifi,motion,sensors,audio,power):
        self.wifi=wifi; self.motion=motion; self.sensors=sensors; self.audio=audio; self.power=power

    def _authorized(self,headers):
        token=str(getattr(self.wifi,"api_token","") or "")
        if not token:
            return True
        supplied=str(headers.get("x-api-token","") or "")
        if not supplied:
            auth=str(headers.get("authorization","") or "")
            if auth.lower().startswith("bearer "):
                supplied=auth[7:].strip()
        return supplied==token

    def telemetry(self):
        m=self.motion; s=self.sensors; age=m.command_age_ms()
        left=m.current_left_pwm; right=m.current_right_pwm
        direction=lambda p:"forward" if p>0 else "reverse" if p<0 else "stopped"
        power=self.power.read()
        wifi=self.wifi.status()
        out={"ok":True,"project":PROJECT_NAME,"runtime_version":RUNTIME_VERSION,"board":BOARD_NAME,
          "ip":self.wifi.ip(),"wifi_rssi":self.wifi.rssi(),"wifi_ssid":wifi.get("ssid",""),"wifi_mode":wifi.get("mode","offline"),"uptime_ms":time.ticks_ms(),
          "front_cm":s.front_cm,"rear_cm":s.rear_cm,"third_cm":s.third_cm,"tof_mm":s.tof_mm,"tof_ok":s.tof_ok,
          "target_left_percent":m.target_left_percent,"target_right_percent":m.target_right_percent,
          "current_left_pwm":left,"current_right_pwm":right,"pwm_limit":m.runtime_max_pwm,"raw_pwm_mode":m.raw_pwm_mode,
          "sensor_safety_enabled":m.sensor_safety_enabled,"ramp_step_pwm":m.ramp_step_pwm,"ramp_period_ms":m.ramp_period_ms,
          "front_stop_cm":m.front_stop_cm,"rear_stop_cm":m.rear_stop_cm,"tof_stop_mm":m.tof_stop_mm,
          "target_left_raw_pwm":m.target_left_raw_pwm,"target_right_raw_pwm":m.target_right_raw_pwm,
          "left_direction":direction(left),"right_direction":direction(right),
          "left_in1":left>0,"left_in2":left<0,"right_in1":right>0,"right_in2":right<0,
          "left_pwm":abs(left),"right_pwm":abs(right),"ain1":left>0,"ain2":left<0,"bin1":right>0,"bin2":right<0,
          "pwma":abs(left),"pwmb":abs(right),"stby":True,"audio_active":self.audio.active,
          "active_sensor_slot":s.active_sensor_slot,"last_stop_reason":m.last_stop_reason,"command_age_ms":age,
          "command_expired":age>m.ttl_ms,"emergency_stop":m.emergency_stop,"last_seq":m.last_seq}
        out.update(power)
        return out

    async def dispatch(self,method,raw_path,headers,body):
        path,q=_query(raw_path); m=self.motion
        if method=="GET" and path in ("/api/status","/api/telemetry"):
            return 200,self.telemetry()
        if method=="GET" and path=="/api/auth/check":
            return (200,{"ok":True,"auth":"token" if self.wifi.api_token else "disabled"}) if self._authorized(headers) else (401,{"ok":False,"error":"invalid token"})

        # Everything below can alter state or expose configuration and therefore requires the token when configured.
        if not self._authorized(headers):
            return 401,{"ok":False,"error":"invalid or missing API token"}

        if method=="POST" and path=="/api/command":
            d=json.loads(body or b"{}"); seq=d.get("seq",m.last_seq+1); m.command(int(d.get("left",0)),int(d.get("right",0)),int(d.get("ttl_ms",DEFAULT_COMMAND_TTL_MS)),int(seq)); return 200,{"ok":True,"seq":seq,"accepted_left":d.get("left",0),"accepted_right":d.get("right",0)}
        if method=="POST" and path=="/api/test/pwm":
            d=json.loads(body or b"{}"); seq=d.get("seq",m.last_seq+1); m.pwm_test(int(d.get("left_pwm",0)),int(d.get("right_pwm",0)),bool(d.get("sensor_safety",True)),int(d.get("ttl_ms",1500)),int(seq)); return 200,{"ok":True,"seq":seq,"accepted_left_pwm":d.get("left_pwm",0),"accepted_right_pwm":d.get("right_pwm",0),"sensor_safety_enabled":bool(d.get("sensor_safety",True)),"mode":"raw_pwm_test"}
        if path=="/api/tuning" and method=="GET": return 200,m.tuning()
        if path=="/api/tuning" and method=="POST": m.apply_tuning(json.loads(body or b"{}")); return 200,m.tuning()
        if path=="/api/stop" and method=="POST": m.hard_stop("remote stop endpoint",emergency=False); m.sensor_safety_enabled=True; m.last_command_ms=time.ticks_ms(); return 200,{"ok":True,"stopped":True}

        if path=="/api/wifi/status" and method=="GET":
            return 200,{"ok":True,**self.wifi.status()}
        if path=="/api/wifi/config" and method=="POST":
            d=json.loads(body or b"{}")
            result=self.wifi.configure_networks(d.get("networks",[]))
            asyncio.create_task(self._reconnect_later())
            return 200,{"ok":True,"wifi":result,"reconnecting":True}
        if path=="/api/wifi/reconnect" and method=="POST":
            asyncio.create_task(self._reconnect_later())
            return 200,{"ok":True,"reconnecting":True}

        if path=="/api/update/status" and method=="GET":
            st=ota_core.status(); st.update({"ok":True,"project":PROJECT_NAME,"runtime_version":RUNTIME_VERSION,"board":BOARD_NAME,"runtime_ota_available":True,"runtime_transaction":ota_runtime.status(),"free_heap":gc.mem_free(),"wifi":self.wifi.status(),"power":self.power.read()}); return 200,st
        if path=="/api/update/runtime/begin" and method=="POST": m.hard_stop("runtime OTA",emergency=False); return 200,ota_runtime.begin()
        if path=="/api/update/runtime/file" and method in ("POST","PUT"): return 200,ota_runtime.stage_file(q.get("path",""),body,q.get("sha256",""))
        if path=="/api/update/runtime/commit" and method=="POST":
            d=json.loads(body or b"{}"); result=ota_runtime.commit(d.get("files",[])); asyncio.create_task(self._reset_later()); return 200,result
        if path=="/api/update/runtime/rollback" and method=="POST": result=ota_runtime.rollback(); asyncio.create_task(self._reset_later()); return 200,result
        if path=="/api/update/core/begin" and method=="POST":
            m.hard_stop("core OTA",emergency=False); d=json.loads(body or b"{}"); return 200,ota_core.begin(int(d.get("size",0)),str(d.get("sha256","")))
        if path=="/api/update/core/chunk" and method in ("POST","PUT"): return 200,ota_core.write_block(int(q.get("block","0")),body)
        if path=="/api/update/core/finish" and method=="POST": return 200,ota_core.finish()
        if path=="/api/update/core/reboot" and method=="POST": asyncio.create_task(self._reset_later()); return 200,{"ok":True,"rebooting":True}
        return 404,{"ok":False,"error":"not found"}

    async def _reconnect_later(self):
        await asyncio.sleep_ms(500)
        try: await self.wifi.reconnect()
        except Exception as exc: print("wifi reconnect:",exc)

    async def _reset_later(self):
        await asyncio.sleep_ms(500); machine.reset()

    async def client(self,reader,writer):
        try:
            req=await asyncio.wait_for(_request(reader),3)
            if req is None:return
            method,path,headers,body=req
            try: code,payload=await self.dispatch(method,path,headers,body)
            except ValueError as exc: code,payload=422,{"ok":False,"error":str(exc)}
            except Exception as exc: code,payload=500,{"ok":False,"error":str(exc)}
            await _send(writer,code,payload)
        except Exception:
            pass
        finally:
            try: writer.close(); await writer.wait_closed()
            except Exception: pass

    async def serve(self): return await asyncio.start_server(self.client,"0.0.0.0",HTTP_PORT)

    async def discovery(self):
        sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); sock.bind(("0.0.0.0",DISCOVERY_PORT)); sock.setblocking(False)
        while True:
            try:
                data,addr=sock.recvfrom(256)
                if data.strip()==b"HOMBOWIFI_DISCOVER":
                    payload=json.dumps({"project":PROJECT_NAME,"version":RUNTIME_VERSION,"board":BOARD_NAME,"ip":self.wifi.ip(),"http_port":HTTP_PORT,"audio_port":AUDIO_PORT,"wifi_mode":self.wifi.mode}).encode(); sock.sendto(payload,addr)
            except OSError: pass
            await asyncio.sleep_ms(100)
