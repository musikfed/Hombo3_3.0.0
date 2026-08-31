# EN: Hombo3 3.0 Robot Control Center runtime entry point.
# RU: Точка входа runtime Hombo3 3.0 Robot Control Center.
import asyncio, time, machine
import ota_runtime
from wifi_manager import WiFiManager
from motion import MotionController
from sensors import Sensors
from audio_service import AudioService
from power import PowerMonitor
from server import RobotServer

async def main():
    wifi=WiFiManager(); motion=MotionController(); sensors=Sensors(); audio=AudioService(); power=PowerMonitor()
    connected=await wifi.connect()
    print('Wi-Fi:','OK' if connected else 'RECOVERY AP','IP:',wifi.ip())
    server=RobotServer(wifi,motion,sensors,audio,power)
    await server.serve(); await audio.serve()
    asyncio.create_task(wifi.watchdog())
    asyncio.create_task(motion.loop(sensors))
    asyncio.create_task(sensors.loop())
    asyncio.create_task(server.discovery())
    # The runtime is considered healthy only after network fallback, HTTP, audio and
    # safety loops have all been constructed. This confirms a pending Wi-Fi OTA.
    ota_runtime.mark_boot_ok()
    while True: await asyncio.sleep(3600)

try:
    asyncio.run(main())
except Exception as exc:
    print('Hombo3 fatal runtime error:',repr(exc))
    # If this was the first boot of a new OTA transaction, record the failure and
    # reboot once. Stable boot.py will restore all .prev files automatically.
    try:
        if ota_runtime.has_pending():
            ota_runtime.record_boot_error(repr(exc))
            time.sleep(2)
            machine.reset()
    except Exception as rollback_exc:
        print('OTA failure handler:',rollback_exc)
    raise
finally:
    try: asyncio.new_event_loop()
    except Exception: pass
