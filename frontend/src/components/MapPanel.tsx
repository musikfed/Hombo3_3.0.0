import { useEffect, useMemo, useState, type MouseEvent } from 'react'
import { BatteryCharging, Boxes, Crosshair, Map as MapIcon, Navigation, RotateCcw, Ruler, Save, Trash2, Waypoints } from 'lucide-react'
import { api, type MapObject, type MapState, type MapWall, type MapZone, type Telemetry } from '../api'
import { Panel, StatusPill } from './Ui'

const W=980, H=620, SCALE=82
const sx=(x:number)=>W/2+x*SCALE
const sy=(y:number)=>H/2-y*SCALE
const wx=(x:number)=>(x-W/2)/SCALE
const wy=(y:number)=>(H/2-y)/SCALE

type Mode='none'|'zone'|'wall'
type Layers={reference:boolean;rays:boolean;trail:boolean;semantic:boolean;route:boolean;changes:boolean}

function centroid(points:{x_m:number;y_m:number}[]){
  if(!points.length)return{x_m:0,y_m:0}
  return{x_m:points.reduce((a,p)=>a+p.x_m,0)/points.length,y_m:points.reduce((a,p)=>a+p.y_m,0)/points.length}
}

function objectTone(o:MapObject){
  if(o.status==='dynamic')return'dynamic'
  if(o.status==='confirmed_static'||o.status==='static_candidate')return'static'
  return'temporary'
}

export function MapPanel({telemetry,onStatus}:{telemetry:Telemetry,onStatus:(s:string)=>void}){
  const [state,setState]=useState<MapState|null>(null)
  const [mode,setMode]=useState<Mode>('none')
  const [draft,setDraft]=useState<{x_m:number;y_m:number}[]>([])
  const [name,setName]=useState('')
  const [kind,setKind]=useState('room')
  const [layers,setLayers]=useState<Layers>(()=>{
    try{return JSON.parse(localStorage.getItem('hombo3.map.layers')||'') as Layers}catch{return{reference:true,rays:true,trail:true,semantic:true,route:true,changes:true}}
  })
  useEffect(()=>{try{localStorage.setItem('hombo3.map.layers',JSON.stringify(layers))}catch{}},[layers])
  const refresh=async()=>{try{setState(await api.mapState())}catch(e){onStatus(String(e))}}
  useEffect(()=>{refresh();const id=window.setInterval(refresh,800);return()=>clearInterval(id)},[])

  const pose=state?.pose||{x_m:0,y_m:0,heading_deg:0,confidence:0,source:'—'}
  const heading=Math.PI*pose.heading_deg/180
  const robotPoints=useMemo(()=>{
    const cx=sx(pose.x_m),cy=sy(pose.y_m),r=16
    return [[r,0],[-r*.8,-r*.68],[-r*.8,r*.68]].map(([dx,dy])=>{
      const x=cx+dx*Math.cos(heading)+dy*Math.sin(heading)
      const y=cy-dx*Math.sin(heading)+dy*Math.cos(heading)
      return `${x},${y}`
    }).join(' ')
  },[pose.x_m,pose.y_m,pose.heading_deg])

  const activeObjects=(state?.objects||[]).filter(o=>o.active!==false).slice(-80)
  const clickMap=(e:MouseEvent<SVGSVGElement>)=>{
    if(mode==='none')return
    const rect=e.currentTarget.getBoundingClientRect()
    const x=(e.clientX-rect.left)*W/rect.width
    const y=(e.clientY-rect.top)*H/rect.height
    const point={x_m:Number(wx(x).toFixed(3)),y_m:Number(wy(y).toFixed(3))}
    if(mode==='wall')setDraft(prev=>prev.length>=2?[point]:[...prev,point])
    else setDraft(prev=>[...prev,point].slice(0,64))
  }
  const startMode=(next:Mode)=>{setMode(next);setDraft([]);setName('');setKind(next==='wall'?'wall':'room')}
  const saveDraft=async()=>{
    try{
      if(mode==='zone'){
        if(!name.trim()||draft.length<3){onStatus('Для зоны нужны имя и минимум 3 точки');return}
        const zone:MapZone={id:'',name:name.trim(),kind,points:draft}
        await api.mapSaveZone(zone)
      }else if(mode==='wall'){
        if(draft.length!==2){onStatus('Для сегмента нужны ровно 2 точки');return}
        const wall:MapWall={id:'',name:name.trim()||'Стена',kind,a:draft[0],b:draft[1],enabled:true}
        await api.mapSaveWall(wall)
      }else return
      setDraft([]);setName('');setMode('none');await refresh();onStatus('Эталонная геометрия сохранена')
    }catch(e){onStatus(String(e))}
  }
  const planZone=async(zone:string)=>{try{const r=await api.mapPlanZone(zone);await refresh();onStatus(r.ok?`Маршрут к «${zone}» построен`:`Маршрут к «${zone}» не найден`)}catch(e){onStatus(String(e))}}
  const promote=async(o:MapObject)=>{try{await api.mapPromoteObject(o.id,o.label);await refresh();onStatus(`${o.label}: подтверждён как статический ориентир`)}catch(e){onStatus(String(e))}}

  const uncertaintyM=0.05+(1-(pose.confidence||0))*0.85
  const recentRays=(state?.rays||[]).filter(r=>(Date.now()/1000-r.t)<8).slice(-260)
  const route=state?.route||[]
  const inventory=state?.inventory||{}

  return <Panel className="map-panel vector-probe-panel" icon={<MapIcon/>} title="Hombo VectorProbe · эталонная / оперативная / семантическая карта" actions={<>
    <StatusPill label={`POSE ${Math.round((pose.confidence||0)*100)}%`} tone={(pose.confidence||0)>.72?'good':(pose.confidence||0)>.42?'warn':'bad'}/>
    <StatusPill label={state?.meta?.vector_probe_ready?'REFERENCE READY':'НАРИСУЙ СТЕНЫ'} tone={state?.meta?.vector_probe_ready?'good':'warn'}/>
    <button className="ghost" onClick={()=>startMode('wall')}><Ruler/>Стена/проход</button>
    <button className="ghost" onClick={()=>startMode('zone')}><Crosshair/>Зона</button>
    <button className="ghost" onClick={async()=>{await api.mapReset();await refresh();onStatus('Оперативная карта и трек сброшены; эталон сохранён')}}><RotateCcw/>Сброс live</button>
  </>}>
    <div className="vector-layerbar">
      {Object.entries({reference:'Эталон',rays:'Лучевой щуп',trail:'Трек',semantic:'Объекты',route:'Маршрут',changes:'Изменения'}).map(([key,label])=><label key={key}><input type="checkbox" checked={layers[key as keyof Layers]} onChange={e=>setLayers(v=>({...v,[key]:e.target.checked}))}/>{label}</label>)}
      <span className="vector-source">{pose.source} {pose.last_correction?.kind?`· correction: ${String(pose.last_correction.kind)}`:''}</span>
    </div>
    <div className="map-layout">
      <div className="map-canvas-wrap">
        <svg className={`map-canvas ${mode!=='none'?'drawing':''}`} viewBox={`0 0 ${W} ${H}`} onClick={clickMap}>
          {Array.from({length:15},(_,i)=>i-7).map(i=><line key={'v'+i} x1={sx(i)} y1={0} x2={sx(i)} y2={H} className={i===0?'axis':'gridline'}/>) }
          {Array.from({length:11},(_,i)=>i-5).map(i=><line key={'h'+i} x1={0} y1={sy(i)} x2={W} y2={sy(i)} className={i===0?'axis':'gridline'}/>) }

          {layers.reference&&state?.walls.map(w=><g key={w.id}>
            <line x1={sx(w.a.x_m)} y1={sy(w.a.y_m)} x2={sx(w.b.x_m)} y2={sy(w.b.y_m)} className={`reference-wall ${w.kind==='opening'||w.kind==='door_open'?'opening':''}`}/>
            <text x={(sx(w.a.x_m)+sx(w.b.x_m))/2+4} y={(sy(w.a.y_m)+sy(w.b.y_m))/2-5} className="wall-label">{w.name}</text>
          </g>)}
          {layers.reference&&state?.zones.map(z=>{const c=centroid(z.points);return <g key={z.id}>
            <polygon points={z.points.map(p=>`${sx(p.x_m)},${sy(p.y_m)}`).join(' ')} className={`map-zone ${z.kind==='charger'?'charger':z.kind==='no-go'?'no-go':''}`}/>
            <text x={sx(c.x_m)} y={sy(c.y_m)} className="zone-label">{z.kind==='charger'?'⚡ ':''}{z.name}</text>
          </g>})}
          {layers.reference&&state?.anchors.map(a=><g key={a.id}>
            <rect x={sx(a.x_m)-5} y={sy(a.y_m)-5} width="10" height="10" transform={`rotate(45 ${sx(a.x_m)} ${sy(a.y_m)})`} className="anchor-marker"/>
            <text x={sx(a.x_m)+9} y={sy(a.y_m)-8} className="anchor-label">{a.name||a.label}</text>
          </g>)}

          {layers.trail&&state?.trail.length&&<polyline points={state.trail.slice(-2200).map(p=>`${sx(p.x_m)},${sy(p.y_m)}`).join(' ')} className="robot-trail"/>}
          {layers.route&&route.length>1&&<><polyline points={route.map(p=>`${sx(p.x_m)},${sy(p.y_m)}`).join(' ')} className="planned-route"/>{route.map((p,i)=><circle key={i} cx={sx(p.x_m)} cy={sy(p.y_m)} r={i===route.length-1?6:3} className="route-node"/>)}</>}

          {layers.rays&&recentRays.map((r,i)=><g key={`${r.t}-${i}`} className={`vector-ray ${r.source.includes('tof')?'tof':''}`}>
            <line x1={sx(r.ox_m)} y1={sy(r.oy_m)} x2={sx(r.x_m)} y2={sy(r.y_m)}/><circle cx={sx(r.x_m)} cy={sy(r.y_m)} r={r.source.includes('tof')?2.8:2}/>
          </g>)}

          {layers.semantic&&activeObjects.map(o=><g key={o.id} className={`semantic-object ${objectTone(o)}`}>
            <circle cx={sx(o.x_m)} cy={sy(o.y_m)} r={o.status==='dynamic'?8:6}/>
            {o.status==='dynamic'&&((o.vx_mps||0)!==0||(o.vy_mps||0)!==0)&&<line x1={sx(o.x_m)} y1={sy(o.y_m)} x2={sx(o.x_m+(o.vx_mps||0))} y2={sy(o.y_m+(o.vy_mps||0))} className="velocity-vector"/>}
            <text x={sx(o.x_m)+9} y={sy(o.y_m)-9} className="object-label">{o.label} {Math.round((o.confidence||0)*100)}%</text>
          </g>)}

          {draft.length>0&&<><polyline points={draft.map(p=>`${sx(p.x_m)},${sy(p.y_m)}`).join(' ')} className={mode==='wall'?'draft-wall':'draft-zone'}/>{draft.map((p,i)=><circle key={i} cx={sx(p.x_m)} cy={sy(p.y_m)} r="4" className="draft-node"/>)}</>}

          <circle cx={sx(pose.x_m)} cy={sy(pose.y_m)} r={uncertaintyM*SCALE} className="pose-uncertainty"/>
          <line x1={sx(pose.x_m)} y1={sy(pose.y_m)} x2={sx(pose.x_m)+42*Math.cos(heading)} y2={sy(pose.y_m)-42*Math.sin(heading)} className="heading-line"/>
          <polygon points={robotPoints} className="robot-marker"/>
        </svg>
      </div>

      <aside className="map-side vector-side">
        <div className="map-stat"><b><Waypoints/> Поза VectorProbe</b><code>x {pose.x_m.toFixed(2)} · y {pose.y_m.toFixed(2)} · {pose.heading_deg.toFixed(0)}°</code><small>Уверенность {Math.round((pose.confidence||0)*100)}%; окружность на карте показывает накопленную неопределённость.</small></div>
        <div className="map-stat"><b>Дальномеры</b><code>F {telemetry.front_cm||0}cm · R {telemetry.rear_cm||0}cm · H {telemetry.third_cm||0}cm · ToF {telemetry.tof_mm||0}mm</code><small>Стены не переписываются по одному замеру: сначала корректируется поза робота.</small></div>
        <div className="map-stat"><b><BatteryCharging/> АКБ 2S2P</b><code>{telemetry.battery_voltage!=null?`${telemetry.battery_voltage.toFixed(2)} V`:'—'} {telemetry.battery_percent!=null?`· ${telemetry.battery_percent}%`:''}</code><small>ADC GPIO2 · делитель 3к/1к · {telemetry.charging_estimated?'заряд растёт':telemetry.battery_policy||'наблюдение'}{telemetry.charge_eta_min_estimated!=null?` · ETA ≈ ${telemetry.charge_eta_min_estimated} мин`:''}</small></div>

        {mode!=='none'&&<div className="zone-editor reference-editor">
          <h3>{mode==='wall'?'Новый опорный сегмент':'Новая зона'}</h3>
          <input placeholder={mode==='wall'?'Стена / дверь / проход':'Комната / кухня / зарядка'} value={name} onChange={e=>setName(e.target.value)}/>
          {mode==='wall'?<select value={kind} onChange={e=>setKind(e.target.value)}><option value="wall">Стена / препятствие</option><option value="door_open">Открытый проход / дверь</option><option value="reference">Опорная линия</option></select>:<select value={kind} onChange={e=>setKind(e.target.value)}><option value="room">Комната</option><option value="charger">Зарядка</option><option value="no-go">Запретная зона</option><option value="poi">Точка интереса</option></select>}
          <span>{mode==='wall'?`Точек ${draft.length}/2`:`Точек ${draft.length}. Кликаешь по контуру.`}</span>
          <button className="primary" disabled={mode==='wall'?draft.length!==2:(!name.trim()||draft.length<3)} onClick={saveDraft}><Save/>Сохранить</button>
          <button className="ghost" onClick={()=>{setDraft([]);setMode('none')}}><Trash2/>Отмена</button>
        </div>}

        <div className="zone-list"><h3><Navigation/> Зоны и маршруты</h3>{state?.zones.length?state.zones.map(z=><div key={z.id} className="zone-row"><span>{z.kind==='charger'?'⚡':'⌂'} {z.name}</span><span className="row-actions"><button className="ghost" title="Построить маршрут" onClick={()=>planZone(z.name)}><Navigation/></button><button className="ghost" title="Удалить" onClick={async()=>{await api.mapDeleteZone(z.id);await refresh()}}><Trash2/></button></span></div>):<small>Сначала нарисуй комнаты/зарядку поверх известного плана.</small>}</div>

        <div className="zone-list"><h3><Boxes/> Семантические объекты</h3>{activeObjects.length?activeObjects.slice(-10).reverse().map(o=><div key={o.id} className="object-row"><span><i className={`dot ${objectTone(o)}`}/>{o.label} · {o.status||'temporary'} · {Math.round((o.confidence||0)*100)}%</span>{o.status!=='dynamic'&&o.status!=='confirmed_static'&&<button className="ghost text-button" onClick={()=>promote(o)}>Закрепить</button>}</div>):<small>Локальный YOLO пока не дал пространственных объектов.</small>}</div>

        {layers.changes&&<div className="zone-list"><h3>Изменения пространства</h3>{state?.changes?.length?state.changes.slice(-8).reverse().map(c=><div key={c.id} className="change-row"><span>{c.kind}</span><small>{c.label||'object'} {c.x_m!=null?`@ ${Number(c.x_m).toFixed(1)},${Number(c.y_m).toFixed(1)}`:''}</small></div>):<small>Новых/перемещённых объектов пока не зафиксировано.</small>}</div>}

        <div className="map-stat compact"><b>Инвентарь</b><code>anchors {String((inventory as any).reference_anchors??0)} · dynamic {String((inventory as any).active_dynamic??0)} · temporary {String((inventory as any).active_temporary??0)}</code></div>
        <button className="danger ghost" onClick={async()=>{if(confirm('Удалить именно ЭТАЛОННУЮ карту: стены, зоны и якоря?')){await api.mapClearReference();await refresh();onStatus('Эталонная карта очищена')}}}>Очистить эталонную карту</button>
      </aside>
    </div>
  </Panel>
}
