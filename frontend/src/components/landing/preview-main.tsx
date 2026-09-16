/**
 * preview-main.tsx — scratch mount for screenshotting Landing in isolation.
 * Not imported by the real app; entry point is frontend/landing-preview.html.
 */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '../../index.css'
import Landing from './Landing'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Landing onStart={() => console.log('[preview] onStart fired')} />
  </StrictMode>,
)
