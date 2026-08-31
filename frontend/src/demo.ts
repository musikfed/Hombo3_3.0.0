import type { DashboardConfig, Telemetry, VisionStatus, VoiceStatus } from './api'

export const demoConfig: DashboardConfig = {
  wheel_diameter_mm: 65,
  motor_estimated_max_rpm: 200,
  drive_pwm_limit: 90,
  telemetry_interval_s: 0.25,
}

export const demoVoice: VoiceStatus = {
  enabled: true,
  announce_actions: true,
  announce_observations: true,
  announce_critical: true,
  queue_size: 0,
  last_phrase: 'Создатель, еду прямо. Скорость примерно 0,18 метра в секунду.',
}

export const demoVision: VisionStatus = {
  enabled: true,
  available: true,
  provider: 'demo',
  model: 'object-detector',
  classes: ['person', 'chair', 'bottle'],
  detections: [
    { label: 'человек', confidence: 0.94 },
    { label: 'стул', confidence: 0.82 },
  ],
}

export function buildDemoTelemetry(time = Date.now()): Telemetry {
  const phase = Math.sin(time / 1300)
  const left = Math.round(35 + phase * 8)
  const right = Math.round(31 - phase * 5)
  return {
    connected: true,
    ok: true,
    ip: '192.168.1.90',
    front_cm: Math.round(52 + Math.sin(time / 900) * 5),
    rear_cm: 118,
    third_cm: 74,
    tof_mm: 486,
    tof_ok: true,
    wifi_rssi: -52,
    uptime_ms: 4_821_000,
    target_left_percent: 38,
    target_right_percent: 34,
    current_left_pwm: left,
    current_right_pwm: right,
    pwm_limit: 90,
    command_age_ms: 84,
    command_expired: false,
    emergency_stop: false,
    last_stop_reason: '',
    last_seq: 2381,
    stby: true,
    audio_active: false,
    active_sensor_slot: Math.floor(time / 700) % 4,
    left_direction: 'forward',
    right_direction: 'forward',
    ain1: true,
    ain2: false,
    bin1: true,
    bin2: false,
    pwma: Math.abs(left),
    pwmb: Math.abs(right),
    estimated_left_rpm: 78,
    estimated_right_rpm: 69,
    estimated_speed_mps: 0.18,
    drive_state: 'forward',
  }
}
