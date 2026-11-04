import { useEffect, useRef, useState } from 'react'
import { Camera, ChevronDown, ChevronLeft, ChevronRight, ChevronUp, Crosshair, RotateCcw, Volume2, ZoomIn, ZoomOut } from 'lucide-react'
import { api, type VisionStatus } from '../api'
import { Panel, StatusPill, Toggle } from './Ui'

const clampZoom = (value: number) => Math.max(1, Math.min(2.5, value))
const readOrientation = (key: string) => {
  try { return localStorage.getItem(key) === '1' } catch { return false }
}
const readZoom = () => {
  try { return clampZoom(Number(localStorage.getItem('hombo3.camera.digital_zoom')) || 1) } catch { return 1 }
}

export function CameraPanel({ vision, onPtz, onVisionToggle }: {
  vision: VisionStatus
  onPtz: (pan:number, tilt:number, zoom?:number)=>void
  onVisionToggle: (enabled:boolean)=>void
}) {
  const [digitalZoom, setDigitalZoom] = useState(readZoom)
  const [mirror, setMirror] = useState(()=>readOrientation('hombo3.camera.mirror'))
  const [flip, setFlip] = useState(()=>readOrientation('hombo3.camera.flip'))
  const [panInvert, setPanInvert] = useState(false)
  const [tiltInvert, setTiltInvert] = useState(false)
  const [ptzNote, setPtzNote] = useState('ONVIF: ожидаем проверку функций камеры')
  const [voiceToken, setVoiceToken] = useState('')
  const [voiceBusy, setVoiceBusy] = useState(false)
  const [voiceResult, setVoiceResult] = useState('Микрофон для STT выключен по умолчанию')
  const [conversationText, setConversationText] = useState('')
  const [conversationHistory, setConversationHistory] = useState<Array<{utterance:string,reply:string,tools:string[]}>>([])
  const [visualMemories, setVisualMemories] = useState<Array<{id:string,label:string,note:string,image_saved:number}>>([])
  const [memoryNote, setMemoryNote] = useState('Память по умолчанию хранит подтверждённые названия, не фотографии.')

  useEffect(() => {
    api.cameraStatus().then(state=>{
      setPanInvert(!!state.pan_invert)
      setTiltInvert(!!state.tilt_invert)
      setPtzNote(state.optical_zoom_supported === true
        ? 'Оптический зум подтверждён ONVIF'
        : 'Оптический зум: только если поддержан камерой; иначе цифровой')
    }).catch(error=>setPtzNote(String(error)))
  }, [])
  const imageRef = useRef<HTMLImageElement | null>(null)
  const [videoTransport, setVideoTransport] = useState<'ws'|'mjpeg'|'paused'>('paused')
  const [browserVisible, setBrowserVisible] = useState(() => !document.hidden)
  useEffect(() => {
    const onVisibility = () => {
      const visible = !document.hidden
      if (!visible) setVideoTransport('paused')
      setBrowserVisible(visible)
    }
    const onPageHide = () => {
      setVideoTransport('paused')
      setBrowserVisible(false)
    }
    const onPageShow = () => setBrowserVisible(!document.hidden)
    document.addEventListener('visibilitychange', onVisibility)
    window.addEventListener('pagehide', onPageHide)
    window.addEventListener('pageshow', onPageShow)
    return () => {
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('pagehide', onPageHide)
      window.removeEventListener('pageshow', onPageShow)
    }
  }, [])
  useEffect(()=>{ try { localStorage.setItem('hombo3.camera.digital_zoom', String(digitalZoom)) } catch {} },[digitalZoom])
  useEffect(()=>{ try { localStorage.setItem('hombo3.camera.mirror',mirror?'1':'0') } catch {} },[mirror])
  useEffect(()=>{ try { localStorage.setItem('hombo3.camera.flip',flip?'1':'0') } catch {} },[flip])

  // The old multipart-MJPEG <img> path can be buffered by browsers for seconds.
  // WS sends raw JPEGs with latest-frame semantics: if rendering/network is slow,
  // intermediate frames are dropped instead of building a stale queue.
  useEffect(() => {
    const image = imageRef.current
    if (!image) return
    if (!browserVisible || document.hidden) {
      image.onload = null
      image.onerror = null
      image.removeAttribute('src')
      return
    }
    const demo = new URLSearchParams(location.search).get('demo') === '1'
    if (demo) return

    const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
    const socket = new WebSocket(`${protocol}://${location.host}/ws/camera`)
    socket.binaryType = 'blob'
    let currentUrl = ''
    let gotFrame = false
    let fallbackActive = false
    let pendingFrame: Blob | null = null
    let drawing = false
    let disposed = false

    const drawLatest = () => {
      if (drawing || !pendingFrame || disposed || fallbackActive) return
      const blob = pendingFrame
      pendingFrame = null
      drawing = true
      const nextUrl = URL.createObjectURL(blob)
      const oldUrl = currentUrl
      currentUrl = nextUrl
      const complete = () => {
        if (oldUrl) URL.revokeObjectURL(oldUrl)
        drawing = false
        drawLatest()
      }
      image.onload = complete
      image.onerror = complete
      image.src = nextUrl
    }

    const useMjpegFallback = () => {
      if (gotFrame || fallbackActive || disposed || document.hidden) return
      fallbackActive = true
      pendingFrame = null
      image.onload = null
      image.onerror = null
      if (currentUrl) URL.revokeObjectURL(currentUrl)
      currentUrl = ''
      setVideoTransport('mjpeg')
      image.src = `/api/camera/stream?fallback=${Date.now()}`
      try { socket.close() } catch {}
    }
    const fallbackTimer = window.setTimeout(useMjpegFallback, 2500)
    // Close immediately on browser hide/unload even if React is suspended
    // before its state update can trigger normal effect cleanup.
    const onHidden = () => { if (document.hidden) cleanupConnection() }
    const onPageHide = () => cleanupConnection()
    const cleanupConnection = () => {
      if (disposed) return
      disposed = true
      pendingFrame = null
      window.clearTimeout(fallbackTimer)
      image.onload = null
      image.onerror = null
      image.removeAttribute('src') // abort MJPEG fallback too
      try { socket.close() } catch {}
      if (currentUrl) URL.revokeObjectURL(currentUrl)
      currentUrl = ''
    }
    document.addEventListener('visibilitychange', onHidden)
    window.addEventListener('pagehide', onPageHide)

    socket.onmessage = event => {
      if (disposed || fallbackActive || document.hidden) return
      gotFrame = true
      window.clearTimeout(fallbackTimer)
      setVideoTransport('ws')
      // Keep only the newest frame while the browser is still decoding.
      // Prevent a queue of stale frames and excessive object URLs at high FPS.
      pendingFrame = event.data instanceof Blob ? event.data : new Blob([event.data], {type:'image/jpeg'})
      drawLatest()
    }
    socket.onerror = useMjpegFallback
    socket.onclose = () => { if (!gotFrame) useMjpegFallback() }

    return () => {
      document.removeEventListener('visibilitychange', onHidden)
      window.removeEventListener('pagehide', onPageHide)
      cleanupConnection()
    }
  }, [browserVisible])

  const zoomBy = (delta: number) => setDigitalZoom(previous => clampZoom(Number((previous + delta).toFixed(2))))
  const saveReverse = (pan:boolean,tilt:boolean) => {
    api.ptzCalibration(pan,tilt).then(()=>{
      setPanInvert(pan);setTiltInvert(tilt)
      setPtzNote('Реверс PTZ сохранён на Acer')
    }).catch(error=>setPtzNote('PTZ calibration: '+String(error)))
  }
  const askCameraVoice = async (askLlm:boolean) => {
    if(!voiceToken){setVoiceResult('Введи токен голосового доступа из локального .env Hombo3');return}
    setVoiceBusy(true)
    setVoiceResult('Записываем 5 секунд с микрофона камеры…')
    try{
      const result=await api.cameraVoiceAsk(voiceToken,5,askLlm)
      setVoiceResult('Распознано: '+(result.transcript||'тишина')+
        (askLlm?'\\nОтвет ИИ: '+(result.reply||'нет ответа')+
          '\\nИнструменты: '+(result.tools?.join(', ')||'обычный разговор')+
          '\\nTTS: '+(result.queued?'поставлен в очередь':'не отправлен'):''))
    }catch(error){setVoiceResult('Голосовой тракт недоступен: '+String(error))}
    finally{setVoiceBusy(false)}
  }
  const sendConversation = async () => {
    const phrase=conversationText.trim()
    if(!voiceToken || !phrase || voiceBusy){setMemoryNote('Для беседы нужны реплика и настроенный операторский токен');return}
    setVoiceBusy(true)
    setConversationText('')
    try{
      const response=await api.cameraConverse(voiceToken,phrase)
      setConversationHistory(old=>[...old,{utterance:phrase,reply:response.reply,
        tools:response.tools||[]}].slice(-12))
      setMemoryNote(response.pending_label
        ? 'Ожидает подтверждения: '+response.pending_label+' — скажи или напиши «да, запомни».'
        : 'Диалог продолжается. Использованные инструменты показаны рядом с ответом.')
      await api.cameraVisualMemory(voiceToken).then(r=>setVisualMemories(r.memories)).catch(()=>{})
    }catch(error){setMemoryNote('Диалог недоступен: '+String(error))}
    finally{setVoiceBusy(false)}
  }
  const loadVisualMemory = async () => {
    if(!voiceToken){setMemoryNote('Нужен операторский токен доступа');return}
    try{
      const result=await api.cameraVisualMemory(voiceToken)
      setVisualMemories(result.memories)
      setMemoryNote(result.dialogue.pending_label
        ? 'Ожидает подтверждения: '+result.dialogue.pending_label
        : 'Визуальная память: '+result.memories.length+' последних записей. Изображения сохраняются только при явной настройке.')
    }catch(error){setMemoryNote('Память недоступна: '+String(error))}
  }
  const deleteVisualMemory = async (id:string) => {
    if(!voiceToken || !window.confirm('Удалить визуальное воспоминание и его локальный пример?'))return
    try{
      await api.cameraVisualMemoryDelete(voiceToken,id)
      await loadVisualMemory()
    }catch(error){setMemoryNote('Не удалось удалить воспоминание: '+String(error))}
  }
  const runAutofocus = () => {
    api.autofocus().then(()=>setPtzNote('ONVIF автофокус включён (проверь резкость в кадре)')).catch(error=>setPtzNote('Автофокус не поддержан: '+String(error)))
  }
  const runFocusStep = (direction:'near'|'far')=>{
    api.focusStep(direction).then(()=>setPtzNote('Фокус '+direction+': импульс 0.2 с, проверь резкость'))
      .catch(error=>setPtzNote('Ручной фокус не поддержан: '+String(error)))
  }
  const visionDiagnostic = vision.error || (!vision.available
    ? `provider=${vision.provider_ok?'OK':'ERR'} · ultralytics=${vision.package_ok?'OK':'ERR'} · model=${vision.model_exists?'OK':'ERR'} · ${vision.model_path||''}`
    : `${vision.provider}: ${vision.model || 'модель не выбрана'}`)

  return <Panel
    title="WIFICAM T23N / ONVIF"
    icon={<Camera size={18}/>}
    className="camera-panel"
    actions={<><StatusPill label={`ВИДЕО · ${videoTransport === 'paused' ? 'PAUSED' : videoTransport === 'ws' ? 'WS LATEST' : 'MJPEG FALLBACK'}`} tone="good"/><StatusPill label="МИКРОФОН · НАЖМИ ▶" tone="info"/></>}
  >
    <div className="camera-frame">
      <img
        ref={imageRef}
        alt="Поток камеры WIFICAM T23N"
        style={{ transform: `scale(${digitalZoom}) scaleX(${mirror?-1:1}) scaleY(${flip?-1:1})` }}
      />
      <div className="camera-hud top-left"><span>лёгкий видеопрофиль</span><span>зум ×{digitalZoom.toFixed(2)}</span></div>
      <div className="camera-hud top-right"><Volume2 size={15}/><span>звук отдельным потоком</span></div>
      <div className="reticle"><i/><i/><i/><i/></div>
      {vision.detections.map((item, index) => (
        <div className={`detection-box box-${index}`} key={`${item.label}-${index}`}>
          <span>{item.label} · {Math.round(item.confidence * 100)}%</span>
        </div>
      ))}
    </div>

    <div className="camera-audio-row">
      <span><Volume2 size={16}/> Микрофон T23N → Acer / STT → ИИ → TTS → динамик T23N</span>
      <audio controls preload="none" src="/api/camera/audio"/>
      <div className="zoom-row">
        <label>Токен голосового доступа
          <input type="password" value={voiceToken}
            onChange={e=>setVoiceToken(e.target.value)} autoComplete="off"
            placeholder="CAMERA_VOICE_ACCESS_TOKEN" />
        </label>
        <button disabled={voiceBusy} onClick={()=>void askCameraVoice(false)}>Распознать 5 с</button>
        <button disabled={voiceBusy} onClick={()=>void askCameraVoice(true)}>Спросить ИИ голосом</button>
      </div>
      <small className="vision-note" style={{whiteSpace:'pre-line'}}>{voiceResult}</small>
      <small className="vision-note">По нажатию, не постоянно. При CAMERA_DIALOGUE_ENABLED=true ИИ сам выбирает зрительные инструменты во время реплик; постоянное прослушивание/VAD ещё не включено. Для звука камеры проверь SPEECH_OUTPUT=camera_ssh.</small>
    </div>
    <div className="camera-audio-row">
      <strong>Разговор с визуальной памятью</strong>
      <small className="vision-note">Та же беседа, что и через микрофон: можно писать реплику или продолжить голосом. Не нужны отдельные кнопки для YOLO/OpenCV — инструменты выбирает модель.</small>
      <div className="zoom-row">
        <input aria-label="Реплика ассистенту" type="text" value={conversationText}
          onChange={event=>setConversationText(event.target.value)}
          onKeyDown={event=>{if(event.key==='Enter'){event.preventDefault();void sendConversation()}}}
          placeholder="Например: а что я показываю теперь?" maxLength={1500}/>
        <button disabled={voiceBusy||!conversationText.trim()} onClick={()=>void sendConversation()}>Сказать ассистенту</button>
        <button disabled={voiceBusy||!voiceToken} onClick={()=>void loadVisualMemory()}>Моя визуальная память</button>
      </div>
      <small className="vision-note" style={{whiteSpace:'pre-line'}}>{memoryNote}</small>
      <div aria-live="polite">
        {conversationHistory.map((turn,index)=>(
          <div key={index} className="vision-note" style={{padding:'8px 0',borderBottom:'1px solid #94a3b8'}}>
            <strong>Ты:</strong> {turn.utterance}
            <div><strong>Ассистент:</strong> {turn.reply}</div>
            <small>Инструменты: {turn.tools.join(', ')||'беседа без камеры'}</small>
          </div>
        ))}
      </div>
      {visualMemories.map(memory=>(
        <div className="vision-note" key={memory.id}>
          <strong>{memory.label}</strong> · {memory.image_saved?'Подтверждённый кадр сохранён':'Только описание'}
          <div>{memory.note}</div>
          <button disabled={voiceBusy} onClick={()=>void deleteVisualMemory(memory.id)}>Удалить воспоминание</button>
        </div>
      ))}
    </div>

    <div className="camera-controls">
      <div className="ptz-pad" aria-label="Управление поворотом камеры">
        <button className="up" onClick={() => onPtz(0, .55)}><ChevronUp/></button>
        {/* Semantic PTZ contract: negative pan = LEFT, positive pan = RIGHT. */}
        <button className="left" onClick={() => onPtz(-.55, 0)}><ChevronLeft/></button>
        <button className="center" onClick={() => onPtz(0, 0)}><Crosshair/></button>
        <button className="right" onClick={() => onPtz(.55, 0)}><ChevronRight/></button>
        <button className="down" onClick={() => onPtz(0, -.55)}><ChevronDown/></button>
      </div>
      <div className="camera-side-controls">
        <div className="zoom-row">
          <button onClick={() => zoomBy(-.25)} disabled={digitalZoom <= 1}><ZoomOut size={18}/>Зум −</button>
          <button onClick={() => setDigitalZoom(1)}><RotateCcw size={18}/>×1</button>
          <button onClick={() => zoomBy(.25)} disabled={digitalZoom >= 2.5}><ZoomIn size={18}/>Зум +</button>
        </div>
        <small className="vision-note">Цифровой зум на Acer не меняет объектив и не нагружает камеру. Оптический зум — только если ONVIF его поддерживает.</small>
        <div className="zoom-row">
          <label><input type="checkbox" checked={mirror} onChange={e=>setMirror(e.target.checked)}/> Зеркало ⇆</label>
          <label><input type="checkbox" checked={flip} onChange={e=>setFlip(e.target.checked)}/> Переворот ⇅</label>
        </div>
        <small className="vision-note">Оба флажка вместе = поворот 180°. Только экран оператора: RTSP/YOLO и моторы не меняются.</small>
        <div className="zoom-row">
          <button onClick={()=>onPtz(0,0,-.4)}><ZoomOut size={18}/>Оптика −</button>
          <button onClick={()=>onPtz(0,0,.4)}><ZoomIn size={18}/>Оптика +</button>
          <button onClick={runAutofocus}>Автофокус ONVIF</button>
          <button onClick={()=>runFocusStep('near')}>Фокус ближе</button>
          <button onClick={()=>runFocusStep('far')}>Фокус дальше</button>
        </div>
        <div className="zoom-row">
          <label><input type="checkbox" checked={panInvert} onChange={event=>saveReverse(event.target.checked,tiltInvert)}/> Реверс лево/право</label>
          <label><input type="checkbox" checked={tiltInvert} onChange={event=>saveReverse(panInvert,event.target.checked)}/> Реверс верх/низ</label>
        </div>
        <small className="vision-note">{ptzNote}</small>
        <Toggle checked={vision.enabled} onChange={onVisionToggle} label="Распознавание объектов"/>
        <small className={vision.error ? 'vision-error' : 'vision-note'}>{visionDiagnostic}</small>
        <div className="object-chips">
          {vision.detections.length ? vision.detections.map((item, index) => (
            <span key={`${item.label}-chip-${index}`}>{item.label}<b>{Math.round(item.confidence * 100)}%</b></span>
          )) : <span className="muted-chip">объекты не обнаружены</span>}
        </div>
      </div>
    </div>
  </Panel>
}


