import { useEffect, useState } from 'react'
import { Download, RefreshCcw, RotateCcw, Save, ShieldCheck, Wifi } from 'lucide-react'
import { api, type DeviceUpdateStatus, type WifiNetwork, type WifiStatus } from '../api'
import { Panel, StatusPill } from './Ui'

export function FirmwarePanel({onStatus}:{onStatus:(value:string)=>void}) {
  const [info,setInfo]=useState<DeviceUpdateStatus|null>(null)
  const [wifi,setWifi]=useState<WifiStatus|null>(null)
  const [networks,setNetworks]=useState<WifiNetwork[]>([])
  const [coreFiles,setCoreFiles]=useState<string[]>([])
  const [selected,setSelected]=useState('')
  const [busy,setBusy]=useState(false)

  const refresh=async()=>{
    try{
      const [s,f,w]=await Promise.all([api.deviceUpdateStatus(),api.coreFiles(),api.deviceWifi()])
      setInfo(s);setCoreFiles(f.files);setWifi(w)
      if(!selected&&f.files[0])setSelected(f.files[0])
      setNetworks((w.networks||[]).map(n=>({ssid:n.ssid,password:'',priority:n.priority,has_password:n.has_password})))
    }catch(e){onStatus(String(e))}
  }
  useEffect(()=>{refresh()},[])
  const run=async(label:string,fn:()=>Promise<unknown>)=>{setBusy(true);onStatus(label+'…');try{await fn();onStatus(label+' — готово');setTimeout(refresh,3000)}catch(e){onStatus(String(e))}finally{setBusy(false)}}
  const updateNetwork=(index:number,key:'ssid'|'password'|'priority',value:string|number)=>setNetworks(prev=>prev.map((n,i)=>i===index?{...n,[key]:value}:n))
  const addBackup=()=>setNetworks(prev=>prev.length>=6?prev:[...prev,{ssid:'',password:'',priority:Math.max(0,100-prev.length*50)}])
  const saveWifi=async()=>{
    const rows=networks.filter(n=>n.ssid.trim()).map(n=>({ssid:n.ssid.trim(),password:n.password||'',priority:Number(n.priority)||0}))
    if(!rows.length){onStatus('Нужна хотя бы одна Wi‑Fi сеть');return}
    setBusy(true);try{await api.deviceWifiSave(rows);onStatus('Список Wi‑Fi сохранён; контроллер переподключается');setTimeout(refresh,5000)}catch(e){onStatus(String(e))}finally{setBusy(false)}
  }

  return <Panel className="firmware-panel" icon={<Download/>} title="Система / OTA / сеть · ESP32-S3 N16R8" actions={<button className="ghost" onClick={refresh} disabled={busy}><RefreshCcw/>Обновить статус</button>}>
    <div className="firmware-grid">
      <div className="tuning-card">
        <h3>MicroPython application runtime</h3>
        <p>Обычное обновление — по текущей Wi‑Fi сети. USB остаётся аварийным способом восстановления.</p>
        <div className="ota-status"><StatusPill label={info?.runtime_ota_available?'RUNTIME OTA READY':'RUNTIME OTA ?'} tone={info?.runtime_ota_available?'good':'warn'}/><code>{info?.runtime_version||'—'}</code></div>
        <button className="primary" disabled={busy} onClick={()=>run('Runtime OTA',api.updateRuntime)}><Download/>Обновить Runtime по Wi‑Fi</button>
        <button className="ghost" disabled={busy} onClick={()=>run('Rollback Runtime',api.rollbackRuntime)}><RotateCcw/>Откатить предыдущий Runtime</button>
      </div>
      <div className="tuning-card">
        <h3>MicroPython core OTA</h3>
        <p>Полное обновление ядра .app-bin доступно после однократной установки dual-OTA partition table.</p>
        <div className="ota-status"><StatusPill label={info?.core_ota_available?'CORE OTA READY':'CORE OTA LOCKED'} tone={info?.core_ota_available?'good':'warn'}/><span>{info?.next||info?.reason||'проверка…'}</span></div>
        <select value={selected} onChange={e=>setSelected(e.target.value)}>{coreFiles.length?coreFiles.map(f=><option key={f}>{f}</option>):<option value="">firmware/core/*.app-bin не найден</option>}</select>
        <button className="primary" disabled={busy||!selected||!info?.core_ota_available} onClick={()=>run('Core OTA',()=>api.updateCore(selected))}><ShieldCheck/>Прошить ядро OTA</button>
      </div>
    </div>

    <div className="network-card">
      <div className="network-head"><div><h3><Wifi/>Primary + Backup Wi‑Fi + Recovery AP</h3><p>Контроллер перебирает сети по priority. Если ни одна не доступна — поднимает собственную аварийную точку.</p></div><div className="network-pills"><StatusPill label={wifi?.connected?`STA ${wifi.ssid}`:(wifi?.recovery_ap_active?'RECOVERY AP':'OFFLINE')} tone={wifi?.connected?'good':'warn'}/><code>{wifi?.ip||'—'}</code></div></div>
      <div className="wifi-table">
        <div className="wifi-row header"><span>SSID</span><span>Пароль</span><span>Priority</span></div>
        {networks.map((n,i)=><div className="wifi-row" key={i}>
          <input value={n.ssid} placeholder={i===0?'Primary Wi‑Fi':'Backup Wi‑Fi'} onChange={e=>updateNetwork(i,'ssid',e.target.value)}/>
          <input value={n.password||''} type="password" placeholder={n.has_password?'оставь пустым — сохранить текущий':'пароль'} onChange={e=>updateNetwork(i,'password',e.target.value)}/>
          <input value={n.priority} type="number" onChange={e=>updateNetwork(i,'priority',Number(e.target.value))}/>
        </div>)}
      </div>
      <div className="network-actions"><button className="ghost" onClick={addBackup} disabled={busy||networks.length>=6}>+ Добавить резервную сеть</button><button className="primary" onClick={saveWifi} disabled={busy}><Save/>Сохранить сети на ESP32</button></div>
      <small>Recovery AP: {wifi?.recovery_ap_ssid||'поднимется только при потере всех STA сетей'}. Пароли обратно из ESP32 не выдаются.</small>
    </div>
  </Panel>
}
