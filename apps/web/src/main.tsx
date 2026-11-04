import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './app/App'
import './index.css'
import { applyTheme, getTheme } from './lib/theme'
import { registerServiceWorker } from './lib/pwa'

applyTheme(getTheme())
registerServiceWorker()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
