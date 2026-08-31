import { Activity, Cpu, Gauge, RotateCcw, ToggleLeft } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { Direction, Telemetry } from '../api'
import { Panel, StatusPill } from './Ui'

const directionLabel = (direction?: Direction) => direction === 'forward' ? 'ВПЕРЁД' : direction === 'reverse' ? 'НАЗАД' : 'СТОП'
const directionClass = (direction?: Direction) => direction || 'stopped'

function SideCard({ code, name, direction, pwm, rpm, enabled, onToggle, locked }: {
  code:string; name:string; direction?:Direction; pwm:number; rpm:number; enabled:boolean; onToggle:()=>void; locked:boolean
}) {
  return <div className={`motor-card side-card ${directionClass(direction)} ${enabled ? 'side-test-active' : ''}`}>
    <div className="motor-card-head"><b>{code}</b><span>{name}</span></div>
    <div className="side-wheel-pair"><div className="wheel-visual"><i/></div><div className="wheel-visual"><i/></div></div>
    <div className="motor-values">
      <strong>{directionLabel(direction)}</strong>
      <span>PWM <b>{Math.abs(pwm)}</b></span>
      <span>≈ <b>{Math.round(rpm)}</b> об/мин</span>
    </div>
    <button disabled={locked} className={enabled ? 'side-toggle active' : 'side-toggle'} onClick={onToggle}>
      <ToggleLeft size={17}/>{enabled ? 'ВЫКЛ тест борта' : 'ВКЛ тест борта'}
    </button>
  </div>
}

function DriverChannel({ channel, side, direction, pwm, rpm, in1, in2 }: {
  channel:string; side:string; direction?:Direction; pwm:number; rpm:number; in1?:boolean; in2?:boolean
}) {
  return <div className={`driver-channel ${directionClass(direction)}`}>
    <div><b>{channel}</b><small>{side}</small></div>
    <div className="logic-bits"><span className={in1 ? 'active' : ''}>IN1 {in1 ? 1 : 0}</span><span className={in2 ? 'active' : ''}>IN2 {in2 ? 1 : 0}</span></div>
    <div className="channel-values"><span>{directionLabel(direction)}</span><b>PWM {Math.abs(pwm)}</b><em>≈ {Math.round(rpm)} rpm</em></div>
  </div>
}

export function ChassisMonitor({ telemetry, sideTestPwm, onSideTest, locked }: {
  telemetry: Telemetry
  sideTestPwm: number
  onSideTest: (leftPwm:number, rightPwm:number)=>void
  locked: boolean
}) {
  const leftDirection = telemetry.left_direction || ((telemetry.current_left_pwm || 0) > 0 ? 'forward' : (telemetry.current_left_pwm || 0) < 0 ? 'reverse' : 'stopped')
  const rightDirection = telemetry.right_direction || ((telemetry.current_right_pwm || 0) > 0 ? 'forward' : (telemetry.current_right_pwm || 0) < 0 ? 'reverse' : 'stopped')
  const leftPwm = telemetry.current_left_pwm || 0
  const rightPwm = telemetry.current_right_pwm || 0
  const leftRpm = telemetry.estimated_left_rpm || 0
  const rightRpm = telemetry.estimated_right_rpm || 0
  const [leftTest, setLeftTest] = useState(false)
  const [rightTest, setRightTest] = useState(false)

  useEffect(() => {
    if (locked) { setLeftTest(false); setRightTest(false) }
  }, [locked])

  useEffect(() => {
    if (!leftTest && !rightTest) return
    if (!locked) onSideTest(leftTest ? sideTestPwm : 0, rightTest ? sideTestPwm : 0)
  }, [sideTestPwm]) // intentionally refresh active side test when calibration PWM moves

  const apply = (left:boolean, right:boolean) => {
    setLeftTest(left); setRightTest(right)
    if (!locked) onSideTest(left ? sideTestPwm : 0, right ? sideTestPwm : 0)
  }

  return <Panel
    title="Бортовая схема шасси"
    icon={<Gauge size={18}/>} 
    className="chassis-panel"
    actions={<>
      <StatusPill label={telemetry.stby ? 'STBY ON' : 'STBY OFF'} tone={telemetry.stby ? 'good' : 'bad'}/>
      <StatusPill label={telemetry.emergency_stop ? 'SAFETY STOP' : 'БЕЗОПАСНО'} tone={telemetry.emergency_stop ? 'bad' : 'good'}/>
    </>}
  >
    <div className="chassis-layout side-layout">
      <div className="motor-grid side-motor-grid">
        <SideCard code="L" name="ЛЕВЫЙ БОРТ · 2 мотора" direction={leftDirection} pwm={leftPwm} rpm={leftRpm} enabled={leftTest} onToggle={()=>apply(!leftTest, rightTest)} locked={locked}/>

        <div className="robot-core side-core">
          <div className="front-label">ПЕРЕД</div>
          <div className={`power-flow left ${directionClass(leftDirection)}`}><i/><i/><i/></div>
          <div className={`power-flow right ${directionClass(rightDirection)}`}><i/><i/><i/></div>
          <div className="core-board">
            <Cpu size={28}/>
            <b>ESP32-S3 DevKitC-1</b>
            <span>N16R8 · управление по бортам</span>
          </div>
          <div className="speed-dial">
            <Activity size={18}/>
            <strong>{(telemetry.estimated_speed_mps || 0).toFixed(2)}</strong>
            <span>м/с · оценка</span>
          </div>
          <div className="rear-label">ЗАД</div>
        </div>

        <SideCard code="R" name="ПРАВЫЙ БОРТ · 2 мотора" direction={rightDirection} pwm={rightPwm} rpm={rightRpm} enabled={rightTest} onToggle={()=>apply(leftTest, !rightTest)} locked={locked}/>
      </div>

      <div className="drivers-stack">
        <div className="driver-card">
          <div className="driver-title"><span>ДРАЙВЕРЫ TB6612 ПО БОРТАМ</span><StatusPill label="1 ДРАЙВЕР = 1 БОРТ" tone="info"/></div>
          <DriverChannel channel="TB6612-L · A+B" side="ЛЕВЫЙ БОРТ · FL + BL" direction={leftDirection} pwm={telemetry.left_pwm ?? telemetry.pwma ?? leftPwm} rpm={leftRpm} in1={telemetry.left_in1 ?? telemetry.ain1} in2={telemetry.left_in2 ?? telemetry.ain2}/>
          <DriverChannel channel="TB6612-R · A+B" side="ПРАВЫЙ БОРТ · FR + BR" direction={rightDirection} pwm={telemetry.right_pwm ?? telemetry.pwmb ?? rightPwm} rpm={rightRpm} in1={telemetry.right_in1 ?? telemetry.bin1} in2={telemetry.right_in2 ?? telemetry.bin2}/>
        </div>
        <div className="estimate-note"><RotateCcw size={16}/><span>Один TB6612 обслуживает один борт. Внутри каждого драйвера каналы A и B получают одинаковые IN1/IN2/PWM, но каждый канал питает свой мотор борта.</span></div>
      </div>
    </div>
  </Panel>
}
