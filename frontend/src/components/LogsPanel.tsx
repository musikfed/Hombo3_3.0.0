import { Database, Download, Filter, RotateCcw } from 'lucide-react'
import type { LogRecord } from '../api'
import { Panel, StatusPill } from './Ui'

export function LogsPanel({ logs, category, onCategory, onRefresh }: {logs:LogRecord[]; category:string; onCategory:(value:string)=>void; onRefresh:()=>void}) {
  return <Panel title="Файловая база событий" icon={<Database size={18}/>} className="logs-panel" actions={<StatusPill label="SQLITE + JSONL" tone="good"/>}>
    <div className="log-toolbar">
      <label><Filter size={16}/><select value={category} onChange={event=>onCategory(event.target.value)}><option value="">Все категории</option><option value="drive">Движение</option><option value="telemetry">Телеметрия</option><option value="camera">Камера</option><option value="vision">Распознавание</option><option value="speech">Голос</option><option value="ollama">Агент</option><option value="safety">Безопасность</option><option value="system">Система</option></select></label>
      <button className="ghost" onClick={onRefresh}><RotateCcw size={16}/>Обновить</button>
      <button className="ghost" disabled title="Экспорт будет подключён следующим этапом"><Download size={16}/>Экспорт</button>
    </div>
    <div className="log-table">
      <div className="log-row header"><span>Время</span><span>Уровень</span><span>Категория</span><span>Событие</span><span>Данные</span></div>
      {logs.length === 0 ? <div className="empty-state">События появятся после запуска backend.</div> : logs.map(log => <div className={`log-row level-${log.level.toLowerCase()}`} key={log.id}>
        <time>{new Date(log.timestamp).toLocaleTimeString('ru-RU')}</time><b>{log.level}</b><span>{log.category}</span><strong>{log.message}</strong><code>{Object.keys(log.payload || {}).length ? JSON.stringify(log.payload) : '—'}</code>
      </div>)}
    </div>
  </Panel>
}
