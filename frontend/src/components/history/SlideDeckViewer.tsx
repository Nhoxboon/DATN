import { ChevronLeft, ChevronRight, Download, ZoomIn, ZoomOut } from 'lucide-react'
import { useMemo, useState } from 'react'
import { slideDeckService } from '../../services/slideDeckService'
import type { SlideDeckDocument, SlideDeckSlide } from '../../types'

interface SlideDeckViewerProps {
  document: SlideDeckDocument
  onRefreshPdfUrl?: (document: SlideDeckDocument) => Promise<{ pdfUrl: string; expiresAt: number } | null>
}

export function SlideDeckViewer({ document, onRefreshPdfUrl }: SlideDeckViewerProps) {
  const slides = document.deckJson?.slides ?? []
  const [activeIndex, setActiveIndex] = useState(0)
  const [zoom, setZoom] = useState(1)
  const activeSlide = slides[Math.min(activeIndex, Math.max(slides.length - 1, 0))]
  const subtitle = slideDeckService.sourceLabel(document.sourceCount)

  const slideStyle = useMemo(
    () => ({
      transform: `scale(${zoom})`,
      transformOrigin: 'top center',
    }),
    [zoom],
  )

  const downloadPdf = async () => {
    const existingUrl = document.pdfUrl
    const pdf = existingUrl ? { pdfUrl: existingUrl } : await onRefreshPdfUrl?.(document)
    if (pdf?.pdfUrl) {
      window.open(pdf.pdfUrl, '_blank', 'noopener,noreferrer')
    }
  }

  if (document.status !== 'completed') {
    return (
      <div className="rounded-xl border border-outline/60 bg-surface-low px-4 py-5 text-sm text-muted">
        {document.errorMessage || document.excerpt}
      </div>
    )
  }

  if (!activeSlide || !slides.length) {
    return (
      <div className="rounded-xl border border-outline/60 bg-surface-low px-4 py-5 text-sm text-muted">
        This presentation has no slide preview.
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[0.7rem] font-semibold uppercase tracking-[0.14em] text-muted">Presentation</div>
          <div className="mt-1 text-[0.76rem] text-muted">{subtitle}</div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setZoom((current) => Math.max(0.72, current - 0.1))}
            className="rounded-md p-2 text-muted transition hover:bg-surface-low hover:text-ink"
            aria-label="Zoom out"
          >
            <ZoomOut className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => setZoom((current) => Math.min(1.25, current + 0.1))}
            className="rounded-md p-2 text-muted transition hover:bg-surface-low hover:text-ink"
            aria-label="Zoom in"
          >
            <ZoomIn className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => {
              void downloadPdf()
            }}
            className="inline-flex items-center gap-2 rounded-lg bg-ink px-3 py-2 text-[0.72rem] font-semibold text-white transition hover:bg-primary"
          >
            <Download className="h-4 w-4" />
            PDF
          </button>
        </div>
      </div>

      <div className="grid min-h-[430px] gap-4 lg:grid-cols-[132px_minmax(0,1fr)]">
        <div className="max-h-[560px] space-y-2 overflow-y-auto pr-1">
          {slides.map((slide, index) => (
            <button
              key={`${document.id}-thumb-${slide.slide_number}`}
              type="button"
              onClick={() => setActiveIndex(index)}
              className={`flex aspect-video w-full items-center justify-center rounded-md border bg-white p-2 text-left text-[0.58rem] leading-4 transition ${
                index === activeIndex ? 'border-primary shadow-[0_0_0_2px_rgba(0,91,192,0.14)]' : 'border-outline/70'
              }`}
            >
              <span className="line-clamp-3 text-ink">{slide.title}</span>
            </button>
          ))}
        </div>

        <div className="overflow-auto rounded-xl bg-[#202529] p-4">
          <div className="mx-auto w-full max-w-[860px]" style={slideStyle}>
            <SlidePreview slide={activeSlide} deckTitle={document.title} sourceCount={document.sourceCount} />
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => setActiveIndex((current) => Math.max(0, current - 1))}
          disabled={activeIndex === 0}
          className="inline-flex items-center gap-2 rounded-lg border border-outline/70 px-3 py-2 text-[0.72rem] font-semibold text-ink transition hover:bg-surface-low disabled:opacity-40"
        >
          <ChevronLeft className="h-4 w-4" />
          Previous
        </button>
        <span className="text-[0.72rem] text-muted">
          {activeIndex + 1} / {slides.length}
        </span>
        <button
          type="button"
          onClick={() => setActiveIndex((current) => Math.min(slides.length - 1, current + 1))}
          disabled={activeIndex >= slides.length - 1}
          className="inline-flex items-center gap-2 rounded-lg border border-outline/70 px-3 py-2 text-[0.72rem] font-semibold text-ink transition hover:bg-surface-low disabled:opacity-40"
        >
          Next
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}

function SlidePreview({
  slide,
  deckTitle,
  sourceCount,
}: {
  slide: SlideDeckSlide
  deckTitle: string
  sourceCount: number
}) {
  const visualUrl = slide.visual?.data_url || null
  const content = slide.content ?? {}
  const layout = slide.layout_type

  return (
    <div className="aspect-video w-full overflow-hidden bg-[#f7fafb] p-[5.5%] text-ink shadow-[0_20px_80px_rgba(0,0,0,0.25)]">
      <div className="mb-5 h-1.5 w-full bg-[#1f5666]" />
      {layout === 'TITLE' ? (
        <div className="flex h-[78%] flex-col justify-center">
          <h3 className="max-w-[82%] text-[clamp(2rem,4vw,4.4rem)] font-bold leading-[1.05] text-[#1f5666]">
            {slide.title || deckTitle}
          </h3>
          {slide.subtitle && <p className="mt-5 max-w-[78%] text-[clamp(1rem,2vw,2rem)] leading-tight">{slide.subtitle}</p>}
          {visualUrl && <img src={visualUrl} alt={slide.visual?.alt || ''} className="mt-7 max-h-[34%] w-full object-contain" />}
        </div>
      ) : layout === 'TWO_COLUMNS' ? (
        <TwoColumns content={content} />
      ) : layout === 'THREE_FEATURES' ? (
        <ThreeFeatures content={content} />
      ) : layout === 'BIG_STAT' ? (
        <BigStat content={content} />
      ) : layout === 'FIGURE_FOCUS' ? (
        <FigureFocus slide={slide} visualUrl={visualUrl} />
      ) : (
        <BulletSlide slide={slide} />
      )}
      <div className="mt-auto text-[clamp(0.55rem,1vw,0.8rem)] text-[#819097]">
        Based on {sourceCount} source{sourceCount === 1 ? '' : 's'}
      </div>
    </div>
  )
}

function BulletSlide({ slide }: { slide: SlideDeckSlide }) {
  const bullets = slide.bullets?.length ? slide.bullets : visibleStrings(slide.content).slice(0, 4)
  return (
    <div className="flex h-[78%] flex-col justify-center">
      <h3 className="mb-8 max-w-[78%] text-[clamp(1.3rem,3vw,2.6rem)] font-bold leading-tight text-[#1f5666]">{slide.title}</h3>
      <div className="grid gap-4">
        {bullets.map((bullet, index) => (
          <div key={`${slide.slide_number}-bullet-${index}`} className="flex items-start gap-3 text-[clamp(0.86rem,1.6vw,1.4rem)] leading-snug">
            <span className="mt-2 h-2.5 w-2.5 shrink-0 rounded-full bg-[#d89c2b]" />
            <span>{bullet}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function TwoColumns({ content }: { content: Record<string, unknown> }) {
  const left = arrayOfStrings(content.left)
  const right = arrayOfStrings(content.right)
  return (
    <div className="grid h-[78%] items-center gap-6 md:grid-cols-2">
      <Column title={String(content.left_title || 'Focus')} items={left} />
      <Column title={String(content.right_title || 'Contrast')} items={right} />
    </div>
  )
}

function Column({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="h-full rounded-lg border border-[#d9e2e6] bg-white p-6">
      <h4 className="mb-5 text-[clamp(0.8rem,1.4vw,1.2rem)] font-semibold uppercase tracking-[0.08em] text-[#1f5666]">{title}</h4>
      <div className="space-y-4 text-[clamp(0.78rem,1.3vw,1.05rem)] leading-snug">
        {items.slice(0, 4).map((item) => (
          <p key={item}>{item}</p>
        ))}
      </div>
    </div>
  )
}

function ThreeFeatures({ content }: { content: Record<string, unknown> }) {
  const features = Array.isArray(content.features) ? content.features.slice(0, 3) : []
  return (
    <div className="grid h-[78%] items-center gap-4 md:grid-cols-3">
      {features.map((feature, index) => {
        const item = feature && typeof feature === 'object' ? (feature as Record<string, unknown>) : {}
        return (
          <div key={`feature-${index}`} className="h-full rounded-lg border border-[#d9e2e6] bg-white p-5">
            <div className="mb-5 text-[clamp(0.7rem,1.2vw,1rem)] font-semibold text-[#d89c2b]">0{index + 1}</div>
            <h4 className="mb-3 text-[clamp(0.9rem,1.5vw,1.25rem)] font-bold leading-tight text-[#1f5666]">{String(item.title || '')}</h4>
            <p className="text-[clamp(0.74rem,1.2vw,0.98rem)] leading-snug">{String(item.text || '')}</p>
          </div>
        )
      })}
    </div>
  )
}

function BigStat({ content }: { content: Record<string, unknown> }) {
  return (
    <div className="flex h-[78%] flex-col justify-center rounded-lg border border-[#d9e2e6] bg-white p-8">
      <div className="text-[clamp(2.6rem,6vw,6rem)] font-bold leading-none text-[#1f5666]">{String(content.stat || '')}</div>
      <div className="mt-5 text-[clamp(1rem,2vw,1.7rem)] font-semibold leading-tight">{String(content.label || '')}</div>
      <div className="mt-4 max-w-[76%] text-[clamp(0.72rem,1.3vw,1rem)] text-[#586064]">{String(content.context || '')}</div>
    </div>
  )
}

function FigureFocus({ slide, visualUrl }: { slide: SlideDeckSlide; visualUrl: string | null }) {
  const content = slide.content ?? {}
  return (
    <div className="grid h-[78%] items-center gap-6 md:grid-cols-[1.5fr_1fr]">
      <div className="flex h-full items-center justify-center rounded-lg border border-[#d9e2e6] bg-white">
        {visualUrl ? <img src={visualUrl} alt={slide.visual?.alt || ''} className="max-h-full max-w-full object-contain" /> : <div className="h-24 w-[70%] rounded-full bg-[#d9e2e6]" />}
      </div>
      <div>
        <h3 className="mb-5 text-[clamp(1.2rem,2.5vw,2.1rem)] font-bold leading-tight text-[#1f5666]">{slide.title}</h3>
        <p className="text-[clamp(0.85rem,1.5vw,1.15rem)] leading-snug">{String(content.caption || '')}</p>
        <p className="mt-5 text-[clamp(0.75rem,1.3vw,1rem)] leading-snug text-[#586064]">{String(content.takeaway || '')}</p>
      </div>
    </div>
  )
}

function arrayOfStrings(value: unknown) {
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : []
}

function visibleStrings(value: unknown): string[] {
  if (!value) {
    return []
  }
  if (typeof value === 'string') {
    return value ? [value] : []
  }
  if (Array.isArray(value)) {
    return value.flatMap(visibleStrings)
  }
  if (typeof value === 'object') {
    return Object.values(value).flatMap(visibleStrings)
  }
  return []
}
