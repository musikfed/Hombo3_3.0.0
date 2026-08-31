"""Hombo3 3.0 release/static validation. No secrets are printed."""
from __future__ import annotations
from pathlib import Path
import ast, json, re, sys
ROOT=Path(__file__).resolve().parents[1]
D=ROOT/'firmware/hombowifi_s3_micropython/device'
EXPECTED={'PIN_LEFT_IN1':18,'PIN_LEFT_IN2':17,'PIN_LEFT_PWM':14,'PIN_RIGHT_IN1':21,'PIN_RIGHT_IN2':10,'PIN_RIGHT_PWM':12,'PIN_STBY':40,'PIN_HC_FRONT_TRIG':1,'PIN_HC_FRONT_ECHO':7,'PIN_HC_REAR_TRIG':6,'PIN_HC_REAR_ECHO':5,'PIN_HC_THIRD_TRIG':4,'PIN_HC_THIRD_ECHO':16,'PIN_I2C_SDA':8,'PIN_I2C_SCL':9,'PIN_I2S_BCLK':11,'PIN_I2S_LRCK':13,'PIN_I2S_DOUT':15,'PIN_BATTERY_ADC':2}
RUNTIME={'main.py','board_config.py','wifi_manager.py','motion.py','sensors.py','vl53l0x.py','audio_service.py','power.py','ota_runtime.py','ota_core.py','server.py'}

def assignment(text,key):
    m=re.search(rf'^\s*{re.escape(key)}\s*=\s*([^#\n]+)',text,re.M)
    if not m: raise SystemExit('Missing '+key)
    return ast.literal_eval(m.group(1).strip())

cfg=(D/'board_config.py').read_text(encoding='utf-8')
for k,v in EXPECTED.items():
    if assignment(cfg,k)!=v: raise SystemExit(f'{k} expected {v}')
if assignment(cfg,'BATTERY_CELLS')!=2 or abs(float(assignment(cfg,'BATTERY_DIVIDER_RATIO'))-4.0)>1e-6: raise SystemExit('Battery 2S / 4:1 divider contract mismatch')
used=list(EXPECTED.values())
if len(used)!=len(set(used)): raise SystemExit('Duplicate GPIO assignment')
for forbidden in (0,3,19,20,35,36,37,45,46):
    if forbidden in used: raise SystemExit(f'Reserved/risk GPIO used: {forbidden}')
for name in RUNTIME|{'boot.py','secrets.py'}:
    if not (D/name).exists(): raise SystemExit('Missing device file '+name)
# Every MicroPython file must parse as Python source.
for p in D.glob('*.py'):
    ast.parse(p.read_text(encoding='utf-8'),filename=str(p))
# Normal OTA must not overwrite stable boot or secrets, and must include the ToF driver.
ota=(D/'ota_runtime.py').read_text(encoding='utf-8')
if "'boot.py'" in re.search(r'ALLOWED\s*=\s*\{(.*?)\}',ota,re.S).group(1): raise SystemExit('boot.py must not be normal OTA')
if "'secrets.py'" in re.search(r'ALLOWED\s*=\s*\{(.*?)\}',ota,re.S).group(1): raise SystemExit('secrets.py must not be normal OTA')
if 'vl53l0x.py' not in ota or 'ota_pending.json' not in ota: raise SystemExit('OTA driver/transaction guard missing')
up=(ROOT/'backend/app/device_update.py').read_text(encoding='utf-8')
if 'boot.py' in re.search(r'RUNTIME_FILES\s*=\s*\[(.*?)\]',up,re.S).group(1): raise SystemExit('backend updater must not overwrite boot.py')
if 'vl53l0x.py' not in up: raise SystemExit('backend updater missing VL53L0X')
prov=(ROOT/'tools/provision_device.py').read_text(encoding='utf-8')
if '--flash-port' not in prov or '--runtime-port' not in prov: raise SystemExit('dual-port provisioner missing')
# Version consistency.
version=(ROOT/'VERSION').read_text(encoding='utf-8').strip()
if version!='3.0.0': raise SystemExit('VERSION must be 3.0.0')
if '3.0.0' not in cfg: raise SystemExit('firmware version mismatch')
# Secret hygiene contract.
gitignore=(ROOT/'.gitignore').read_text(encoding='utf-8')
for required in ('.env','secrets.py','node_modules','.venv','__pycache__'):
    if required not in gitignore: raise SystemExit('.gitignore missing '+required)
if not (ROOT/'.env').exists() or not (D/'secrets.py').exists(): raise SystemExit('private runtime config missing')
if (ROOT/'firmware/legacy_arduino_s3_uno/secrets.h').exists(): raise SystemExit('legacy secrets.h must not be packaged')
print('OK: Hombo3 3.0 pin contract, battery ADC, ToF driver, transactional OTA, dual-COM provisioning, version and secret hygiene')
