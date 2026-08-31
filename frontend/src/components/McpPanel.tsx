import { useEffect, useMemo, useState } from 'react'
import { Braces, Play, RefreshCcw, ShieldCheck } from 'lucide-react'
import { api, type McpTool } from '../api'
import { Panel, StatusPill } from './Ui'

type FieldSpec={type?:string;min?:number;max?:number;enum?:string[]}

const examples:Record<string,Record<string,unknown>>={
  'robot.stop':{}, 'robot.move':{speed:20,duration_ms:700}, 'robot.turn':{direction:'left',speed:20,duration_ms:500},
  'sensors.read':{}, 'head.look':{pan:-0.5,tilt:0}, 'head.scan':{}, 'vector_probe.status':{},
  'map.resolve':{name:'Кухня'}, 'map.plan':{name:'Зарядка'}, 'map.steering_hint':{name:'Зарядка'},
  'inventory.status':{}, 'speech.say':{text:'Проверка голоса Hombo3'},
}

function storageKey(name:string){return `hombo3.mcp.args.${name}`}
function initialArgs(name:string){
  try{const raw=localStorage.getItem(storageKey(name));if(raw)return JSON.parse(raw)}catch{}
  return {...(examples[name]||{})}
}

export function McpPanel({onStatus}:{onStatus:(s:string)=>void}){
  const [protocol,setProtocol]=useState('')
  const [tools,setTools]=useState<McpTool[]>([])
  const [selected,setSelected]=useState(()=>{try{return localStorage.getItem('hombo3.mcp.selected')||'sensors.read'}catch{return'sensors.read'}})
  const [values,setValues]=useState<Record<string,unknown>>(()=>initialArgs(selected))
  const [result,setResult]=useState('')
  const tool=useMemo(()=>tools.find(t=>t.name===selected),[tools,selected])
  const schema=(tool?.input||{}) as Record<string,FieldSpec>

  const selectTool=(name:string)=>{
    setSelected(name);setValues(initialArgs(name));setResult('')
    try{localStorage.setItem('hombo3.mcp.selected',name)}catch{}
  }
  useEffect(()=>{try{localStorage.setItem(storageKey(selected),JSON.stringify(values))}catch{}},[selected,values])

  const refresh=async()=>{try{const r=await api.mcpTools();setProtocol(r.protocol);setTools(r.tools);if(!r.tools.some(t=>t.name===selected)&&r.tools[0])selectTool(r.tools[0].name)}catch(e){onStatus(String(e))}}
  useEffect(()=>{refresh()},[])
  const call=async()=>{try{const r=await api.mcpCall(selected,values);setResult(JSON.stringify(r,null,2));onStatus(`MCP ${selected} выполнен`)}catch(e){setResult(String(e));onStatus(String(e))}}
  const set=(key:string,value:unknown)=>setValues(prev=>({...prev,[key]:value}))

  return <Panel className="mcp-panel" icon={<Braces/>} title="MCP / агент · семантические инструменты робота" actions={<><StatusPill label={protocol||'MCP'} tone="info"/><button className="ghost" onClick={refresh}><RefreshCcw/>Обновить</button></>}>
    <div className="mcp-grid">
      <div className="tool-list">{tools.map(t=><button key={t.name} className={selected===t.name?'active':''} onClick={()=>selectTool(t.name)}><b>{t.name}</b><span>{t.description}</span></button>)}</div>
      <div className="tool-console">
        <div className="safety-note"><ShieldCheck/> Это не «настройки MCP», а список команд-инструментов агента. LLM не получает сырой GPIO/PWM; ESP32 сохраняет watchdog и obstacle-stop.</div>
        <label>Инструмент<select value={selected} onChange={e=>selectTool(e.target.value)}>{tools.map(t=><option key={t.name}>{t.name}</option>)}</select></label>
        {tool&&<div className="vision-note"><b>{tool.name}</b> — {tool.description}</div>}
        {Object.entries(schema).length>0 ? <div className="mcp-arg-fields">{Object.entries(schema).map(([key,spec])=>{
          const value=values[key]??''
          if(spec.enum?.length)return <label key={key}>{key}<select value={String(value)} onChange={e=>set(key,e.target.value)}>{spec.enum.map(v=><option key={v}>{v}</option>)}</select></label>
          if(spec.type==='integer'||spec.type==='number')return <label key={key}>{key}<input type="number" min={spec.min} max={spec.max} step={spec.type==='integer'?1:.1} value={Number(value||0)} onChange={e=>set(key,spec.type==='integer'?Number.parseInt(e.target.value||'0',10):Number(e.target.value||0))}/><small>{spec.min!=null||spec.max!=null?`диапазон ${spec.min??'−∞'} … ${spec.max??'∞'}`:''}</small></label>
          return <label key={key}>{key}<input value={String(value)} onChange={e=>set(key,e.target.value)}/></label>
        })}</div> : <div className="vision-note">Аргументы не нужны — можно вызывать сразу.</div>}
        <details><summary>Расширенный JSON</summary><textarea value={JSON.stringify(values,null,2)} onChange={e=>{try{setValues(JSON.parse(e.target.value||'{}'))}catch{}}} spellCheck={false}/></details>
        <button className="primary" onClick={call}><Play/>Вызвать инструмент</button>
        <pre>{result||'Результат вызова появится здесь.'}</pre>
      </div>
    </div>
  </Panel>
}
