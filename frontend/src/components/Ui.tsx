import type { PropsWithChildren, ReactNode } from 'react'

export function Panel({ title, icon, actions, className = '', children }: PropsWithChildren<{title: string; icon?: ReactNode; actions?: ReactNode; className?: string}>) {
  return <section className={`panel ${className}`}>
    <div className="panel-header">
      <div className="panel-heading">{icon}<h2>{title}</h2></div>
      {actions && <div className="panel-actions">{actions}</div>}
    </div>
    {children}
  </section>
}

export function StatusPill({ label, tone = 'neutral' }: {label: string; tone?: 'good'|'warn'|'bad'|'info'|'neutral'}) {
  return <span className={`status-pill ${tone}`}><i/>{label}</span>
}

export function Metric({ label, value, unit = '', accent = false }: {label: string; value?: string|number; unit?: string; accent?: boolean}) {
  return <div className={`metric-card ${accent ? 'accent' : ''}`}>
    <span>{label}</span>
    <strong>{value ?? '—'}{value !== undefined && value !== '—' ? unit : ''}</strong>
  </div>
}

export function Toggle({ checked, onChange, label, disabled = false }: {checked: boolean; onChange: (value:boolean)=>void; label: string; disabled?: boolean}) {
  return <label className={`toggle ${disabled ? 'disabled' : ''}`}>
    <input type="checkbox" checked={checked} onChange={event => onChange(event.target.checked)} disabled={disabled}/>
    <span className="toggle-track"><span/></span>
    <em>{label}</em>
  </label>
}
