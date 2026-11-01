import { Component, type ReactNode } from 'react'

type Props = { children: ReactNode }

/** Si una pantalla falla al pintarse, lo dice y ofrece recargar en vez de quedarse congelada. */
export class ErrorBoundary extends Component<Props, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <div className="center" role="alert">
        <p className="error">Algo ha fallado al mostrar esta pantalla.</p>
        <button className="btn" type="button" onClick={() => window.location.reload()}>
          Recargar
        </button>
      </div>
    )
  }
}
