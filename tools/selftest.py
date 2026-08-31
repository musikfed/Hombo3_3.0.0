"""Host-side Hombo3 release self-test. No hardware required."""
from __future__ import annotations
import importlib.util, os, sys, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def check(ok,msg):
    if not ok: raise AssertionError(msg)
    print('PASS',msg)

def test_vl53():
    p=ROOT/'firmware/hombowifi_s3_micropython/device/vl53l0x.py'
    spec=importlib.util.spec_from_file_location('hombo_vl53',p); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    class FakeI2C:
        def __init__(self):
            self.m={0xC0:0xEE,0xC1:0xAA,0xC2:0x10,0x92:0x8F,0x13:0x07,0x1E:0x01,0x1F:0xF4}
            for i in range(6): self.m[0xB0+i]=0xFF
        def writeto_mem(self,addr,reg,data):
            for i,b in enumerate(data): self.m[reg+i]=b
        def readfrom_mem(self,addr,reg,n):
            out=[]
            for i in range(n):
                r=reg+i
                if r==0x83 and self.m.get(r,0)==0: out.append(1)
                elif r==0x00 and self.m.get(r,0)&1: out.append(0)
                else: out.append(self.m.get(r,0))
            return bytes(out)
    # CPython lacks MicroPython ticks helpers; emulate them for driver logic.
    if not hasattr(time,'ticks_ms'): time.ticks_ms=lambda: int(time.monotonic()*1000)
    if not hasattr(time,'ticks_diff'): time.ticks_diff=lambda a,b:a-b
    if not hasattr(time,'sleep_ms'): time.sleep_ms=lambda ms: time.sleep(ms/1000)
    tof=mod.VL53L0X(FakeI2C(),io_timeout_ms=50)
    check(tof.range==500,'VL53L0X driver initializes and returns a bounded single-shot range')

def test_vectorprobe():
    from backend.app.database import init_database
    init_database()
    from backend.app.mapping import VectorProbeEngine
    with tempfile.TemporaryDirectory() as td:
        e=VectorProbeEngine(path=Path(td)/'map.json')
        e.clear_reference()
        # 4x3 m room and a charger zone near the east wall.
        walls=[((-2,-1.5),(2,-1.5)),((2,-1.5),(2,1.5)),((2,1.5),(-2,1.5)),((-2,1.5),(-2,-1.5))]
        for i,(a,b) in enumerate(walls): e.add_wall({'id':f'w{i}','name':f'wall{i}','a':{'x_m':a[0],'y_m':a[1]},'b':{'x_m':b[0],'y_m':b[1]},'kind':'wall'})
        e.add_zone({'id':'charger','name':'Зарядка','kind':'charger','points':[{'x_m':1.35,'y_m':-.35},{'x_m':1.8,'y_m':-.35},{'x_m':1.8,'y_m':.35},{'x_m':1.35,'y_m':.35}]})
        e.set_pose(0,0,0)
        route=e.plan_to_zone('Зарядка')
        check(route['ok'] and len(route['route'])>=2,'VectorProbe plans a path to a named charger zone')
        hint=e.steering_hint(route['zone']['target'])
        check('suggested_heading_deg' in hint,'VectorProbe produces attraction/repulsion steering hint')
        state=e.state()
        check(state['meta']['vector_probe_ready'],'VectorProbe reference geometry is marked ready')

def test_contracts():
    d=ROOT/'firmware/hombowifi_s3_micropython/device'
    ota=(d/'ota_runtime.py').read_text('utf-8')
    boot=(d/'boot.py').read_text('utf-8')
    provision=(ROOT/'tools/provision_device.py').read_text('utf-8')
    check("'boot.py'" not in ota.split('ALLOWED={',1)[1].split('}',1)[0],'normal Wi-Fi OTA cannot replace stable boot.py')
    check('ota_pending.json' in ota and 'AUTO-ROLLBACK' in boot,'runtime OTA has pending confirmation and automatic boot rollback')
    check('--flash-port' in provision and '--runtime-port' in provision,'USB provisioner separates flash COM and runtime/REPL COM')
    check((ROOT/'frontend/dist/index.html').exists() and any((ROOT/'frontend/dist/assets').glob('*.js')),'bundled production web panel exists without npm build dependency')

def main():
    test_contracts(); test_vl53(); test_vectorprobe(); print('SELFTEST OK')
if __name__=='__main__': main()
