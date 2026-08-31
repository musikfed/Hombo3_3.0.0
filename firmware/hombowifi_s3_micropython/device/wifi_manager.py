# EN: Multi-network Wi-Fi manager with recovery AP and persistent configuration.
# RU: Менеджер нескольких Wi-Fi сетей с аварийной точкой доступа и сохранением настроек.
import asyncio
import json
import os
import machine
import network

CONFIG_PATH = "/wifi_config.json"

try:
    import secrets as _secrets
except Exception:
    _secrets = None


def _default_networks():
    # New format first; legacy WIFI_SSID/WIFI_PASSWORD stays compatible.
    if _secrets is not None:
        value = getattr(_secrets, "WIFI_NETWORKS", None)
        if isinstance(value, (list, tuple)) and value:
            out = []
            for item in value:
                if isinstance(item, dict):
                    ssid = str(item.get("ssid", ""))
                    password = str(item.get("password", ""))
                    priority = int(item.get("priority", 0) or 0)
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    ssid = str(item[0])
                    password = str(item[1])
                    priority = int(item[2] if len(item) > 2 else 0)
                else:
                    continue
                if ssid:
                    out.append({"ssid": ssid, "password": password, "priority": priority})
            if out:
                return out
        ssid = str(getattr(_secrets, "WIFI_SSID", "") or "")
        password = str(getattr(_secrets, "WIFI_PASSWORD", "") or "")
        if ssid:
            return [{"ssid": ssid, "password": password, "priority": 100}]
    return []


def _recovery_password():
    if _secrets is None:
        return ""
    return str(getattr(_secrets, "RECOVERY_AP_PASSWORD", "") or "")


def _api_token():
    if _secrets is None:
        return ""
    return str(getattr(_secrets, "API_TOKEN", "") or "")


class WiFiManager:
    def __init__(self):
        self.wlan = network.WLAN(network.STA_IF)
        self.ap = network.WLAN(network.AP_IF)
        self.networks = self._load_networks()
        self.current_ssid = ""
        self.mode = "offline"
        self.last_error = ""
        self.ap_ssid = self._make_ap_ssid()
        self.api_token = _api_token()

    def _make_ap_ssid(self):
        try:
            suffix = machine.unique_id().hex()[-4:].upper()
        except Exception:
            suffix = "S3"
        return "Hombo3-Recovery-" + suffix

    def _load_networks(self):
        try:
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
            rows = data.get("networks", []) if isinstance(data, dict) else []
            out = []
            for item in rows:
                ssid = str(item.get("ssid", ""))
                if ssid:
                    out.append({
                        "ssid": ssid,
                        "password": str(item.get("password", "")),
                        "priority": int(item.get("priority", 0) or 0),
                    })
            if out:
                return out
        except Exception:
            pass
        return _default_networks()

    def _save_networks(self):
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"networks": self.networks}, f)
        try:
            os.remove(CONFIG_PATH)
        except OSError:
            pass
        os.rename(tmp, CONFIG_PATH)

    def public_networks(self):
        return [
            {"ssid": item.get("ssid", ""), "priority": int(item.get("priority", 0) or 0), "has_password": bool(item.get("password", ""))}
            for item in sorted(self.networks, key=lambda x: int(x.get("priority", 0) or 0), reverse=True)
        ]

    def status(self):
        return {
            "connected": self.wlan.isconnected(),
            "mode": self.mode,
            "ip": self.ip(),
            "ssid": self.current_ssid,
            "rssi": self.rssi(),
            "networks": self.public_networks(),
            "has_backup": len(self.networks) >= 2,
            "recovery_ap_active": self.ap.active(),
            "recovery_ap_ssid": self.ap_ssid if self.ap.active() else "",
            "last_error": self.last_error,
        }

    def configure_networks(self, rows):
        out = []
        if not isinstance(rows, list):
            raise ValueError("networks must be a list")
        for item in rows[:6]:
            if not isinstance(item, dict):
                continue
            ssid = str(item.get("ssid", "")).strip()
            if not ssid:
                continue
            password = item.get("password", None)
            # Blank/omitted password preserves the existing password for that SSID.
            if password is None or password == "":
                old = next((x for x in self.networks if x.get("ssid") == ssid), None)
                password = str(old.get("password", "")) if old else ""
            out.append({
                "ssid": ssid,
                "password": str(password),
                "priority": int(item.get("priority", 0) or 0),
            })
        if not out:
            raise ValueError("at least one Wi-Fi network is required")
        self.networks = sorted(out, key=lambda x: int(x.get("priority", 0) or 0), reverse=True)
        self._save_networks()
        return self.status()

    async def _connect_one(self, item, timeout_s=8):
        ssid = str(item.get("ssid", ""))
        if not ssid:
            return False
        try:
            self.wlan.disconnect()
        except Exception:
            pass
        await asyncio.sleep_ms(120)
        try:
            self.wlan.connect(ssid, str(item.get("password", "")))
        except Exception as exc:
            self.last_error = str(exc)
            return False
        for _ in range(max(1, int(timeout_s * 5))):
            if self.wlan.isconnected():
                self.current_ssid = ssid
                self.mode = "sta"
                self.last_error = ""
                if self.ap.active():
                    self.ap.active(False)
                return True
            await asyncio.sleep_ms(200)
        return False

    async def connect(self, timeout_s=20):
        self.wlan.active(True)
        try:
            self.wlan.config(pm=network.WLAN.PM_NONE)
        except Exception:
            pass
        if self.wlan.isconnected():
            self.mode = "sta"
            try:
                self.current_ssid = self.wlan.config("ssid") or self.current_ssid
            except Exception:
                pass
            return True
        rows = sorted(self.networks, key=lambda x: int(x.get("priority", 0) or 0), reverse=True)
        per_network = max(4, min(10, int(timeout_s / max(1, len(rows)))))
        for item in rows:
            if await self._connect_one(item, per_network):
                return True
        self.start_recovery_ap()
        return False

    def start_recovery_ap(self):
        try:
            self.ap.active(True)
            password = _recovery_password()
            if len(password) >= 8:
                try:
                    self.ap.config(essid=self.ap_ssid, password=password, authmode=network.AUTH_WPA2_PSK)
                except Exception:
                    self.ap.config(essid=self.ap_ssid, password=password)
            else:
                self.ap.config(essid=self.ap_ssid)
            self.mode = "recovery-ap"
        except Exception as exc:
            self.last_error = "recovery AP: " + str(exc)

    def ip(self):
        try:
            if self.wlan.isconnected():
                return self.wlan.ifconfig()[0]
            if self.ap.active():
                return self.ap.ifconfig()[0]
        except Exception:
            pass
        return "0.0.0.0"

    def rssi(self):
        try:
            return self.wlan.status("rssi") if self.wlan.isconnected() else -127
        except Exception:
            return -127

    async def reconnect(self):
        return await self.connect(20)

    async def watchdog(self):
        while True:
            if not self.wlan.isconnected():
                await self.connect(20)
            await asyncio.sleep(5)
