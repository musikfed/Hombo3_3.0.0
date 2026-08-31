import { Radar, Ruler } from 'lucide-react'
import type { Telemetry } from '../api'
import { Panel, StatusPill } from './Ui'

type SensorGaugeProps = {
  label: string
  value: number
  max: number
  unit: string
  active: boolean
  valid: boolean
  critical?: number
}

function SensorGauge({ label, value, max, unit, active, valid, critical = 18 }: SensorGaugeProps) {
  const safeValue = valid ? Math.max(0, Math.min(max, value)) : 0
  const ratio = safeValue / max
  const danger = valid && value > 0 && value <= critical

  const statusLabel = danger
    ? 'БЛИЗКО'
    : active
      ? 'ОПРОС'
      : valid
        ? 'ДАННЫЕ'
        : 'НЕТ ОТВЕТА'

  const statusTone = danger
    ? 'bad'
    : active
      ? 'info'
      : valid
        ? 'good'
        : 'neutral'

  return <div className={`sensor-gauge ${active ? 'active' : ''} ${danger ? 'danger' : ''}`}>
    <div className="sensor-gauge-head">
      <b>{label}</b>
      <StatusPill label={statusLabel} tone={statusTone}/>
    </div>
    <div className="sensor-value">
      <strong>{valid ? value : '—'}</strong><span>{unit}</span>
    </div>
    <div className="distance-ray">
      <i style={{width: valid ? `${Math.max(2, ratio * 100)}%` : '0%'}}/>
    </div>
  </div>
}

export function SensorPanel({ telemetry }: {telemetry: Telemetry}) {
  const front = telemetry.front_cm ?? 0
  const rear = telemetry.rear_cm ?? 0
  const third = telemetry.third_cm ?? 0
  const tof = telemetry.tof_mm ?? 0

  return <Panel
    title="Дальномеры · числовой мониторинг"
    icon={<Radar size={18}/>}
    className="sensor-panel"
    actions={<StatusPill label="4 СЛОТА ОПРОСА" tone="info"/>}
  >
    <div className="sensor-grid">
      <SensorGauge label="HC-SR04 · передний" value={front} max={250} unit="см" active={telemetry.active_sensor_slot === 0} valid={front > 0}/>
      <SensorGauge label="HC-SR04 · задний" value={rear} max={250} unit="см" active={telemetry.active_sensor_slot === 1} valid={rear > 0}/>
      <SensorGauge label="HC-SR04 · третий" value={third} max={250} unit="см" active={telemetry.active_sensor_slot === 2} valid={third > 0}/>
      <SensorGauge label="VL53L0X · ToF" value={tof} max={2000} unit="мм" active={telemetry.active_sensor_slot === 3} valid={telemetry.tof_ok === true && tof > 0} critical={150}/>
    </div>
    <div className="sensor-summary">
      <Ruler size={17}/>
      <span>«НЕТ ОТВЕТА» означает нулевое/невалидное измерение. Для HC-SR04 это может быть отключённый датчик, тайм-аут эха или цель вне диапазона.</span>
    </div>
  </Panel>
}
