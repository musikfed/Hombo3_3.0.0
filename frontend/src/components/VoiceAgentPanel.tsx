import { Bot, BrainCircuit, MessageSquareText, Volume2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { LlmStatus, VoiceStatus, VisionStatus } from '../api'
import { Panel, StatusPill, Toggle } from './Ui'

const DEFAULT_TEXT = 'Система готова к прогоночному тестированию.'
const DEFAULT_PROMPT = 'Оцени показания датчиков, активный профиль ходовой и предложи одно безопасное действие.'

function readString(key: string, fallback: string): string {
  try { return localStorage.getItem(key) ?? fallback } catch { return fallback }
}

function readBool(key: string, fallback = false): boolean {
  try {
    const value = localStorage.getItem(key)
    if (value === null) return fallback
    return value === '1' || value === 'true'
  } catch { return fallback }
}

export function VoiceAgentPanel({ voice, vision, llm, onSpeak, onAsk, onVoiceConfig, onRefreshLlm }: {
  voice:VoiceStatus
  vision:VisionStatus
  llm:LlmStatus
  onSpeak:(text:string)=>Promise<void>
  onAsk:(prompt:string, allowAction:boolean)=>Promise<unknown>
  onVoiceConfig:(next:Partial<VoiceStatus>)=>void
  onRefreshLlm:()=>Promise<void>
}) {
  const [text, setText] = useState(() => readString('robot.voice.text', DEFAULT_TEXT))
  const [prompt, setPrompt] = useState(() => readString('robot.agent.prompt', DEFAULT_PROMPT))
  const [allowAction, setAllowAction] = useState(() => readBool('robot.agent.allow_action', false))
  const [answer, setAnswer] = useState(() => readString('robot.agent.answer', ''))
  const [busy, setBusy] = useState(false)
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => { try { localStorage.setItem('robot.voice.text', text) } catch {} }, [text])
  useEffect(() => { try { localStorage.setItem('robot.agent.prompt', prompt) } catch {} }, [prompt])
  useEffect(() => { try { localStorage.setItem('robot.agent.allow_action', allowAction ? '1' : '0') } catch {} }, [allowAction])
  useEffect(() => { try { localStorage.setItem('robot.agent.answer', answer) } catch {} }, [answer])

  useEffect(() => {
    let wasInflight = false
    try {
      wasInflight = localStorage.getItem('robot.agent.inflight') === '1'
      localStorage.removeItem('robot.agent.inflight')
    } catch {}
    if (wasInflight) {
      setAnswer(previous => previous || 'Предыдущий запрос был прерван обновлением страницы. Текст вопроса сохранён — отправь его повторно.')
    }
  }, [])

  useEffect(() => {
    if (!busy) { setElapsed(0); return }
    const started = Date.now()
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000)
    return () => clearInterval(timer)
  }, [busy])

  return <Panel title="Голос и агент машинки" icon={<BrainCircuit size={18}/>} className="voice-agent-panel" actions={<>
    <StatusPill label={llm.reachable ? 'HERMES ONLINE' : 'HERMES OFFLINE'} tone={llm.reachable ? 'good' : 'bad'}/>
    <StatusPill label={vision.available ? `ACER VISION: ${vision.model || 'local'}` : 'ACER VISION OFF'} tone={vision.available ? 'info' : 'warn'}/>
  </>}>
    <div className="voice-agent-grid">
      <div className="voice-box">
        <div className="subheading"><Volume2 size={17}/><b>Голосовой мониторинг</b></div>
        <textarea value={text} onChange={event=>setText(event.target.value)}/>
        <button className="primary" onClick={()=>onSpeak(text)}>Произнести через машинку</button>
        <div className="toggle-stack">
          <Toggle checked={voice.announce_actions} onChange={value=>onVoiceConfig({announce_actions:value})} label="Действия"/>
          <Toggle checked={voice.announce_observations} onChange={value=>onVoiceConfig({announce_observations:value})} label="Наблюдения"/>
          <Toggle checked={voice.announce_critical} onChange={value=>onVoiceConfig({announce_critical:value})} label="Критические события"/>
        </div>
        <div className="last-phrase"><MessageSquareText size={16}/><span>{voice.last_phrase || 'Фраз ещё не было'}</span></div>
      </div>
      <div className="agent-box">
        <div className="subheading"><Bot size={17}/><b>Hermes 4 · генеративный мозг</b></div>
        <div className="llm-line"><code>{llm.base_url || 'OLLAMA_BASE_URL не задан'}</code><button className="ghost" onClick={onRefreshLlm}>Проверить</button></div>
        <small>{llm.model}</small>
        {llm.error && <div className="error-box">{llm.error}</div>}
        <textarea value={prompt} onChange={event=>setPrompt(event.target.value)}/>
        <Toggle checked={allowAction} onChange={setAllowAction} label="Разрешить одно проверенное действие"/>
        <button className="primary" disabled={busy} onClick={async()=>{
          if (!prompt.trim()) return
          setBusy(true)
          try {
            localStorage.setItem('robot.agent.inflight', '1')
            localStorage.setItem('robot.agent.prompt', prompt)
            const result = await onAsk(prompt, allowAction)
            setAnswer(JSON.stringify(result, null, 2))
          }
          catch (error) { setAnswer(String(error)) }
          finally {
            try { localStorage.removeItem('robot.agent.inflight') } catch {}
            setBusy(false)
          }
        }}>{busy ? `Hermes думает… ${elapsed} с` : 'Спросить агента'}</button>
        <pre>{answer || 'Диалог с Hermes работает независимо от камеры. Во время «Hermes думает» страницу не обновлять: refresh прерывает текущий HTTP-запрос. Сам вопрос теперь сохраняется.'}</pre>
      </div>
    </div>
  </Panel>
}
