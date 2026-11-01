import type { ReactNode, Ref } from 'react'

/**
 * Envoltorio accesible (ADR-0014): el SVG es una imagen con un resumen en `label`, y los datos
 * se repiten en una tabla visualmente oculta para lectores de pantalla.
 */
export function ChartFigure({
  label,
  rows,
  className = '',
  measureRef,
  children,
}: {
  label: string
  rows: [string, string][]
  className?: string
  /** Para que el gráfico mida su ancho (`useChartWidth`). */
  measureRef?: Ref<HTMLElement>
  children: ReactNode
}) {
  return (
    <figure className={`chart ${className}`} ref={measureRef}>
      <div role="img" aria-label={label}>
        {children}
      </div>
      {/* Envuelta en un div: una tabla no recorta su contenido y desbordaría la página en móvil. */}
      <div className="sr-only">
        <table>
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
      </div>
    </figure>
  )
}
