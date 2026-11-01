import { exportUrl } from '../../api/client'

/** Descarga de los datos del hogar (OF-501). */
export function ExportMenu() {
  return (
    <details className="export-menu">
      <summary className="btn small">Exportar</summary>
      <div className="export-panel">
        <p className="muted">
          Descarga lo que ves en OpenFinance. La cuenta personal de la otra persona no se incluye.
        </p>
        <a className="btn small" href={exportUrl('json')} download>
          JSON
        </a>
        <a className="btn small" href={exportUrl('csv')} download>
          CSV (ZIP)
        </a>
      </div>
    </details>
  )
}
