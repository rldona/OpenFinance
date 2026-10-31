export function ComingSoon({ title, ticket }: { title: string; ticket: string }) {
  return (
    <section>
      <h1>{title}</h1>
      <div className="card empty">
        <p>
          Esta pantalla llegará con <strong>{ticket}</strong>. Mientras tanto podéis importar extractos y revisar los
          movimientos.
        </p>
        <a className="btn" href="#movimientos">
          Ver movimientos
        </a>
      </div>
    </section>
  )
}
