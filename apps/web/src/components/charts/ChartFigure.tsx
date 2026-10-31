import type { ReactNode } from 'react'

/**
 * Envoltorio accesible (ADR-0014): el SVG es una imagen con un resumen en `label`, y los datos
 * se repiten en una tabla visualmente oculta para lectores de pantalla.
 */
export function ChartFigure({
  label,
  rows,
  className = '',
  children,
}: {
  label: string
  rows: [string, string][]
  className?: string
  children: ReactNode
}) {
  return (
    <figure className={`chart ${className}`}>
      <div role="img" aria-label={label}>
        {children}
      </div>
      <table className="sr-only">
        <caption>{label}</caption>
        <tbody>
          {rows.map(([k, v], i) => (
            <tr key={`${k}-${i}`}>
              <th scope="row">{k}</th>
              <td>{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  )
}
