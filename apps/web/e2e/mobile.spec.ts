import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { type Page, expect, test } from '@playwright/test'

/**
 * OF-503: las pantallas se usan en un móvil (360–390 px) y en escritorio sin scroll horizontal,
 * con gráficos que caben y se leen. Ver ADR-0014 para los gráficos.
 */

const TABS = [
  { id: 'mes', title: 'Este mes' },
  { id: 'gastos', title: '¿En qué gastamos?' },
  { id: 'evolucion', title: 'Evolución' },
  { id: 'ahorrar', title: 'Ahorrar' },
  { id: 'movimientos', title: 'Movimientos' },
  { id: 'importar', title: 'Importar extracto' },
] as const

const HIDDEN = [
  { id: 'categorias', title: 'Categorías' },
  { id: 'presupuestos', title: 'Presupuestos' },
] as const

const FIXTURE = join(import.meta.dirname, '../../../services/api/tests/fixtures/revolut_joint_synthetic.csv')
const MIN_TOUCH = 40
const MIN_LABEL_PX = 11

const isMobile = (name: string) => name.startsWith('mobile')

async function settle(page: Page, title: string) {
  await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible()
  await page.waitForLoadState('networkidle')
  await expect(page.getByText('Cargando…')).toHaveCount(0)
}

async function shot(page: Page, name: string) {
  const dir = process.env.E2E_SCREENSHOTS
  if (dir) await page.screenshot({ path: join(dir, `${test.info().project.name}-${name}.png`), fullPage: true })
}

/** Ancho de la ventana configurada: en móvil `innerWidth` crece si el contenido se desborda. */
const viewportWidth = (page: Page) => page.viewportSize()?.width ?? 0

async function expectNoHorizontalScroll(page: Page) {
  const width = viewportWidth(page)
  const { scrollWidth, wide } = await page.evaluate(
    (w) => ({
      scrollWidth: document.documentElement.scrollWidth,
      // Los elementos más profundos que se salen, para saber qué arreglar.
      wide: Array.from(document.body.querySelectorAll('*'))
        .filter((el) => el.getBoundingClientRect().right > w + 1 && !el.closest('.tabs, .sr-only'))
        .filter((el, _, all) => !all.some((other) => other !== el && el.contains(other)))
        .slice(0, 5)
        .map((el) => `${el.tagName.toLowerCase()}.${el.className} → ${Math.round(el.getBoundingClientRect().right)}`),
    }),
    width,
  )
  expect(scrollWidth, `la página no se desplaza en horizontal: ${wide.join(', ')}`).toBeLessThanOrEqual(width + 1)
}

/**
 * Los gráficos que miden su ancho (`useChartWidth`) dibujan con un `viewBox` igual al ancho de su
 * figura. Hasta que coinciden en dos lecturas seguidas, la geometría aún no es la definitiva.
 */
async function waitForChartsSized(page: Page) {
  let previous = ''
  await expect
    .poll(
      async () => {
        const state = await page.evaluate(() =>
          Array.from(document.querySelectorAll('main figure.chart:not(.donut)')).map((figure) => {
            const width = Math.round(figure.getBoundingClientRect().width)
            const viewBox = figure.querySelector('svg')?.viewBox.baseVal.width ?? 0
            return width === 0 || viewBox === width ? `${width}` : `${viewBox}≠${width}`
          }),
        )
        const snapshot = state.join(',')
        const stable = snapshot === previous && !snapshot.includes('≠')
        previous = snapshot
        return stable ? 'estable' : snapshot
      },
      { message: 'el ancho de los gráficos se estabiliza', intervals: [50, 100, 200] },
    )
    .toBe('estable')
}

async function expectChartsFit(page: Page) {
  await waitForChartsSized(page)
  const problems = await page.evaluate(
    ({ minLabel, width }) => {
      const out: string[] = []
      const visible = (el: Element) => {
        const r = el.getBoundingClientRect()
        return r.width > 0 && r.height > 0
      }
      for (const svg of Array.from(document.querySelectorAll('main svg')).filter(visible)) {
        const r = svg.getBoundingClientRect()
        if (r.left < -1 || r.right > width + 1) out.push(`svg fuera del viewport (${r.left}–${r.right})`)
        const texts = Array.from(svg.querySelectorAll('text')).filter(visible)
        for (const t of texts) {
          const scale = (t as SVGTextElement).getScreenCTM()?.a ?? 1
          const px = parseFloat(getComputedStyle(t).fontSize) * scale
          if (px < minLabel - 0.05) out.push(`«${t.textContent}» a ${px.toFixed(1)} px`)
          const tr = t.getBoundingClientRect()
          if (tr.left < r.left - 2 || tr.right > r.right + 2) out.push(`«${t.textContent}» se sale del gráfico`)
        }
        const axis = texts.map((t) => ({ text: t.textContent, box: t.getBoundingClientRect() }))
        for (let i = 0; i < axis.length; i++)
          for (let j = i + 1; j < axis.length; j++) {
            const a = axis[i].box
            const b = axis[j].box
            const w = Math.min(a.right, b.right) - Math.max(a.left, b.left)
            const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top)
            if (w > 1 && h > 1) out.push(`«${axis[i].text}» se solapa con «${axis[j].text}»`)
          }
      }
      return out
    },
    { minLabel: MIN_LABEL_PX, width: viewportWidth(page) },
  )
  expect(problems, 'gráficos dentro del viewport y legibles').toEqual([])
}

async function expectTouchTargets(page: Page) {
  const small = await page.evaluate(
    ({ min }) =>
      Array.from(
        document.querySelectorAll(
          '.tabs a, .top .btn, .top summary, main .btn.primary, main .month-picker button, form .field',
        ),
      )
        .map((el) => ({ el, r: el.getBoundingClientRect() }))
        .filter(({ r }) => r.width > 0 && r.height > 0 && (r.height < min || r.width < min))
        .map(({ el, r }) => `${el.textContent?.trim() || el.tagName} ${Math.round(r.width)}×${Math.round(r.height)}`),
    { min: MIN_TOUCH },
  )
  expect(small, `objetivos táctiles de al menos ${MIN_TOUCH} px`).toEqual([])
}

async function expectTabsReachable(page: Page) {
  const nav = page.getByRole('navigation', { name: 'Secciones' })
  for (const tab of TABS) {
    const link = nav.getByRole('link', { name: tab.title === 'Importar extracto' ? 'Importar' : tab.title })
    await link.scrollIntoViewIfNeeded()
    await expect(link).toBeInViewport()
  }
}

async function checkScreen(page: Page, name: string) {
  await expectNoHorizontalScroll(page)
  await expectChartsFit(page)
  if (isMobile(test.info().project.name)) await expectTouchTargets(page)
  await shot(page, name)
}

test.describe('pantallas', () => {
  for (const tab of TABS) {
    test(`${tab.title} cabe y se lee`, async ({ page }) => {
      await page.goto('/#mes')
      await settle(page, 'Este mes')
      await expectTabsReachable(page)
      const nav = page.getByRole('navigation', { name: 'Secciones' })
      const link = nav.getByRole('link', { name: tab.id === 'importar' ? 'Importar' : tab.title })
      await link.scrollIntoViewIfNeeded()
      await link.click()
      await expect(link).toHaveAttribute('aria-current', 'page')
      await settle(page, tab.title)
      await checkScreen(page, tab.id)
    })
  }

  for (const screen of HIDDEN) {
    test(`${screen.title} cabe y se lee`, async ({ page }) => {
      await page.goto(`/#${screen.id}`)
      await settle(page, screen.title)
      await checkScreen(page, screen.id)
    })
  }

  test.describe('sin sesión', () => {
    test.use({ storageState: { cookies: [], origins: [] } })

    test('el acceso cabe en la pantalla', async ({ page }) => {
      await page.goto('/')
      await expect(page.getByRole('form', { name: 'Iniciar sesión' })).toBeVisible()
      await expectNoHorizontalScroll(page)
      if (isMobile(test.info().project.name)) await expectTouchTargets(page)
      await shot(page, 'login')
    })
  })
})

test('importar un extracto en tres pasos', async ({ page }, info) => {
  test.skip(!isMobile(info.project.name), 'el flujo de escritorio lo cubren los tests de componentes')
  // Descripciones únicas por ejecución: el mismo extracto dos veces no crea movimientos nuevos.
  const tag = `e2e ${info.project.name} ${Date.now()}`
  const [header, ...rows] = readFileSync(FIXTURE, 'utf8').trimEnd().split('\n')
  const csv = [
    header,
    ...rows.map((row) =>
      row.replace(/^((?:[^,]*,){4})("[^"]*"|[^,]*)/, (_, head: string, desc: string) =>
        desc.startsWith('"') ? `${head}${desc.slice(0, -1)} ${tag}"` : `${head}${desc} ${tag}`,
      ),
    ),
  ].join('\n')

  await page.goto('/#importar')
  await settle(page, 'Importar extracto')
  await expect(page.locator('.step[aria-current="step"]')).toContainText('Subir extracto')
  await page.getByLabel('Extracto').setInputFiles({ name: 'extracto.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) })
  await page.getByRole('button', { name: 'Ver vista previa' }).click()

  await expect(page.locator('.step[aria-current="step"]')).toContainText('Revisar')
  await expect(page.getByText(`Mercadona ${tag}`)).toBeVisible()
  await checkScreen(page, 'importar-revisar')
  await page.getByRole('button', { name: /^Importar \d+ movimientos?$/ }).click()

  await expect(page.locator('.step[aria-current="step"]')).toContainText('Listo')
  await expect(page.getByRole('heading', { name: /Importados? \d+ movimientos?/ })).toBeVisible()
  await checkScreen(page, 'importar-listo')
})

test('la exportación se descarga', async ({ page }) => {
  await page.goto('/#mes')
  await settle(page, 'Este mes')
  await page.getByText('Exportar', { exact: true }).click()
  const json = page.getByRole('link', { name: 'JSON' })
  await expect(json).toBeInViewport()
  await expectNoHorizontalScroll(page)
  await shot(page, 'exportar')

  const download = page.waitForEvent('download')
  await json.click()
  expect((await download).suggestedFilename()).toMatch(/\.json$/)

  for (const format of ['json', 'csv']) {
    const res = await page.request.get(`/api/v1/export?format=${format}`)
    expect(res.status()).toBe(200)
    expect(res.headers()['content-disposition']).toContain('attachment')
  }
})
