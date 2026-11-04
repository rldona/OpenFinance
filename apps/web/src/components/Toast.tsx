import type { Notice } from './useToast'

export function Toast({ notice, onDismiss }: { notice: Notice | null; onDismiss: () => void }) {
  return (
    <div className={`toast ${notice ? 'show' : ''}`} role="status" aria-live="polite">
      {notice?.message}
      {notice?.action && (
        <button
          className="toast-action"
          type="button"
          onClick={() => {
            notice.action?.run()
            onDismiss()
          }}
        >
          {notice.action.label}
        </button>
      )}
    </div>
  )
}
