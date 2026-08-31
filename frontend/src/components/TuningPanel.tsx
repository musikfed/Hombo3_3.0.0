import { BrainCircuit, Radio, Save, SlidersHorizontal } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { AutonomyStatus, DriveTuning, TuningState } from '../api'
import { Panel, StatusPill, Toggle } from './Ui'

const numberField = (label:string, value:number, onChange:(n:number)=>void, min:number, max:number, step=1, unit='') =>
  <label className="tuning-field"><span>{label}</span><div><input type="number" value={value} min={min} max={max} step={step} onChange={e=>onChange(Number(e.target.value))}/>{unit && <em>{unit}</em>}</div></label>

function draftKey(name:string){ return `hombo3.tuning.draft.${name}` }

export function TuningPanel({ state, autonomy, onSave, onLoad, onPreview, onAutonomy }: {
  state:TuningState
  autonomy:AutonomyStatus
  onSave:(name:string, settings:DriveTuning, activate:boolean)=>Promise<void>
  onLoad:(name:string)=>Promise<void>
  onPreview:(settings:DriveTuning)=>Promise<void>
  onAutonomy:(enabled:boolean, goal:string)=>Promise<void>
}) {
  const [draft, setDraft] = useState<DriveTuning>(state.current)
  const [name, setName] = useState(state.active)
  const [goal, setGoal] = useState(autonomy.goal)

  useEffect(()=>{
    let restored:DriveTuning|undefined
    try {
      const raw=localStorage.getItem(draftKey(state.active))
      if(raw){
        const parsed=JSON.parse(raw)
        if(parsed?.draft && JSON.stringify(parsed.base)===JSON.stringify(state.current)) restored=parsed.draft
      }
    } catch {}
    setDraft(restored||state.current)
  }, [state.active, state.revision])
  useEffect(()=>setName(state.active), [state.active])
  useEffect(()=>setGoal(autonomy.goal), [autonomy.goal])
  useEffect(()=>{
    try{localStorage.setItem(draftKey(state.active),JSON.stringify({base:state.current,draft}))}catch{}
  },[draft,state.active,state.revision])

  const set = <K extends keyof DriveTuning>(key:K, value:DriveTuning[K]) => setDraft(prev=>({...prev,[key]:value}))

  return <Panel title="Тюнинг ходовой · профили и автономия" icon={<SlidersHorizontal size={18}/>} className="tuning-panel" actions={<>
    <StatusPill label={`ПРОФИЛЬ: ${state.active}`} tone="info"/>
    <StatusPill label={`REV ${state.revision}`} tone="good"/>
  </>}>
    <div className="tuning-grid">
      <div className="tuning-card">
        <h3>Скорость и плавность</h3>
        {numberField('PWM калибровки', draft.calibration_pwm, n=>set('calibration_pwm',n), 0,255)}
        {numberField('Крейсерский PWM', draft.cruise_pwm, n=>set('cruise_pwm',n), 0,255)}
        {numberField('Максимальный PWM', draft.max_pwm, n=>set('max_pwm',n), 1,255)}
        {numberField('Внутренний борт в повороте', draft.turn_inner_percent, n=>set('turn_inner_percent',n), 0,100,1,'%')}
        {numberField('Шаг плавного разгона', draft.ramp_step_pwm, n=>set('ramp_step_pwm',n), 1,64)}
        {numberField('Период рампы', draft.ramp_period_ms, n=>set('ramp_period_ms',n), 5,250,1,'мс')}
      </div>
      <div className="tuning-card">
        <h3>Дальномеры и STOP</h3>
        {numberField('Передний HC-SR04 STOP', draft.front_stop_cm, n=>set('front_stop_cm',n), 2,400,1,'см')}
        {numberField('Задний HC-SR04 STOP', draft.rear_stop_cm, n=>set('rear_stop_cm',n), 2,400,1,'см')}
        {numberField('VL53L0X STOP', draft.tof_stop_mm, n=>set('tof_stop_mm',n), 20,4000,10,'мм')}
        <Toggle checked={draft.sensor_safety_default} onChange={v=>set('sensor_safety_default',v)} label="Защита дальномерами по умолчанию"/>
        <h3>Агент</h3>
        <label className="tuning-field"><span>Имя машинки</span><div><input value={draft.robot_name} onChange={e=>set('robot_name',e.target.value)}/></div></label>
        {numberField('Интервал решений Hermes', draft.autonomy_decision_interval_s, n=>set('autonomy_decision_interval_s',n), .5,15,.5,'с')}
        {numberField('TTL команды автономии', draft.autonomy_command_ms, n=>set('autonomy_command_ms',n), 150,3000,50,'мс')}
      </div>
      <div className="tuning-card profile-card">
        <h3>Именованные настройки</h3>
        <label className="tuning-field"><span>Имя профиля</span><div><input value={name} onChange={e=>setName(e.target.value)}/></div></label>
        <div className="profile-actions">
          <button className="primary" onClick={()=>onSave(name,draft,false)}><Save size={16}/>Сохранить профиль</button>
          <button className="ghost" onClick={()=>onSave(name,draft,true)}><Radio size={16}/>Сохранить + активировать</button>
          <button className="ghost" onClick={()=>onPreview(draft)}><Radio size={16}/>Применить на ESP32 без сохранения</button>
          <select value={state.active} onChange={e=>onLoad(e.target.value)}>
            {state.profiles.map(p=><option key={p} value={p}>{p}</option>)}
          </select>
        </div>
        <p><b>На Acer:</b> профили, калибровочный/крейсерский PWM, логика поворота, параметры Hermes и имя. <b>На ESP32:</b> max PWM обычного движения, рампа, STOP-пороги и default защиты. При активации профиль автоматически отправляется контроллеру.</p>
        <p>Несохранённый черновик сохраняется только в браузере и переживает F5. Кнопка «Применить … без сохранения» нужна для стендовой настройки рампы/STOP.</p>
      </div>
      <div className="tuning-card autonomy-card">
        <div className="autonomy-head"><BrainCircuit size={18}/><h3>Автономный режим</h3></div>
        <textarea value={goal} onChange={e=>setGoal(e.target.value)}/>
        <Toggle checked={autonomy.enabled} onChange={v=>onAutonomy(v,goal)} label={autonomy.enabled ? 'АВТОНОМИЯ ВКЛ: движения выбирает Hermes' : 'Автономия выключена'}/>
        <p>Цель сохраняется на Acer. После перезапуска backend автономное движение специально остаётся ВЫКЛ — это safety-правило.</p>
        {autonomy.last_error && <div className="error-box">{autonomy.last_error}</div>}
        {Object.keys(autonomy.last_decision || {}).length > 0 && <pre>{JSON.stringify(autonomy.last_decision,null,2)}</pre>}
      </div>
    </div>
  </Panel>
}
