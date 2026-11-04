# ADR-0014: Custom SVG charts in React

- Status: Accepted
- Date: 2026-10-31

## Context

Phase 3 (OF-302 to OF-305) needs these charts: donut, bars with a reference line and a highlighted month, stacked bars, lines with area, and a progress ring (phase 4). They are few and simple, with small data volumes: 12 months and about 15 categories. They must:

- look good on mobile (OF-503);
- be accessible;
- be testable with the same tests as the rest of the web app (Vitest + jsdom);
- not treat amounts as `float`.

The prototype (`docs/product/prototypes/charts.js`) already draws them by hand with SVG in about 150 lines.

### Measurements

The same set (donut, bars with reference, and lines) was built with each option, using `esbuild --minify` and gzip -9 in production. The table shows how much each one adds on top of the React 19 baseline (69.1 KB gzip):

| Option | Version | Adds (gzip) | Technology |
| --- | --- | --- | --- |
| Custom SVG | — | ≈ 0.2 KB per chart (≈ 4 KB for all) | SVG in React |
| Chart.js | 4.6.1 | 61.7 KB | `<canvas>` |
| Recharts | 3.10.1 | 121.6 KB | SVG (with d3 dependencies) |

The whole web app currently weighs ≈ 74 KB gzip; Recharts would almost triple it.

### Other criteria

| Criterion | Custom SVG | Chart.js | Recharts |
| --- | --- | --- | --- |
| Accessibility | `role="img"`, `aria-label`, `<title>` and an equivalent table for screen readers | Canvas: a bitmap with no structure; the data has to be duplicated separately | Accessible SVG, but with its own layers to configure |
| Tests in jsdom | The DOM of each bar can be inspected | jsdom does not implement canvas: it has to be mocked | Needs mocking `ResizeObserver` and container measurements |
| Mobile | Scalable `viewBox`, no container measuring | Resizes via JS | `ResponsiveContainer` resizes via JS |
| Maintenance | Our own code (≈ 300 lines), no dependencies | Mature dependency, imperative API | Large dependency, API changes between major versions |
| Advanced interaction (zoom, range selection) | No | Yes, via plugins | Partial |

## Decision

Port the prototype's SVG charts to React components, in `apps/web/src/components/charts/`:

- **Accessibility:** each chart is drawn inside a `<figure>` with `role="img"` and an `aria-label` that summarizes the main data point. It also includes a visually hidden data table (`.sr-only`) for screen readers and a `<title>` per element, which serves as a native tooltip.
- **Scaling:** a `viewBox` is used and the chart takes 100 % of the width, without measuring the container.
- **Amounts:** the API keeps sending exact decimal text. For drawing, amounts are converted to cents (`BigInt`) and from there to `Number`. That `Number` is used only to compute geometry; the figures that are displayed always come from the original text through `formatMoney`.
- **Calculations in the Core:** totals, averages and aggregates are computed in the backend (OF-301); the components only paint.

## Consequences

- The web app size practically does not change (≈ 4 KB) and no dependency is added.
- The charts are tested with Testing Library like any other component.
- We maintain axes, scales and labels ourselves; edge cases (negative values, months with no data) must be tested.
- This decision will be revisited if advanced interaction is needed (zoom, range selection, or long series spanning many years). The preferred alternative then would be a low-level, modular library, or Chart.js if canvas is accepted.
