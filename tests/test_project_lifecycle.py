"""Do not terminate robot control without commanding ESP32 motor STOP."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class LifecycleSafetyTests(unittest.TestCase):
    def test_linux_stops_motors_before_backend(self):
        s = (ROOT / "stop.sh").read_text()
        self.assertIn("/api/stop", s)
        self.assertIn('{"voice":false}', s)
        self.assertLess(s.index("/api/stop"), s.index('kill -TERM "$PID"'))
        self.assertNotIn('killall', s)
        self.assertNotIn('pkill', s)
        self.assertIn("BACKEND", s)

    def test_windows_stops_motors_before_backend(self):
        s = (ROOT / "stop.ps1").read_text()
        self.assertIn('/api/stop', s)
        self.assertLess(s.index('/api/stop'), s.index('Stop-Process -Id'))
        self.assertIn('ExecutablePath', s)
        self.assertNotIn('taskkill', s)

    def test_existing_launchers_reused(self):
        self.assertIn('START_HOMBO3_LINUX.sh', (ROOT / 'start.sh').read_text())
        self.assertIn('scripts/run.ps1', (ROOT / 'start.ps1').read_text())

if __name__ == '__main__':
    unittest.main()
