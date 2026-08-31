# Hombo3 3.0 · Robot Control Center

Hombo3 is the dedicated home-robot stack for **ESP32-S3-DevKitC-1 N16R8**. Ghost32 remains the universal board lab; Hombo3 owns the vehicle runtime, ONVIF camera, local vision, VectorProbe spatial engine, RAG/Graph memory, semantic MCP tools, Ollama/LLM orchestration and Wi-Fi OTA.

Hardware baseline: side-based dual TB6612 drive, 3× HC-SR04, VL53L0X, MAX98357A on GPIO11/13/**15**, and a 2S2P battery ADC on **GPIO2 / ADC1_CH1** through a 3k/1k divider (4:1). This is the frozen Hombo3 soldering contract.

Normal application updates are delivered over the active Wi-Fi network with backup/rollback; USB remains recovery. VectorProbe fuses an operator-drawn reference map, range rays, dead-reckoned pose, visual landmarks, semantic inventory, dynamic objects, robot trail and route planning. LLM tools stay semantic; raw GPIO remains inside deterministic ESP32 safety code.

See `README_RU.md`, `docs/HARDWARE_BASELINE_RU.md` and `docs/VECTORPROBE_RU.md`.
