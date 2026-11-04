/** Error de un campo, justo debajo de él. El campo lo enlaza con `aria-describedby={id}` y `aria-invalid`. */
export function FieldError({ id, message }: { id: string; message?: string | null }) {
  if (!message) return null
  return (
    <p id={id} className="small error field-error" role="alert">
      {message}
    </p>
  )
}
