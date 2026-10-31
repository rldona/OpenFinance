/** Máximo «redondo» para el eje: 1, 2, 2.5 o 5 por potencia de 10. */
export function niceMax(value: number): number {
  if (!(value > 0)) return 1
  const p = 10 ** Math.floor(Math.log10(value))
  return [1, 2, 2.5, 5, 10].map((k) => k * p).find((x) => x >= value) ?? value
}
