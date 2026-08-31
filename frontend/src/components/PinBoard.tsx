import { CircuitBoard } from 'lucide-react'
import type { Telemetry } from '../api'
import { Panel, StatusPill } from './Ui'

type Pin = {label:string; gpio:string; role:string; group:'motor'|'sensor'|'i2c'|'audio'|'system'|'power'; active:(t:Telemetry)=>boolean}

const pins: Pin[] = [
  {label:'GPIO18', gpio:'18', role:'LEFT IN1 → AIN1+BIN1 · TB6612-L', group:'motor', active:t=>!!(t.left_in1 ?? t.ain1)},
  {label:'GPIO17', gpio:'17', role:'LEFT IN2 → AIN2+BIN2 · TB6612-L', group:'motor', active:t=>!!(t.left_in2 ?? t.ain2)},
  {label:'GPIO14', gpio:'14', role:'LEFT PWM → PWMA+PWMB · TB6612-L', group:'motor', active:t=>Math.abs(t.left_pwm ?? t.pwma ?? t.current_left_pwm ?? 0)>0},
  {label:'GPIO21', gpio:'21', role:'RIGHT IN1 → AIN1+BIN1 · TB6612-R', group:'motor', active:t=>!!(t.right_in1 ?? t.bin1)},
  {label:'GPIO10', gpio:'10', role:'RIGHT IN2 → AIN2+BIN2 · TB6612-R', group:'motor', active:t=>!!(t.right_in2 ?? t.bin2)},
  {label:'GPIO12', gpio:'12', role:'RIGHT PWM → PWMA+PWMB · TB6612-R', group:'motor', active:t=>Math.abs(t.right_pwm ?? t.pwmb ?? t.current_right_pwm ?? 0)>0},
  {label:'GPIO40', gpio:'40', role:'STBY → оба TB6612', group:'system', active:t=>!!t.stby},
  {label:'GPIO1', gpio:'1', role:'HC-F TRIG', group:'sensor', active:t=>t.active_sensor_slot===0},
  {label:'GPIO7', gpio:'7', role:'HC-F ECHO · через 1k/2k', group:'sensor', active:t=>t.active_sensor_slot===0},
  {label:'GPIO6', gpio:'6', role:'HC-R TRIG', group:'sensor', active:t=>t.active_sensor_slot===1},
  {label:'GPIO5', gpio:'5', role:'HC-R ECHO · через 1k/2k', group:'sensor', active:t=>t.active_sensor_slot===1},
  {label:'GPIO4', gpio:'4', role:'HC-HEAD TRIG', group:'sensor', active:t=>t.active_sensor_slot===2},
  {label:'GPIO16', gpio:'16', role:'HC-HEAD ECHO · через 1k/2k', group:'sensor', active:t=>t.active_sensor_slot===2},
  {label:'GPIO8', gpio:'8', role:'I²C SDA · VL53L0X', group:'i2c', active:t=>t.active_sensor_slot===3},
  {label:'GPIO9', gpio:'9', role:'I²C SCL · VL53L0X', group:'i2c', active:t=>t.active_sensor_slot===3},
  {label:'GPIO11', gpio:'11', role:'I²S BCLK · MAX98357A', group:'audio', active:t=>!!t.audio_active},
  {label:'GPIO13', gpio:'13', role:'I²S LRC/WS · MAX98357A', group:'audio', active:t=>!!t.audio_active},
  {label:'GPIO15', gpio:'15', role:'I²S DIN · MAX98357A', group:'audio', active:t=>!!t.audio_active},
  {label:'GPIO2', gpio:'2', role:'BATTERY ADC1_CH1 · делитель 3k/1k', group:'power', active:t=>t.battery_voltage!=null},
]

export function PinBoard({ telemetry }: {telemetry: Telemetry}) {
  return <Panel title="ESP32-S3-DevKitC-1 N16R8 · активность пинов" icon={<CircuitBoard size={18}/>} className="pin-panel" actions={<StatusPill label="LIVE GPIO" tone="info"/>}>
    <div className="pin-legend">
      <span className="motor">моторы</span><span className="sensor">ультразвук</span><span className="i2c">I²C</span><span className="audio">аудио</span><span className="power">АКБ</span><span className="system">система</span>
    </div>
    <div className="board-shell">
      <div className="board-title"><b>ESP32-S3</b><span>DevKitC-1 · N16R8</span></div>
      <div className="pin-grid">
        {pins.map(pin => <div className={`pin ${pin.group} ${pin.active(telemetry) ? 'active' : ''}`} key={`${pin.label}-${pin.gpio}`}>
          <span className="pin-dot"/><div><b>{pin.label}</b><small>IO {pin.gpio}</small></div><em>{pin.role}</em>
        </div>)}
      </div>
    </div>
    <p className="panel-footnote">GPIO2 теперь выделен под измерение 2S АКБ. MAX98357A DIN перенесён на GPIO15. Это зафиксированный Hombo3 pinout для пайки.</p>
  </Panel>
}
