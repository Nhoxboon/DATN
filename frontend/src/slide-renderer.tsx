import { createRoot, type Root } from 'react-dom/client'
import { SlideExportDocument } from './components/slides/SlideExportDocument'
import './styles/global.css'
import type { SlideDeckJson } from './types'

declare global {
  interface Window {
    __SLIDE_DECK__?: SlideDeckJson
    __SLIDE_RENDER_READY__?: boolean
    __SLIDE_RENDERER_VERSION__?: string
    renderSlideDeck?: (deck: SlideDeckJson) => Promise<boolean>
  }
}

const SLIDE_RENDERER_VERSION = 'v5-title-layout'

window.__SLIDE_RENDERER_VERSION__ = SLIDE_RENDERER_VERSION

const rootElement = document.getElementById('root')
let root: Root | null = null

if (rootElement) {
  root = createRoot(rootElement)
}

async function waitForImages() {
  const images = Array.from(document.images)
  await Promise.all(
    images.map((image) => {
      if (image.complete) {
        return Promise.resolve()
      }
      return new Promise<void>((resolve) => {
        image.addEventListener('load', () => resolve(), { once: true })
        image.addEventListener('error', () => resolve(), { once: true })
      })
    }),
  )
}

async function waitForStableRender() {
  await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))
  await document.fonts.ready
  await waitForImages()
  await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
}

window.renderSlideDeck = async (deck: SlideDeckJson) => {
  if (!root) {
    throw new Error('Slide renderer root was not found.')
  }
  window.__SLIDE_RENDER_READY__ = false
  window.__SLIDE_DECK__ = deck
  root.render(<SlideExportDocument deck={deck} />)
  await waitForStableRender()
  window.__SLIDE_RENDER_READY__ = true
  return true
}

if (window.__SLIDE_DECK__) {
  void window.renderSlideDeck?.(window.__SLIDE_DECK__)
}
