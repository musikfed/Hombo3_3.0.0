export type Direction = 'forward' | 'reverse' | 'stopped'

export type Telemetry = {
  connected?: boolean
  ok?: boolean
  ip?: string
  front_cm?: number
  rear_cm?: number
  third_cm?: number
  tof_mm?: number
  tof_ok?: boolean
  wifi_rssi?: number
  wifi_ssid?: string
  wifi_mode?: string
  battery_voltage?: number | null
  battery_percent?: number | null
  battery_cells?: number
  battery_adc_pin?: number
  battery_divider_ratio?: number
  battery_low?: boolean
  battery_return_home?: boolean
  battery_critical?: boolean
  charging_estimated?: boolean
  charge_eta_min_estimated?: number | null
  charge_rate_pct_min_estimated?: number | null
  voltage_rate_v_min?: number | null
  battery_policy?: string
  power_available?: boolean
  reason?: string
  uptime_ms?: number
  target_left_percent?: number
  target_right_percent?: number
  current_left_pwm?: number
  current_right_pwm?: number
  pwm_limit?: number
  command_age_ms?: number
  command_expired?: boolean
  emergency_stop?: boolean
  raw_pwm_mode?: boolean
  sensor_safety_enabled?: boolean
  target_left_raw_pwm?: number
  target_right_raw_pwm?: number
  last_stop_reason?: string
  last_seq?: number
  stby?: boolean
  audio_active?: boolean
  active_sensor_slot?: number
  left_direction?: Direction
  right_direction?: Direction
  left_in1?: boolean
  left_in2?: boolean
  right_in1?: boolean
  right_in2?: boolean
  left_pwm?: number
  right_pwm?: number
  // Legacy aliases from v0.4/v1.1 firmware:
  ain1?: boolean
  ain2?: boolean
  bin1?: boolean
  bin2?: boolean
  pwma?: number
  pwmb?: number
  estimated_left_rpm?: number
  estimated_right_rpm?: number
  estimated_speed_mps?: number
  drive_state?: string
  ramp_step_pwm?: number
  ramp_period_ms?: number
  front_stop_cm?: number
  rear_stop_cm?: number
  tof_stop_mm?: number
  error?: string
}

export type Detection = {
  label: string
  confidence: number
  x?: number
  y?: number
  width?: number
  height?: number
}

export type VisionStatus = {
  enabled: boolean
  available: boolean
  provider_ok?: boolean
  package_ok?: boolean
  model_exists?: boolean
  provider: string
  model?: string
  model_path?: string
  classes: string[]
  detections: Detection[]
  error?: string
}

export type VoiceStatus = {
  enabled: boolean
  announce_actions: boolean
  announce_observations: boolean
  announce_critical: boolean
  queue_size: number
  last_phrase?: string
}

export type DashboardConfig = {
  wheel_diameter_mm: number
  motor_estimated_max_rpm: number
  drive_pwm_limit: number
  telemetry_interval_s: number
  active_profile?: string
}

export type LogRecord = {
  id: number
  timestamp: string
  level: string
  category: string
  message: string
  payload: Record<string, unknown>
}

export type DriveTuning = {
  name: string
  calibration_pwm: number
  cruise_pwm: number
  max_pwm: number
  turn_inner_percent: number
  ramp_step_pwm: number
  ramp_period_ms: number
  front_stop_cm: number
  rear_stop_cm: number
  tof_stop_mm: number
  sensor_safety_default: boolean
  autonomy_decision_interval_s: number
  autonomy_command_ms: number
  robot_name: string
}

export type TuningState = {
  active: string
  revision: number
  updated_at?: string
  current: DriveTuning
  profiles: string[]
  esp32_error?: string
}

export type LlmStatus = {
  configured: boolean
  reachable: boolean
  base_url: string
  model: string
  model_found: boolean
  error?: string
}

export type DeviceUpdateStatus = {
  ok?: boolean
  project?: string
  board?: string
  runtime_version?: string
  runtime_ota_available?: boolean
  core_ota_available?: boolean
  running?: string
  next?: string
  next_size?: number
  free_heap?: number
  reason?: string
}

export type MapPoint = { x_m:number; y_m:number; source?:string; t?:number }
export type MapRay = { ox_m:number; oy_m:number; x_m:number; y_m:number; distance_m:number; angle_deg:number; relative_angle_deg?:number; source:string; weight?:number; t:number }
export type MapTrailPoint = { x_m:number; y_m:number; heading_deg?:number; t?:number }
export type MapObject = { id:string; label:string; x_m:number; y_m:number; confidence?:number; first_seen?:number; last_seen?:number; seen_count?:number; status?:string; active?:boolean; age_s?:number; vx_mps?:number; vy_mps?:number; anchor_id?:string }
export type MapZone = { id:string; name:string; kind:string; points:{x_m:number;y_m:number}[]; target?:{x_m:number;y_m:number} }
export type MapWall = { id:string; name:string; kind:string; a:{x_m:number;y_m:number}; b:{x_m:number;y_m:number}; enabled?:boolean }
export type MapAnchor = { id:string; label:string; name:string; x_m:number; y_m:number; kind?:string; confidence?:number; notes?:string }
export type MapChange = { id:string; kind:string; object_id?:string; label?:string; x_m?:number; y_m?:number; t:number; [key:string]:unknown }
export type MapPose = {x_m:number;y_m:number;heading_deg:number;confidence:number;source:string;last_correction?:Record<string,unknown>}
export type MapState = {
  engine?:string
  enabled:boolean
  pose:MapPose
  points:MapPoint[]
  rays:MapRay[]
  trail:MapTrailPoint[]
  objects:MapObject[]
  zones:MapZone[]
  walls:MapWall[]
  anchors:MapAnchor[]
  route:{x_m:number;y_m:number}[]
  changes:MapChange[]
  inventory?:Record<string,unknown>
  meta?:Record<string,unknown>
}

export type WifiNetwork = { ssid:string; password?:string; priority:number; has_password?:boolean }
export type WifiStatus = { ok?:boolean; connected:boolean; mode:string; ip:string; ssid:string; rssi:number; networks:WifiNetwork[]; has_backup:boolean; recovery_ap_active:boolean; recovery_ap_ssid:string; last_error?:string }

export type McpTool = { name:string; description:string; input:Record<string,unknown> }

export type AutonomyStatus = {
  enabled: boolean
  goal: string
  cycle: number
  last_decision: Record<string, unknown>
  last_error: string
  mode: string
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options?.headers || {}) },
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`${response.status}: ${text}`)
  }
  return response.json() as Promise<T>
}

export const api = {
  vector: (throttle: number, turn: number, voice = true) => request('/api/vector', {
    method: 'POST', body: JSON.stringify({ throttle, turn, ttl_ms: 1000, voice }),
  }),
  pwmTest: (leftPwm: number, rightPwm: number, sensorSafety: boolean, voice = true) => request('/api/pwm-test', {
    method: 'POST', body: JSON.stringify({
      left_pwm: leftPwm,
      right_pwm: rightPwm,
      sensor_safety: sensorSafety,
      ttl_ms: 1800,
      voice,
    }),
  }),
  stop: (voice = true) => request('/api/stop', {
    method: 'POST', body: JSON.stringify({ voice }),
  }),
  speak: (text: string) => request('/api/speak', {
    method: 'POST', body: JSON.stringify({ text, rate: 0 }),
  }),
  llm: (prompt: string, allowAction: boolean) => request<{decision: Record<string, unknown>}>('/api/llm', {
    method: 'POST', body: JSON.stringify({ prompt, allow_action: allowAction }),
  }),
  llmStatus: () => request<LlmStatus>('/api/llm/status'),
  agentContext: (q = 'текущее состояние') => request<Record<string, unknown>>(`/api/agent/context?q=${encodeURIComponent(q)}`),
  logs: (limit = 250, category = '') => request<LogRecord[]>(`/api/logs?limit=${limit}${category ? `&category=${encodeURIComponent(category)}` : ''}`),
  ptz: (pan: number, tilt: number, zoom = 0) => request('/api/camera/ptz', {
    method: 'POST', body: JSON.stringify({ pan, tilt, zoom }),
  }),
  visionStatus: () => request<VisionStatus>('/api/vision/status'),
  visionConfigure: (enabled: boolean, classes: string[]) => request<VisionStatus>('/api/vision/config', {
    method: 'POST', body: JSON.stringify({ enabled, classes }),
  }),
  voiceStatus: () => request<VoiceStatus>('/api/voice/status'),
  voiceConfigure: (config: Partial<VoiceStatus>) => request<VoiceStatus>('/api/voice/config', {
    method: 'POST', body: JSON.stringify(config),
  }),
  dashboardConfig: () => request<DashboardConfig>('/api/dashboard/config'),
  tuning: () => request<TuningState>('/api/tuning'),
  tuningSave: (name: string, settings: DriveTuning, activate = false) => request<TuningState>('/api/tuning/save', {
    method: 'POST', body: JSON.stringify({ name, settings: { ...settings, name }, activate }),
  }),
  tuningPreview: (settings: DriveTuning) => request('/api/tuning/preview', {
    method: 'POST', body: JSON.stringify(settings),
  }),
  tuningLoad: (name: string) => request<TuningState>('/api/tuning/load', {
    method: 'POST', body: JSON.stringify({ name }),
  }),
  tuningPush: () => request('/api/tuning/push', { method: 'POST' }),
  autonomyStatus: () => request<AutonomyStatus>('/api/autonomy/status'),
  autonomyConfigure: (enabled: boolean, goal: string) => request<AutonomyStatus>('/api/autonomy/config', {
    method: 'POST', body: JSON.stringify({ enabled, goal }),
  }),
  deviceUpdateStatus: () => request<DeviceUpdateStatus>('/api/device/update/status'),
  updateRuntime: () => request('/api/device/update/runtime', { method: 'POST' }),
  rollbackRuntime: () => request('/api/device/update/rollback', { method: 'POST' }),
  coreFiles: () => request<{files:string[]}>('/api/device/update/core-files'),
  updateCore: (filename:string) => request('/api/device/update/core', { method:'POST', body:JSON.stringify({filename}) }),
  deviceWifi: () => request<WifiStatus>('/api/device/wifi'),
  deviceWifiSave: (networks:WifiNetwork[]) => request('/api/device/wifi', { method:'POST', body:JSON.stringify({networks}) }),
  mapState: () => request<MapState>('/api/map'),
  mapReset: () => request<MapState>('/api/map/reset', {method:'POST'}),
  mapSetPose: (x_m:number,y_m:number,heading_deg:number) => request('/api/map/pose', {method:'POST',body:JSON.stringify({x_m,y_m,heading_deg})}),
  mapSaveZone: (zone:MapZone) => request('/api/map/zones', {method:'POST',body:JSON.stringify(zone)}),
  mapDeleteZone: (id:string) => request(`/api/map/zones/${encodeURIComponent(id)}`, {method:'DELETE'}),
  mapSaveWall: (wall:MapWall) => request('/api/map/walls', {method:'POST',body:JSON.stringify(wall)}),
  mapDeleteWall: (id:string) => request(`/api/map/walls/${encodeURIComponent(id)}`, {method:'DELETE'}),
  mapSaveAnchor: (anchor:MapAnchor) => request('/api/map/anchors', {method:'POST',body:JSON.stringify(anchor)}),
  mapDeleteAnchor: (id:string) => request(`/api/map/anchors/${encodeURIComponent(id)}`, {method:'DELETE'}),
  mapPromoteObject: (object_id:string,name='') => request('/api/map/promote', {method:'POST',body:JSON.stringify({object_id,name})}),
  mapPlanZone: (zone:string) => request<{ok:boolean;zone?:MapZone;route:{x_m:number;y_m:number}[]}>('/api/map/plan', {method:'POST',body:JSON.stringify({zone})}),
  mapPlanPoint: (x_m:number,y_m:number) => request<{ok:boolean;route:{x_m:number;y_m:number}[]}>('/api/map/plan', {method:'POST',body:JSON.stringify({x_m,y_m})}),
  mapClearReference: () => request<MapState>('/api/map/reference/clear', {method:'POST'}),
  mcpTools: () => request<{protocol:string;tools:McpTool[]}>('/api/mcp/tools'),
  mcpCall: (name:string, args:Record<string,unknown>={}) => request<{ok:boolean;tool:string;result:unknown}>('/api/mcp/call', {method:'POST',body:JSON.stringify({name,arguments:args})}),
}
