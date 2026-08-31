"""Hombo3 custom MCP-like metaprotocol.

The LLM receives semantic, bounded robot tools. It never receives raw GPIO access.
Navigation remains deterministic and ESP32 owns TTL/watchdog/obstacle stop.
"""
from __future__ import annotations

import asyncio
from typing import Any

from .database import log_event
from .models import ManualVector


class RobotMcpBridge:
    def __init__(self, robot, camera, mapping, telemetry, announce) -> None:
        self.robot = robot
        self.camera = camera
        self.mapping = mapping
        self.telemetry = telemetry
        self.announce = announce

    def tools(self) -> list[dict[str, Any]]:
        return [
            {"name":"robot.stop","description":"Immediate safe stop","input":{}},
            {"name":"robot.move","description":"Move forward/backward for a bounded time; ESP32 safety stays enabled","input":{"speed":{"type":"integer","min":-60,"max":60},"duration_ms":{"type":"integer","min":100,"max":3000}}},
            {"name":"robot.turn","description":"Turn left/right for a bounded time","input":{"direction":{"enum":["left","right"]},"speed":{"type":"integer","min":5,"max":60},"duration_ms":{"type":"integer","min":100,"max":2500}}},
            {"name":"sensors.read","description":"Read current robot telemetry including battery and range sensors","input":{}},
            {"name":"head.look","description":"Move ONVIF head by one calibrated PTZ step","input":{"pan":{"type":"number","min":-1,"max":1},"tilt":{"type":"number","min":-1,"max":1}}},
            {"name":"head.scan","description":"Perform a short left-center-right active-perception scan","input":{}},
            {"name":"vector_probe.status","description":"Read fused pose, vector rays, reference geometry, inventory and current route","input":{}},
            {"name":"map.resolve","description":"Resolve a named room/zone to a target point","input":{"name":{"type":"string"}}},
            {"name":"map.plan","description":"Plan a collision-aware route to a named zone without moving the robot","input":{"name":{"type":"string"}}},
            {"name":"map.steering_hint","description":"Get VectorProbe attraction/repulsion heading hint for a named zone","input":{"name":{"type":"string"}}},
            {"name":"inventory.status","description":"Read semantic inventory and recent spatial changes","input":{}},
            {"name":"speech.say","description":"Speak through MAX98357A speaker","input":{"text":{"type":"string"}}},
        ]

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        arguments = arguments or {}
        log_event("INFO", "mcp", "Tool call", {"name": name, "arguments": arguments})
        if name == "robot.stop":
            return await self.robot.stop("mcp")
        if name == "robot.move":
            speed = max(-60, min(60, int(arguments.get("speed", 20))))
            duration = max(100, min(3000, int(arguments.get("duration_ms", 700))))
            await self.robot.vector(ManualVector(throttle=speed, turn=0, ttl_ms=duration+250, voice=False), source="mcp")
            await asyncio.sleep(duration/1000)
            await self.robot.stop("mcp-duration")
            return {"ok":True,"speed":speed,"duration_ms":duration}
        if name == "robot.turn":
            direction = str(arguments.get("direction", "left"))
            speed = max(5, min(60, abs(int(arguments.get("speed", 20)))))
            duration = max(100, min(2500, int(arguments.get("duration_ms", 500))))
            turn = -speed if direction == "left" else speed
            await self.robot.vector(ManualVector(throttle=0, turn=turn, ttl_ms=duration+250, voice=False), source="mcp")
            await asyncio.sleep(duration/1000)
            await self.robot.stop("mcp-turn-duration")
            return {"ok":True,"direction":direction,"speed":speed,"duration_ms":duration}
        if name == "sensors.read":
            return {"ok":True,"telemetry":self.telemetry()}
        if name == "head.look":
            pan = max(-1.0, min(1.0, float(arguments.get("pan",0.0))))
            tilt = max(-1.0, min(1.0, float(arguments.get("tilt",0.0))))
            await self.camera.ptz_move(pan, tilt, 0.0)
            return {"ok":True,"camera":self.camera.status()}
        if name == "head.scan":
            # Relative PTZ pulses: left -> centre -> right -> centre. VectorProbe
            # receives range rays at every stop through the telemetry loop.
            readings=[]
            for pan in (-0.75, 0.75, 0.75, -0.75):
                await self.camera.ptz_move(pan,0.0,0.0)
                await asyncio.sleep(0.28)
                readings.append({"head":self.camera.status().get("head_pan_deg",0),"telemetry":self.telemetry(),"pose":self.mapping.pose()})
            return {"ok":True,"readings":readings,"pose":self.mapping.pose()}
        if name in {"vector_probe.status", "map.status"}:
            return {"ok":True,"map":self.mapping.state()}
        if name == "map.resolve":
            zone=self.mapping.resolve_zone(str(arguments.get("name","")))
            return {"ok":bool(zone),"zone":zone}
        if name == "map.plan":
            result=self.mapping.plan_to_zone(str(arguments.get("name","")))
            return result
        if name == "map.steering_hint":
            zone=self.mapping.resolve_zone(str(arguments.get("name","")))
            if not zone: return {"ok":False,"error":"zone not found"}
            return {"ok":True,"zone":zone,"steering":self.mapping.steering_hint(zone["target"])}
        if name == "inventory.status":
            state=self.mapping.state()
            return {"ok":True,"inventory":state.get("inventory",{}),"changes":state.get("changes",[])[-40:]}
        if name == "speech.say":
            text=str(arguments.get("text",""))[:500].strip()
            if not text:
                raise ValueError("text is required")
            queued=await self.announce(text,"action",0.5)
            return {"ok":True,"queued":queued,"text":text}
        raise ValueError("unknown MCP tool: "+name)
