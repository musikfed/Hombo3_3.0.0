import { useEffect, useMemo, useState } from 'react'
import { Activity, Braces, Cpu, Download, FlaskConical, Map as MapIcon, Radio, ShieldAlert, Wifi } from 'lucide-react'
import { api, type AutonomyStatus, type DashboardConfig, type DriveTuning, type LlmStatus, type LogRecord, type Telemetry, type TuningState, type VisionStatus, type VoiceStatus } from './api'
import { buildDemoTelemetry, demoConfig, demoVision, demoVoice } from './demo'
import { CameraPanel } from './components/CameraPanel'
import { ChassisMonitor } from './components/ChassisMonitor'
import { PinBoard } from './components/PinBoard'
import { SensorPanel } from './components/SensorPanel'
import { ManualControl } from './components/ManualControl'
import { VoiceAgentPanel } from './components/VoiceAgentPanel'
import { LogsPanel } from './components/LogsPanel'
import { TuningPanel } from './components/TuningPanel'
import { FirmwarePanel } from './components/FirmwarePanel'
import { MapPanel } from './components/MapPanel'
import { McpPanel } from './components/McpPanel'
import { Metric, StatusPill } from './components/Ui'

const isDemo = new URLSearchParams(location.search).get('demo') === '1'

const defaultTuning:DriveTuning = {
  name:'default', calibration_pwm:80, cruise_pwm:120, max_pwm:180, turn_inner_percent:35,
  ramp_step_pwm:2, ramp_period_ms:20, front_stop_cm:18, rear_stop_cm:15, tof_stop_mm:150,
  sensor_safety_default:true, autonomy_decision_interval_s:1.5, autonomy_command_ms:900, robot_name:'Машинка',
}
const defaultTuningState:TuningState = {active:'default',revision:1,current:defaultTuning,profiles:['default']}
const defaultLlm:LlmStatus = {configured:false,reachable:false,base_url:'',model:'',model_found:false,error:''}
const defaultAutonomy:AutonomyStatus = {enabled:false,goal:'Безопасно исследовать пространство и не сталкиваться с препятствиями.',cycle:0,last_decision:{},last_error:'',mode:'hermes_only_motion + esp32_safety_override'}

function enrichTelemetry(input: Telemetry, config: DashboardConfig): Telemetry {
  const pwmLimit = input.pwm_limit || config.drive_pwm_limit || 255
  const leftPwm = input.current_left_pwm || 0
  const rightPwm = input.current_right_pwm || 0
  const leftRpm = Math.abs(leftPwm) / Math.max(1, pwmLimit) * config.motor_estimated_max_rpm
  const rightRpm = Math.abs(rightPwm) / Math.max(1, pwmLimit) * config.motor_estimated_max_rpm
  const circumference = Math.PI * config.wheel_diameter_mm / 1000
  const sign = Math.sign(leftPwm + rightPwm)
  const speed = ((leftRpm + rightRpm) / 2) * circumference / 60 * sign
  const direction = (value:number) => value > 0 ? 'forward' as const : value < 0 ? 'reverse' as const : 'stopped' as const
  return {
    ...input,
    pwm_limit: pwmLimit,
    left_direction: input.left_direction || direction(leftPwm),
    right_direction: input.right_direction || direction(rightPwm),
    estimated_left_rpm: input.estimated_left_rpm ?? leftRpm,
    estimated_right_rpm: input.estimated_right_rpm ?? rightRpm,
    estimated_speed_mps: input.estimated_speed_mps ?? speed,
    pwma: input.pwma ?? Math.abs(leftPwm),
    pwmb: input.pwmb ?? Math.abs(rightPwm),
    ain1: input.ain1 ?? leftPwm > 0,
    ain2: input.ain2 ?? leftPwm < 0,
    bin1: input.bin1 ?? rightPwm > 0,
    bin2: input.bin2 ?? rightPwm < 0,
  }
}

export default function App() {
  const [telemetryRaw, setTelemetryRaw] = useState<Telemetry>({ connected: false })
  const [config, setConfig] = useState<DashboardConfig>({...demoConfig, drive_pwm_limit:255})
  const [vision, setVision] = useState<VisionStatus>({...demoVision, enabled:false, available:false, detections:[]})
  const [voice, setVoice] = useState<VoiceStatus>({...demoVoice, enabled:true, announce_actions:true, announce_observations:true, announce_critical:true, queue_size:0, last_phrase:''})
  const [tuning, setTuning] = useState<TuningState>(defaultTuningState)
  const [llm, setLlm] = useState<LlmStatus>(defaultLlm)
  const [autonomy, setAutonomy] = useState<AutonomyStatus>(defaultAutonomy)
  const [calibrationPwm, setCalibrationPwm] = useState(Number(localStorage.getItem('robot.calibration_pwm')) || defaultTuning.calibration_pwm)
  const [logs, setLogs] = useState<LogRecord[]>([])
  const [logCategory, setLogCategory] = useState('')
  const [status, setStatus] = useState('Система готова к подключению')
  const savedTab = localStorage.getItem('robot.active_tab') as 'run'|'map'|'agent'|'mcp'|'logs'|'system' | null
  const [activeTab, setActiveTabState] = useState<'run'|'map'|'agent'|'mcp'|'logs'|'system'>(savedTab || 'run')
  const setActiveTab = (tab:'run'|'map'|'agent'|'mcp'|'logs'|'system') => { setActiveTabState(tab); localStorage.setItem('robot.active_tab', tab) }

  const telemetry = useMemo(() => enrichTelemetry(telemetryRaw, config), [telemetryRaw, config])

  const refreshLlm = async () => {
    if (isDemo) { setLlm({...defaultLlm,configured:true,reachable:true,model_found:true,base_url:'demo',model:'Hermes 4'}); return }
    try { setLlm(await api.llmStatus()) } catch (error) { setLlm({...defaultLlm,error:String(error)}); setStatus(String(error)) }
  }
  const refreshAutonomy = async () => {
    if (isDemo) return
    try { setAutonomy(await api.autonomyStatus()) } catch (error) { setStatus(String(error)) }
  }

  useEffect(() => {
    if (isDemo) {
      setConfig({...demoConfig, drive_pwm_limit:255}); setVision(demoVision); setVoice(demoVoice)
      const timer = window.setInterval(() => setTelemetryRaw(buildDemoTelemetry()), 250)
      setTelemetryRaw(buildDemoTelemetry())
      return () => clearInterval(timer)
    }

    Promise.allSettled([api.dashboardConfig(), api.visionStatus(), api.voiceStatus(), api.tuning(), api.llmStatus(), api.autonomyStatus()]).then(results => {
      if (results[0].status === 'fulfilled') setConfig(results[0].value)
      if (results[1].status === 'fulfilled') setVision(results[1].value)
      if (results[2].status === 'fulfilled') setVoice(results[2].value)
      if (results[3].status === 'fulfilled') { setTuning(results[3].value); if (!localStorage.getItem('robot.calibration_pwm')) setCalibrationPwm(results[3].value.current.calibration_pwm) }
      if (results[4].status === 'fulfilled') setLlm(results[4].value)
      if (results[5].status === 'fulfilled') setAutonomy(results[5].value)
    })
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
    const socket = new WebSocket(`${protocol}://${location.host}/ws/telemetry`)
    socket.onopen = () => setStatus('WebSocket телеметрии подключён')
    socket.onmessage = event => setTelemetryRaw(JSON.parse(event.data))
    socket.onerror = () => setStatus('Ошибка WebSocket телеметрии')
    socket.onclose = () => setTelemetryRaw(previous => ({...previous, connected:false}))
    const keepalive = window.setInterval(() => socket.readyState === WebSocket.OPEN && socket.send('ping'), 15000)
    const agentRefresh = window.setInterval(refreshAutonomy, 3000)
    return () => { clearInterval(keepalive); clearInterval(agentRefresh); socket.close() }
  }, [])

  const pwmTest = async (leftPwm:number, rightPwm:number, sensorSafety:boolean, announce:boolean) => {
    if (isDemo) { setStatus(`DEMO RAW PWM: L=${leftPwm}, R=${rightPwm}, sensors=${sensorSafety}`); return }
    try {
      await api.pwmTest(leftPwm, rightPwm, sensorSafety, announce)
      setStatus(`RAW PWM принят: L=${leftPwm}, R=${rightPwm}; дальномеры ${sensorSafety ? 'ВКЛ' : 'ОБХОД'}`)
    } catch (error) { setStatus(String(error)) }
  }
  const stop = async () => {
    if (isDemo) { setStatus('DEMO: аварийная остановка'); return }
    try { await api.stop(voice.announce_actions); setStatus('СТОП отправлен') } catch (error) { setStatus(String(error)) }
  }
  const refreshLogs = async () => {
    if (isDemo) return
    try { setLogs(await api.logs(300, logCategory)); setStatus('Журнал обновлён') } catch (error) { setStatus(String(error)) }
  }
  const updateVision = async (enabled:boolean) => {
    if (isDemo) { setVision(previous=>({...previous, enabled})); return }
    try { setVision(await api.visionConfigure(enabled, vision.classes)); } catch (error) { setStatus(String(error)) }
  }
  const updateVoice = async (next:Partial<VoiceStatus>) => {
    if (isDemo) { setVoice(previous=>({...previous, ...next})); return }
    try { setVoice(await api.voiceConfigure(next)); } catch (error) { setStatus(String(error)) }
  }
  const saveTuning = async (name:string, next:DriveTuning, activate:boolean) => {
    if (isDemo) { setTuning(prev=>({...prev,active:activate?name:prev.active,current:activate?{...next,name}:prev.current,revision:prev.revision+1,profiles:Array.from(new Set([...prev.profiles,name]))})); return }
    try {
      const state = await api.tuningSave(name,next,activate)
      setTuning(state)
      setStatus(activate ? `Профиль ${name} сохранён и активирован, rev ${state.revision}` : `Профиль ${name} сохранён на Acer, rev ${state.revision}`)
    } catch (error) { setStatus(String(error)) }
  }
  const previewTuning = async (next:DriveTuning) => {
    if (isDemo) { setStatus('DEMO: временный tuning push'); return }
    try { await api.tuningPreview(next); setStatus('Временные max PWM / рампа / STOP отправлены на ESP32 без сохранения профиля') } catch (error) { setStatus(String(error)) }
  }
  const loadTuning = async (name:string) => {
    if (isDemo) return
    try { const state = await api.tuningLoad(name); setTuning(state); setStatus(`Профиль ${name} активирован`) } catch (error) { setStatus(String(error)) }
  }
  const configureAutonomy = async (enabled:boolean, goal:string) => {
    if (isDemo) { setAutonomy(prev=>({...prev,enabled,goal})); return }
    try { const next = await api.autonomyConfigure(enabled,goal); setAutonomy(next); setStatus(enabled ? 'Автономный режим Hermes включён' : 'Автономный режим выключен') } catch (error) { setStatus(String(error)) }
  }

  const connectionTone = telemetry.connected ? 'good' : 'bad'
  const rssiTone = (telemetry.wifi_rssi || -127) > -67 ? 'good' : (telemetry.wifi_rssi || -127) > -78 ? 'warn' : 'bad'

  return <main className="app-shell">
    <header className="topbar">
      <div className="brand">
        <div className="brand-mark"><FlaskConical/></div>
        <div><p>HOMBO3 3.0 · ROBOT CONTROL CENTER</p><h1>Умная машинка · карта / ONVIF / MCP / Ollama / Wi‑Fi OTA</h1></div>
      </div>
      <div className="top-status">
        {isDemo && <StatusPill label="DEMO UI" tone="warn"/>}
        <StatusPill label={telemetry.connected ? 'ESP32 В СЕТИ' : 'ESP32 НЕТ СВЯЗИ'} tone={connectionTone}/>
        <StatusPill label={`Wi‑Fi ${telemetry.wifi_rssi ?? '—'} dBm`} tone={rssiTone}/>
        <StatusPill label={telemetry.battery_percent!=null?`АКБ ${telemetry.battery_percent}%`:'АКБ ADC —'} tone={telemetry.battery_percent!=null&&telemetry.battery_percent<20?'warn':'info'}/>
        <StatusPill label={llm.reachable ? 'HERMES ONLINE' : 'HERMES OFFLINE'} tone={llm.reachable ? 'good' : 'bad'}/>
        <StatusPill label={autonomy.enabled ? 'АВТОНОМИЯ: HERMES' : 'РУЧНОЙ/ТЕСТ'} tone={autonomy.enabled ? 'warn' : 'info'}/>
      </div>
    </header>

    <nav className="tabs">
      <button className={activeTab==='run' ? 'active':''} onClick={()=>setActiveTab('run')}><Activity/>Машинка</button>
      <button className={activeTab==='map' ? 'active':''} onClick={()=>setActiveTab('map')}><MapIcon/>Карта</button>
      <button className={activeTab==='agent' ? 'active':''} onClick={()=>setActiveTab('agent')}><Cpu/>Диалог / AI</button>
      <button className={activeTab==='mcp' ? 'active':''} onClick={()=>setActiveTab('mcp')}><Braces/>MCP</button>
      <button className={activeTab==='logs' ? 'active':''} onClick={()=>{setActiveTab('logs'); refreshLogs()}}><Radio/>Логи</button>
      <button className={activeTab==='system' ? 'active':''} onClick={()=>setActiveTab('system')}><Download/>Прошивка / сеть</button>
      <span className="tab-note">Профили, память и версия настроек сохраняются на Acer</span>
    </nav>

    {activeTab === 'run' && <>
      <section className="run-grid">
        <CameraPanel vision={vision}
          onPtz={(pan,tilt,zoom=0)=>isDemo ? setStatus(`DEMO PTZ ${pan}/${tilt}/${zoom}`) : api.ptz(pan,tilt,zoom).catch(error=>setStatus(String(error)))}
          onVisionToggle={updateVision}
        />
        <ChassisMonitor telemetry={telemetry} sideTestPwm={calibrationPwm} onSideTest={(l,r)=>pwmTest(l,r,false,false)} locked={autonomy.enabled}/>
      </section>

      <section className="dashboard-metrics">
        <Metric label="Оценочная скорость" value={(telemetry.estimated_speed_mps || 0).toFixed(2)} unit=" м/с" accent/>
        <Metric label="Левый борт · 2 мотора" value={Math.abs(telemetry.current_left_pwm || 0)} unit=" PWM"/>
        <Metric label="Правый борт · 2 мотора" value={Math.abs(telemetry.current_right_pwm || 0)} unit=" PWM"/>
        <Metric label="Команда TTL" value={telemetry.command_expired ? 'ИСТЕКЛА' : `${telemetry.command_age_ms || 0} мс`}/>
        <Metric label="Uptime ESP32" value={Math.floor((telemetry.uptime_ms || 0)/1000)} unit=" с"/>
        <Metric label="Профиль" value={tuning.active}/>
        <Metric label="АКБ" value={telemetry.battery_percent!=null?telemetry.battery_percent:'—'} unit={telemetry.battery_percent!=null?' %':''} />
      </section>

      <section className="detail-grid">
        <PinBoard telemetry={telemetry}/>
        <SensorPanel telemetry={telemetry}/>
      </section>
      <ManualControl onPwmTest={pwmTest} onStop={stop} voiceEnabled={voice.announce_actions} onVoiceToggle={value=>updateVoice({announce_actions:value})} tuning={tuning.current} locked={autonomy.enabled} onCalibrationPwmChange={setCalibrationPwm}/>
      <TuningPanel state={tuning} autonomy={autonomy} onSave={saveTuning} onLoad={loadTuning} onPreview={previewTuning} onAutonomy={configureAutonomy}/>
    </>}

    {activeTab === 'map' && <MapPanel telemetry={telemetry} onStatus={setStatus}/>}

    {activeTab === 'agent' && <VoiceAgentPanel
      voice={voice}
      vision={vision}
      llm={llm}
      onRefreshLlm={refreshLlm}
      onSpeak={async text=>{ if (isDemo) {setVoice(previous=>({...previous,last_phrase:text})); return}; await api.speak(text); setStatus('Фраза передана на MAX98357A')}}
      onAsk={async(prompt,allowAction)=>isDemo ? {say:'Предлагаю продолжить прямо на малой скорости.',action:'forward',speed:18,reason:'проход свободен'} : (await api.llm(prompt,allowAction)).decision}
      onVoiceConfig={updateVoice}
    />}

    {activeTab === 'mcp' && <McpPanel onStatus={setStatus}/>}

    {activeTab === 'logs' && <LogsPanel logs={logs} category={logCategory} onCategory={setLogCategory} onRefresh={refreshLogs}/>}

    {activeTab === 'system' && <FirmwarePanel onStatus={setStatus}/>} 

    <footer className="statusbar">
      <span><Wifi size={15}/>{status}</span>
      <span><ShieldAlert size={15}/>{autonomy.enabled ? 'Автономия: движение выбирает Hermes; ESP32 может только остановить по безопасности.' : 'Ручной режим: RAW PWM, профили и дальномерная защита.'}</span>
    </footer>
  </main>
}
