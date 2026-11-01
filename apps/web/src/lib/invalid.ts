/** Atributos de accesibilidad de un campo con (o sin) error; el `id` es el de su `FieldError`. */
export function invalid(id: string, message?: string | null) {
  return message ? { 'aria-invalid': true as const, 'aria-describedby': id } : {}
}
