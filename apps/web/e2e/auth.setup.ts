import { expect, test as setup } from '@playwright/test'
import { STORAGE_STATE } from '../playwright.config.ts'

const EMAIL = process.env.E2E_EMAIL ?? 'raul@demo.openfinance'
const PASSWORD = process.env.E2E_PASSWORD ?? 'demo-openfinance'

setup('inicia sesión una vez', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('Email').fill(EMAIL)
  await page.getByLabel('Contraseña').fill(PASSWORD)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await expect(page.getByRole('navigation', { name: 'Secciones' })).toBeVisible()
  await page.context().storageState({ path: STORAGE_STATE })
})
