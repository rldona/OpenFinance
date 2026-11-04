import { useRef, useState } from 'react'
import { ApiError, api, type Attachment } from '../../api/client'
import { useHousehold } from '../../app/household-context'
import { useLoad } from '../../lib/useLoad'

const MAX_MB = 5
const ACCEPT = 'application/pdf,image/png,image/jpeg,image/webp'

function size(bytes: number): string {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`
}

/** Tickets y facturas de un movimiento: subir, descargar y borrar (OF-1007). */
export function Attachments({
  transactionId,
  onChanged,
}: {
  transactionId: string
  onChanged: (message: string, operationId: string | null) => void
}) {
  const { notify } = useHousehold()
  const list = useLoad<Attachment[]>(`att|${transactionId}`, (s) => api.attachments(transactionId, s))
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function upload(file: File | undefined) {
    if (!file) return
    if (file.size > MAX_MB * 1024 * 1024) {
      setError(`«${file.name}» pesa más de ${MAX_MB} MB.`)
      return
    }
    setBusy(true)
    setError(null)
    try {
      const r = await api.addAttachment(transactionId, file)
      list.reload()
      onChanged(`Adjuntado «${r.attachment.filename}»`, r.operation_id)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se ha podido adjuntar')
    } finally {
      setBusy(false)
      if (input.current) input.current.value = ''
    }
  }

  async function remove(a: Attachment) {
    try {
      const r = await api.deleteAttachment(a.id)
      list.reload()
      onChanged(`Adjunto «${a.filename}» borrado`, r.operation_id)
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido borrar el adjunto')
    }
  }

  return (
    <div className="attachments">
      {list.error && <p className="small muted">No se han podido cargar los adjuntos.</p>}
      {list.data && list.data.length > 0 && (
        <ul className="plain" aria-label="Adjuntos">
          {list.data.map((a) => (
            <li key={a.id} className="toolbar">
              <a href={`/api/v1/attachments/${a.id}`} download={a.filename}>
                📎 {a.filename}
              </a>
              <span className="small muted">{size(a.size)}</span>
              <button className="btn small" type="button" aria-label={`Borrar el adjunto ${a.filename}`} onClick={() => void remove(a)}>
                Borrar
              </button>
            </li>
          ))}
        </ul>
      )}
      <label className="small">
        Adjuntar ticket o factura (PDF o imagen, máx. {MAX_MB} MB){' '}
        <input
          ref={input}
          type="file"
          accept={ACCEPT}
          disabled={busy}
          onChange={(e) => void upload(e.target.files?.[0])}
          aria-describedby={error ? 'attachment-error' : undefined}
        />
      </label>
      {error && (
        <p id="attachment-error" className="error small" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}
