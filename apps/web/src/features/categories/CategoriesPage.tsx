import { type FormEvent, useState } from 'react'
import { ApiError, api, type Category } from '../../api/client'
import { useHousehold } from '../../app/household-context'

function CategoryRow({ c }: { c: Category }) {
  const { reloadCategories, notify } = useHousehold()
  const [name, setName] = useState(c.name)
  const [icon, setIcon] = useState(c.icon)
  const [color, setColor] = useState(c.color)

  async function save(patch: Parameters<typeof api.updateCategory>[1]) {
    try {
      await api.updateCategory(c.id, patch)
      reloadCategories()
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido guardar')
      setName(c.name)
      setIcon(c.icon)
      setColor(c.color)
    }
  }

  return (
    <tr role="row" className={c.hidden ? 'dim' : ''}>
      <td role="cell">
        <input
          className="field icon-field"
          aria-label={`Icono de ${c.name}`}
          value={icon}
          maxLength={8}
          onChange={(e) => setIcon(e.target.value)}
          onBlur={() => icon.trim() && icon !== c.icon && void save({ icon })}
        />
      </td>
      <td role="cell">
        <input
          className="field"
          aria-label={`Nombre de ${c.name}`}
          value={name}
          maxLength={50}
          onChange={(e) => setName(e.target.value)}
          onBlur={() => name.trim() && name.trim() !== c.name && void save({ name: name.trim() })}
          onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
        />
        {c.slug && <span className="small muted"> · de serie</span>}
      </td>
      <td role="cell">
        <input
          type="color"
          aria-label={`Color de ${c.name}`}
          value={color}
          onChange={(e) => setColor(e.target.value)}
          onBlur={() => color !== c.color && void save({ color })}
        />
      </td>
      <td role="cell">
        <label className="small">
          <input type="checkbox" checked={c.hidden} onChange={(e) => void save({ hidden: e.target.checked })} /> Oculta
        </label>
      </td>
    </tr>
  )
}

export function CategoriesPage() {
  const { categories, reloadCategories, notify } = useHousehold()
  const [name, setName] = useState('')
  const [icon, setIcon] = useState('🏷️')

  async function create(e: FormEvent) {
    e.preventDefault()
    try {
      await api.createCategory({ name: name.trim(), icon: icon.trim() || '🏷️', color: '#64748b' })
      setName('')
      setIcon('🏷️')
      reloadCategories()
      notify(`Categoría «${name.trim()}» creada`)
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'No se ha podido crear')
    }
  }

  return (
    <section>
      <h1>Categorías</h1>
      <p className="lead">
        Renombra, cambia el icono o el color, u oculta las que no uséis. Ocultar no borra nada: los movimientos conservan su
        categoría. <a href="#reglas">Ver las reglas aprendidas</a> · <a href="#movimientos">Volver a movimientos</a>
      </p>
      <div className="card">
        <table role="table" className="rows cats">
          <thead role="rowgroup">
            <tr role="row">
              <th role="columnheader">Icono</th>
              <th role="columnheader">Nombre</th>
              <th role="columnheader">Color</th>
              <th role="columnheader">
                <span className="sr-only">Oculta</span>
              </th>
            </tr>
          </thead>
          <tbody role="rowgroup">
            {categories.map((c) => (
              <CategoryRow key={`${c.id}-${c.name}-${c.icon}-${c.color}`} c={c} />
            ))}
          </tbody>
        </table>
        <form className="toolbar end" onSubmit={create} aria-label="Nueva categoría">
          <input
            className="field icon-field"
            aria-label="Icono de la nueva categoría"
            value={icon}
            maxLength={8}
            onChange={(e) => setIcon(e.target.value)}
          />
          <input
            className="field"
            aria-label="Nombre de la nueva categoría"
            placeholder="Nueva categoría (p. ej. Mascotas)"
            value={name}
            maxLength={50}
            onChange={(e) => setName(e.target.value)}
          />
          <button className="btn primary" type="submit" disabled={!name.trim()}>
            Añadir
          </button>
        </form>
      </div>
    </section>
  )
}
