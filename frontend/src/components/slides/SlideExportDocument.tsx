import { SlideCanvas } from '../history/SlideDeckViewer'
import type { SlideDeckJson } from '../../types'

export function SlideExportDocument({ deck }: { deck: SlideDeckJson }) {
  const slides = Array.isArray(deck.slides) ? deck.slides : []

  return (
    <main className="min-h-screen bg-white">
      {slides.map((slide) => (
        <section
          key={`slide-export-${slide.slide_number}`}
          className="slide-render-page h-[900px] w-[1600px] overflow-hidden bg-white"
          data-slide-number={slide.slide_number}
        >
          <SlideCanvas slide={slide} deckTitle={deck.title || 'Presentation'} />
        </section>
      ))}
    </main>
  )
}
