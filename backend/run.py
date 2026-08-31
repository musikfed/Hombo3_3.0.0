"""Windows-friendly launcher with clean camera shutdown."""
import logging

import uvicorn

from app.camera import camera_hub
from app.config import settings

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class RobotServer(uvicorn.Server):
    def handle_exit(self, sig, frame) -> None:  # type: ignore[override]
        # Stop camera/audio streams before Uvicorn begins waiting for open
        # StreamingResponse connections. Otherwise Ctrl+C can hang.
        camera_hub.request_shutdown()
        super().handle_exit(sig, frame)


if __name__ == "__main__":
    config = uvicorn.Config(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=False,
        log_level="info",
        access_log=False,
        timeout_graceful_shutdown=3,
    )
    RobotServer(config).run()
