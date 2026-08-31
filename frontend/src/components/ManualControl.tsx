import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, CircleStop, Gamepad2, Mic2, ShieldCheck, ShieldOff } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { DriveTuning } from '../api'
import { Panel, Toggle } from './Ui'

type KeyState = { w:boolean; s:boolean; a:boolean; d:boolean }
type DriveMode = 'forward'|'reverse'|'left'|'right'
type Command = { left:number; right:number; safety:boolean; announce:boolean }

export function ManualControl({ onPwmTest, onStop, voiceEnabled, onVoiceToggle, tuning, locked, onCalibrationPwmChange }: {
  onPwmTest:(leftPwm:number, rightPwm:number, sensorSafety:boolean, announce:boolean)=>void | Promise<unknown>
  onStop:()=>void | Promise<unknown>
  voiceEnabled:boolean
  onVoiceToggle:(value:boolean)=>void
  tuning:DriveTuning
  locked:boolean
  onCalibrationPwmChange:(value:number)=>void
}) {
  const initialSavedPwm = Number(localStorage.getItem('robot.calibration_pwm'))
  const initialSavedSafety = localStorage.getItem('robot.sensor_safety')
  const initialPwm = Number.isFinite(initialSavedPwm) ? Math.max(0, Math.min(255, initialSavedPwm)) : tuning.calibration_pwm
  const initialSafety = initialSavedSafety === null ? tuning.sensor_safety_default : initialSavedSafety === '1'

  const [pwm, setPwm] = useState(initialPwm)
  const [sensorSafety, setSensorSafety] = useState(initialSafety)

  // Mutable refs keep keyboard/hold logic stable while React state changes.
  // This fixes the old bug where changing PWM re-created the key listeners,
  // cleared the hold timer and let the ESP32 TTL expire while W/A/S/D was still held.
  const pwmRef = useRef(initialPwm)
  const safetyRef = useRef(initialSafety)
  const turnInnerRef = useRef(tuning.turn_inner_percent)
  const voiceRef = useRef(voiceEnabled)
  const lockedRef = useRef(locked)
  const onPwmTestRef = useRef(onPwmTest)
  const onStopRef = useRef(onStop)
  const calibrationChangeRef = useRef(onCalibrationPwmChange)

  const repeatTimer = useRef<number | null>(null)
  const activeButton = useRef<DriveMode|null>(null)
  const keys = useRef<KeyState>({w:false,s:false,a:false,d:false})

  // Last-wins command queue: slider/key-repeat updates never pile up as many
  // simultaneous fetch() calls. If Wi-Fi is briefly slow, only the newest PWM
  // command is sent next.
  const pendingCommand = useRef<Command|null>(null)
  const commandBusy = useRef(false)
  const driveEpoch = useRef(0)

  useEffect(() => { pwmRef.current = pwm }, [pwm])
  useEffect(() => { safetyRef.current = sensorSafety }, [sensorSafety])
  useEffect(() => { turnInnerRef.current = tuning.turn_inner_percent }, [tuning.turn_inner_percent])
  useEffect(() => { voiceRef.current = voiceEnabled }, [voiceEnabled])
  useEffect(() => { lockedRef.current = locked }, [locked])
  useEffect(() => { onPwmTestRef.current = onPwmTest }, [onPwmTest])
  useEffect(() => { onStopRef.current = onStop }, [onStop])
  useEffect(() => { calibrationChangeRef.current = onCalibrationPwmChange }, [onCalibrationPwmChange])

  const isDriving = () => activeButton.current !== null || Object.values(keys.current).some(Boolean)

  const flushCommands = async (epoch:number) => {
    if (commandBusy.current) return
    commandBusy.current = true
    try {
      while (pendingCommand.current && epoch === driveEpoch.current) {
        const command = pendingCommand.current
        pendingCommand.current = null
        try {
          await Promise.resolve(onPwmTestRef.current(command.left, command.right, command.safety, command.announce))
        } catch {
          // App.tsx shows the request error. The hold loop continues and may recover.
        }
      }
    } finally {
      commandBusy.current = false
      if (pendingCommand.current && epoch === driveEpoch.current) void flushCommands(epoch)
    }
  }

  const queueCommand = (command:Command) => {
    if (lockedRef.current) return
    pendingCommand.current = command
    void flushCommands(driveEpoch.current)
  }

  const clampRaw = (value:number) => Math.max(-255, Math.min(255, Math.round(value)))
  const inner = () => Math.round(pwmRef.current * turnInnerRef.current / 100)

  const commandForButton = (mode:DriveMode):[number,number] => {
    const value = pwmRef.current
    if (mode === 'forward') return [value,value]
    if (mode === 'reverse') return [-value,-value]
    if (mode === 'left') return [-value,value]
    return [value,-value]
  }

  const commandForKeys = ():[number,number] => {
    const state = keys.current
    const value = pwmRef.current
    const throttle = (state.w ? 1 : 0) + (state.s ? -1 : 0)
    const turn = (state.d ? 1 : 0) + (state.a ? -1 : 0)
    if (throttle === 0 && turn === 0) return [0,0]
    if (throttle === 0) return turn < 0 ? [-value,value] : [value,-value]
    if (turn === 0) return [throttle*value, throttle*value]
    const inside = inner()
    if (throttle > 0 && turn < 0) return [inside,value]
    if (throttle > 0 && turn > 0) return [value,inside]
    if (throttle < 0 && turn < 0) return [-inside,-value]
    return [-value,-inside]
  }

  const sendCurrent = (announce=false) => {
    if (lockedRef.current) return
    const pair = activeButton.current ? commandForButton(activeButton.current) : commandForKeys()
    queueCommand({ left: clampRaw(pair[0]), right: clampRaw(pair[1]), safety: safetyRef.current, announce })
  }

  const clearRepeat = () => {
    if (repeatTimer.current !== null) {
      window.clearInterval(repeatTimer.current)
      repeatTimer.current = null
    }
  }

  const beginRepeat = (announce:boolean) => {
    clearRepeat()
    sendCurrent(announce)
    // 300 ms refresh gives a large margin against the ESP32 command TTL and
    // feels continuous even if one Wi-Fi request is delayed.
    repeatTimer.current = window.setInterval(() => sendCurrent(false), 300)
  }

  const stopDrive = () => {
    driveEpoch.current += 1
    pendingCommand.current = null
    activeButton.current = null
    keys.current = {w:false,s:false,a:false,d:false}
    clearRepeat()
    void Promise.resolve(onStopRef.current())
  }

  const setExactPwm = (value:number) => {
    const next = Math.max(0, Math.min(255, Math.round(value)))
    pwmRef.current = next
    setPwm(next)
    localStorage.setItem('robot.calibration_pwm', String(next))
    calibrationChangeRef.current(next)
    if (isDriving()) sendCurrent(false)
  }

  const setSafety = (value:boolean) => {
    safetyRef.current = value
    setSensorSafety(value)
    localStorage.setItem('robot.sensor_safety', value ? '1' : '0')
    if (isDriving()) sendCurrent(false)
  }

  const startButton = (mode:DriveMode) => () => {
    if (lockedRef.current) return
    driveEpoch.current += 1
    activeButton.current = mode
    beginRepeat(voiceRef.current)
  }

  // Load the calibration PWM from a newly loaded tuning profile only when the
  // browser does not already have a manually selected calibration value.
  useEffect(() => {
    const saved = Number(localStorage.getItem('robot.calibration_pwm'))
    if (!Number.isFinite(saved)) setExactPwm(tuning.calibration_pwm)
  }, [tuning.name])

  // A changed turn parameter takes effect immediately during a held W+A/W+D.
  useEffect(() => {
    if (isDriving()) sendCurrent(false)
  }, [tuning.turn_inner_percent])

  // Register keyboard listeners once. They read live values through refs.
  useEffect(() => {
    const normalize = (event:KeyboardEvent) => {
      const key = event.key.toLowerCase()
      if (key === 'arrowup') return 'w'
      if (key === 'arrowdown') return 's'
      if (key === 'arrowleft') return 'a'
      if (key === 'arrowright') return 'd'
      return key
    }

    const down = (event:KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (target && ['INPUT','TEXTAREA','SELECT'].includes(target.tagName)) return
      if (event.code === 'Space') { event.preventDefault(); stopDrive(); return }
      if (event.key === '+' || event.key === '=') {
        event.preventDefault(); setExactPwm(pwmRef.current + (event.shiftKey ? 5 : 1)); return
      }
      if (event.key === '-' || event.key === '_') {
        event.preventDefault(); setExactPwm(pwmRef.current - (event.shiftKey ? 5 : 1)); return
      }
      const key = normalize(event)
      if (!['w','a','s','d'].includes(key) || lockedRef.current) return
      event.preventDefault()

      const wasDriving = Object.values(keys.current).some(Boolean)
      ;(keys.current as Record<string,boolean>)[key] = true
      activeButton.current = null
      if (!wasDriving) {
        driveEpoch.current += 1
        beginRepeat(voiceRef.current)
      } else {
        sendCurrent(false)
      }
    }

    const up = (event:KeyboardEvent) => {
      const key = normalize(event)
      if (!['w','a','s','d'].includes(key)) return
      ;(keys.current as Record<string,boolean>)[key] = false
      if (!Object.values(keys.current).some(Boolean)) stopDrive()
      else sendCurrent(false)
    }

    const blur = () => {
      // If the browser loses focus while a key is held, keyup may never arrive.
      // Explicit STOP prevents a stuck/stuttering command after Alt+Tab/clicks.
      if (isDriving()) stopDrive()
    }

    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    window.addEventListener('blur', blur)
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', up)
      window.removeEventListener('blur', blur)
      clearRepeat()
    }
  }, [])

  return <Panel title="Калибровка моторов · RAW PWM 0…255" icon={<Gamepad2 size={18}/>} className="control-panel">
    {locked && <div className="autonomy-lock">АВТОНОМНЫЙ РЕЖИМ: ручные команды заблокированы. Доступен только аварийный СТОП.</div>}
    <div className="control-layout">
      <div className="drive-pad">
        <button disabled={locked} className="forward" onPointerDown={startButton('forward')} onPointerUp={stopDrive} onPointerLeave={stopDrive} onPointerCancel={stopDrive}><ArrowUp/>ВПЕРЁД</button>
        <button disabled={locked} className="left" onPointerDown={startButton('left')} onPointerUp={stopDrive} onPointerLeave={stopDrive} onPointerCancel={stopDrive}><ArrowLeft/>ВЛЕВО</button>
        <button className="stop" onClick={stopDrive}><CircleStop size={30}/>СТОП</button>
        <button disabled={locked} className="right" onPointerDown={startButton('right')} onPointerUp={stopDrive} onPointerLeave={stopDrive} onPointerCancel={stopDrive}><ArrowRight/>ВПРАВО</button>
        <button disabled={locked} className="reverse" onPointerDown={startButton('reverse')} onPointerUp={stopDrive} onPointerLeave={stopDrive} onPointerCancel={stopDrive}><ArrowDown/>НАЗАД</button>
      </div>

      <div className="control-settings">
        <label className="speed-slider">
          <span>Точный PWM на TB6612</span>
          <b>{pwm} / 255</b>
          <input type="range" min="0" max="255" step="1" value={pwm} onChange={event=>setExactPwm(Number(event.target.value))}/>
        </label>

        <div className="pwm-entry-row">
          <input aria-label="Точный PWM" type="number" min="0" max="255" step="1" value={pwm} onChange={event=>setExactPwm(Number(event.target.value))}/>
          <div className="pwm-nudges">
            <button className="ghost" onClick={()=>setExactPwm(pwm-5)}>−5</button>
            <button className="ghost" onClick={()=>setExactPwm(pwm-1)}>−1</button>
            <button className="ghost" onClick={()=>setExactPwm(pwm+1)}>+1</button>
            <button className="ghost" onClick={()=>setExactPwm(pwm+5)}>+5</button>
          </div>
        </div>

        <div className="safety-box">
          <Toggle checked={sensorSafety} onChange={setSafety} label={sensorSafety ? 'ПРОГОН В СБОРЕ · дальномеры блокируют опасное движение' : 'СТЕНД / РАЗОБРАНО · дальномеры НЕ блокируют моторы'}/>
          <div className="voice-hint">
            {sensorSafety ? <ShieldCheck size={17}/> : <ShieldOff size={17}/>} 
            <span>{sensorSafety ? 'Передний HC-SR04 + VL53L0X защищают движение вперёд, задний HC-SR04 — назад.' : 'Только для вывешенных колёс/разобранного стенда. TTL и STOP остаются активными.'}</span>
          </div>
        </div>

        <Toggle checked={voiceEnabled} onChange={onVoiceToggle} label="Озвучивать первый запуск команды"/>
        <div className="voice-hint"><Mic2 size={17}/><span>WASD/стрелки используют ТЕКУЩИЙ PWM. +/− меняют PWM прямо во время движения. Команда обновляется каждые 300 мс без накопления запросов.</span></div>
        <p>Ползунок меняет скорость сразу при удерживаемой кнопке/клавише. При потере фокуса браузера отправляется STOP.</p>
      </div>
    </div>
  </Panel>
}
