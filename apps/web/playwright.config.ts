import { defineConfig, devices } from '@playwright/test'

/**
 * Pruebas de extremo a extremo (OF-503) contra una instancia en marcha: por defecto la de
 * Docker Compose en modo directo. En local, `E2E_BASE_URL=http://localhost:5173` con `make api`
 * y `make web`. Las credenciales son las de `openfinance demo` salvo que se indiquen otras.
 */
export const STORAGE_STATE = 'test-results/.auth/session.json'

export default defineConfig({
  testDir: './e2e',
  outputDir: 'test-results',
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:8080',
    ignoreHTTPSErrors: Boolean(process.env.E2E_INSECURE_TLS),
    locale: 'es-ES',
    // Las trazas guardan peticiones con la contraseña y la cookie: en CI no se generan,
    // porque los informes se suben como artefactos.
    trace: process.env.CI ? 'off' : 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    // Una sola sesión para todos los proyectos: nginx limita el login a 10 por minuto.
    { name: 'setup', testMatch: /auth\.setup\.ts/, use: { ...devices['Desktop Chrome'] } },
    {
      name: 'mobile-chrome',
      dependencies: ['setup'],
      use: { ...devices['Pixel 7'], viewport: { width: 360, height: 780 }, storageState: STORAGE_STATE },
    },
    {
      name: 'mobile-safari',
      dependencies: ['setup'],
      use: { ...devices['iPhone 13'], storageState: STORAGE_STATE },
    },
    {
      name: 'desktop',
      dependencies: ['setup'],
      use: { ...devices['Desktop Chrome'], storageState: STORAGE_STATE },
    },
  ],
})
