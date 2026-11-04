import { ApiError, api, type Me, type RevertResult } from '../api/client'
import type { Notify } from '../components/useToast'

/** Qué decir tras deshacer: si algo se respetó porque alguien lo cambió después, quién. */
export function revertMessage(r: RevertResult, me: Me, done = 'Deshecho'): string {
  if (r.kept === 0) return done
  const names = r.kept_by.map((id) => (id === me.user.id ? 'tú' : (me.members.find((m) => m.id === id)?.display_name ?? 'alguien')))
  const who = names.length ? ` (lo cambió después ${names.join(' y ')})` : ''
  return `${done}. ${r.kept === 1 ? '1 cambio se ha respetado' : `${r.kept} cambios se han respetado`}${who}`
}

/** Aviso con «Deshacer» para una operación del registro de cambios (ADR-0017). */
export function notifyUndoable(
  notify: Notify,
  me: Me,
  message: string,
  operationId: string | null | undefined,
  afterUndo: () => void,
): void {
  if (!operationId) {
    notify(message)
    return
  }
  notify(message, {
    label: 'Deshacer',
    run: () => {
      api.undo(operationId).then(
        (r) => {
          notify(revertMessage(r, me))
          afterUndo()
        },
        (err: unknown) => notify(err instanceof ApiError ? err.message : 'No se ha podido deshacer'),
      )
    },
  })
}
