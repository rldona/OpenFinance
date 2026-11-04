import { useEffect, useState } from 'react'
import { ApiError, api, type Invitation, type Member, type Role } from '../../api/client'
import { useHousehold } from '../../app/household-context'

const ROLES: { id: Role; label: string; help: string }[] = [
  { id: 'owner', label: 'Administra', help: 'Todo, y además invita y gestiona a las personas' },
  { id: 'editor', label: 'Edita', help: 'Anota y cambia datos del hogar' },
  { id: 'viewer', label: 'Solo mira', help: 'Ve todo lo compartido, sin cambiar nada' },
]

function dateLabel(iso: string) {
  return new Date(iso).toLocaleDateString('es-ES', { day: 'numeric', month: 'long' })
}

/** Personas del hogar, sus roles e invitaciones (ADR-0026, OF-1601). */
export function MembersSettings() {
  const { me, notify } = useHousehold()
  const owner = me.role === 'owner'
  const [members, setMembers] = useState<Member[] | null>(null)
  const [invitations, setInvitations] = useState<Invitation[]>([])
  const [role, setRole] = useState<Role>('editor')
  const [link, setLink] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    // Es un complemento de Ajustes: si falla, el resto sigue funcionando.
    api.members(controller.signal).then(setMembers, () => undefined)
    if (owner) api.invitations(controller.signal).then(setInvitations, () => undefined)
    return () => controller.abort()
  }, [owner])

  if (!members) return null

  async function run(action: () => Promise<void>, failure: string) {
    setBusy(true)
    try {
      await action()
    } catch (err) {
      notify(err instanceof ApiError ? err.message : failure)
    } finally {
      setBusy(false)
    }
  }

  const reload = async () => setMembers(await api.members())

  const changeRole = (m: Member, next: Role) =>
    run(async () => {
      await api.setMemberRole(m.id, next)
      await reload()
    }, 'No se ha podido cambiar el rol')

  const remove = (m: Member) =>
    run(async () => {
      await api.removeMember(m.id)
      await reload()
      notify(`${m.display_name} ya no está en el hogar`)
    }, 'No se ha podido quitar a esa persona')

  const invite = () =>
    run(async () => {
      const created = await api.createInvitation(role)
      setInvitations(await api.invitations())
      setLink(`${window.location.origin}/#unirse?token=${created.token}`)
    }, 'No se ha podido crear la invitación')

  const revoke = (i: Invitation) =>
    run(async () => {
      await api.revokeInvitation(i.id)
      setInvitations((all) => all.filter((x) => x.id !== i.id))
    }, 'No se ha podido revocar la invitación')

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(link ?? '')
      notify('Enlace copiado')
    } catch {
      notify('Copia el enlace a mano: el navegador no lo ha permitido')
    }
  }

  return (
    <section className="card stack" aria-label="Personas del hogar">
      <h2>Personas del hogar</h2>
      <ul className="plain">
        {members.map((m) => (
          <li key={m.id}>
            <strong>{m.display_name}</strong>
            {m.is_me && ' (tú)'} ·{' '}
            {owner && !m.is_me ? (
              <select
                aria-label={`Rol de ${m.display_name}`}
                value={m.role}
                disabled={busy}
                onChange={(e) => void changeRole(m, e.target.value as Role)}
              >
                {ROLES.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.label}
                  </option>
                ))}
              </select>
            ) : (
              ROLES.find((r) => r.id === m.role)?.label
            )}{' '}
            {owner && !m.is_me && (
              <button type="button" className="btn small" disabled={busy} onClick={() => void remove(m)}>
                Quitar a {m.display_name}
              </button>
            )}
          </li>
        ))}
      </ul>
      <p className="small muted">El rol decide qué puede cambiar cada persona, no qué ve: las cuentas personales son solo de su titular.</p>

      {owner && (
        <>
          <h3>Invitar a alguien</h3>
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault()
              void invite()
            }}
          >
            <label className="field">
              <span>Qué podrá hacer</span>
              <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
                {ROLES.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.label} · {r.help}
                  </option>
                ))}
              </select>
            </label>
            <button type="submit" className="btn" disabled={busy}>
              Crear invitación
            </button>
          </form>
          {link && (
            <div className="stack" role="status">
              <p className="small">
                Pásale este enlace: <strong>solo se enseña ahora</strong> y vale 7 días y una sola vez.
              </p>
              <input readOnly value={link} aria-label="Enlace de la invitación" onFocus={(e) => e.currentTarget.select()} />
              <button type="button" className="btn small" onClick={() => void copy()}>
                Copiar enlace
              </button>
            </div>
          )}
          {invitations.length > 0 && (
            <ul className="plain" aria-label="Invitaciones pendientes">
              {invitations.map((i) => (
                <li key={i.id}>
                  {ROLES.find((r) => r.id === i.role)?.label} · caduca el {dateLabel(i.expires_at)}{' '}
                  <button type="button" className="btn small" disabled={busy} onClick={() => void revoke(i)}>
                    Revocar invitación
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  )
}
