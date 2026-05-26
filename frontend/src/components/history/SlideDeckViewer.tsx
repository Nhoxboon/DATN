import {
  Box,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Code2,
  Cpu,
  Database,
  Download,
  Gamepad2,
  Gauge,
  Globe2,
  Layers,
  ListChecks,
  Network,
  Package,
  Palette,
  Repeat2,
  Rocket,
  Route,
  Search,
  Server,
  ShieldCheck,
  Timer,
  TriangleAlert,
  Workflow,
  Zap,
  ZoomIn,
  ZoomOut,
  type LucideIcon,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import type {
  SlideCalloutComponent,
  SlideCardComponent,
  SlideChecklistComponent,
  SlideDeckDocument,
  SlideDeckSlide,
  SlideIconKey,
  SlideMetricComponent,
} from '../../types'

const SLIDE_CANVAS_WIDTH = 1600
const SLIDE_CANVAS_HEIGHT = 900
const VIEWER_BASE_SCALE = 0.5375

interface SlideDeckViewerProps {
  document: SlideDeckDocument
  onRefreshPdfUrl?: (document: SlideDeckDocument) => Promise<{ pdfUrl: string; expiresAt: number } | null>
}

export function SlideDeckViewer({ document, onRefreshPdfUrl }: SlideDeckViewerProps) {
  const slides = document.deckJson?.slides ?? []
  const [activeIndex, setActiveIndex] = useState(0)
  const [zoom, setZoom] = useState(1)
  const activeSlide = slides[Math.min(activeIndex, Math.max(slides.length - 1, 0))]
  const previewScale = VIEWER_BASE_SCALE * zoom

  const slideFrameStyle = useMemo(
    () => ({
      width: `${SLIDE_CANVAS_WIDTH * previewScale}px`,
      height: `${SLIDE_CANVAS_HEIGHT * previewScale}px`,
    }),
    [previewScale],
  )
  const slideStyle = useMemo(
    () => ({
      width: `${SLIDE_CANVAS_WIDTH}px`,
      height: `${SLIDE_CANVAS_HEIGHT}px`,
      transform: `scale(${previewScale})`,
      transformOrigin: 'top left',
    }),
    [previewScale],
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
          <div className="mx-auto" style={slideFrameStyle}>
            <div style={slideStyle}>
              <SlideCanvas slide={activeSlide} deckTitle={document.title} />
            </div>
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

export function SlideCanvas({
  slide,
  deckTitle,
}: {
  slide: SlideDeckSlide
  deckTitle: string
}) {
  const visualUrl = slide.visual?.data_url || null
  const anchorVisualUrl = slide.components?.visual_anchor?.data_url || null
  const content = slide.content ?? {}
  const layout = slide.layout_type

  if (layout === 'TRANSITION' || layout === 'SECTION_DIVIDER') {
    return <SectionDivider slide={slide} deckTitle={deckTitle} />
  }

  return (
    <div className="aspect-video w-full overflow-hidden bg-[#f7fafb] p-[5.5%] text-ink shadow-[0_20px_80px_rgba(0,0,0,0.25)]">
      <div className="mb-5 h-1.5 w-full bg-[#1f5666]" />
      {layout === 'TITLE_HERO' ? (
        <TitleHero slide={slide} deckTitle={deckTitle} visualUrl={anchorVisualUrl || visualUrl} />
      ) : layout === 'DUAL_PILLARS' ? (
        <DualPillars slide={slide} />
      ) : layout === 'GRID_COMPOSITE' ? (
        <GridComposite slide={slide} />
      ) : layout === 'PROCESS_FLOW_WITH_CALLOUT' ? (
        <ProcessFlowWithCallout slide={slide} />
      ) : layout === 'VISUAL_ANCHOR' ? (
        <VisualAnchorSlide slide={slide} visualUrl={anchorVisualUrl || visualUrl} />
      ) : layout === 'METRIC_DASHBOARD' ? (
        <MetricDashboard slide={slide} />
      ) : layout === 'CODE_COMPARISON' ? (
        <CodeComparison slide={slide} />
      ) : layout === 'CHECKLIST' ? (
        <ChecklistSlide slide={slide} />
      ) : layout === 'TITLE' ? (
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
      ) : layout === 'HIGHLIGHT_CARD' ? (
        <HighlightCard slide={slide} visualUrl={visualUrl} />
      ) : layout === 'TIMELINE' ? (
        <TimelineSlide content={content} />
      ) : layout === 'SUMMARY' ? (
        <SummarySlide slide={slide} />
      ) : (
        <BulletSlide slide={slide} />
      )}
    </div>
  )
}

function SectionDivider({ slide, deckTitle }: { slide: SlideDeckSlide; deckTitle: string }) {
  return (
    <div className="aspect-video w-full overflow-hidden bg-[#1f5666] p-[5.5%] text-white shadow-[0_20px_80px_rgba(0,0,0,0.25)]">
      <div className="mb-10 h-1.5 w-40 bg-[#d89c2b]" />
      <div className="flex h-[74%] flex-col justify-center">
        <h3 className="max-w-[78%] text-[clamp(2rem,4vw,4.4rem)] font-bold leading-[1.05]">{slide.title || deckTitle}</h3>
        {slide.subtitle && <p className="mt-6 max-w-[72%] text-[clamp(1rem,2vw,1.8rem)] leading-tight text-[#dce9ed]">{slide.subtitle}</p>}
      </div>
    </div>
  )
}

function TitleHero({ slide, deckTitle, visualUrl }: { slide: SlideDeckSlide; deckTitle: string; visualUrl: string | null }) {
  const anchor = slide.components?.visual_anchor
  return (
    <div className="grid h-[78%] items-center gap-8 md:grid-cols-[1.45fr_0.9fr]">
      <div>
        <h3 className="max-w-[92%] text-[clamp(2rem,4vw,4.4rem)] font-bold leading-[1.05] text-[#1f5666]">
          {slide.title || deckTitle}
        </h3>
        {slide.subtitle && <p className="mt-5 max-w-[88%] text-[clamp(1rem,2vw,2rem)] leading-tight">{slide.subtitle}</p>}
      </div>
      <VisualAnchorBlock iconKey={anchor?.icon_key || 'rocket'} caption={anchor?.caption || null} visualUrl={visualUrl} />
    </div>
  )
}

function DualPillars({ slide }: { slide: SlideDeckSlide }) {
  const cards = slide.components?.cards?.slice(0, 2) ?? []
  return (
    <div className="grid h-[78%] items-center gap-6 md:grid-cols-2">
      {cards.map((card, index) => (
        <ComponentCard key={card.id || `${slide.slide_number}-pillar-${index}`} card={card} size="large" />
      ))}
    </div>
  )
}

function GridComposite({ slide }: { slide: SlideDeckSlide }) {
  const cards = slide.components?.cards?.slice(0, 3) ?? []
  return (
    <div className="grid h-[78%] items-center gap-4 md:grid-cols-3">
      {cards.map((card, index) => (
        <ComponentCard key={card.id || `${slide.slide_number}-grid-${index}`} card={card} />
      ))}
    </div>
  )
}

function ComponentCard({ card, size = 'normal' }: { card: SlideCardComponent; size?: 'normal' | 'large' }) {
  const style = tagStyle(card.tag)
  return (
    <div className={`h-full rounded-lg border p-5 ${style.shell}`}>
      <div className="mb-5 flex items-center justify-between gap-3">
        <IconBadge iconKey={card.icon_key || 'check'} className={style.icon} />
        <span className={`text-[clamp(0.58rem,0.9vw,0.72rem)] font-bold uppercase tracking-[0.08em] ${style.label}`}>
          {(card.tag || 'DEFAULT').replace('_', ' ')}
        </span>
      </div>
      <h4 className={`${size === 'large' ? 'text-[clamp(1.15rem,2vw,1.7rem)]' : 'text-[clamp(0.95rem,1.55vw,1.25rem)]'} mb-4 font-bold leading-tight text-[#1f5666]`}>
        {card.heading}
      </h4>
      <p className="text-[clamp(0.74rem,1.2vw,0.98rem)] leading-snug text-[#2b3437]">{card.desc}</p>
    </div>
  )
}

function ProcessFlowWithCallout({ slide }: { slide: SlideDeckSlide }) {
  const steps = slide.components?.flow_steps?.slice(0, 5) ?? []
  return (
    <div className="flex h-[78%] flex-col justify-center gap-6">
      <div className="grid gap-3 md:grid-cols-5">
        {steps.map((step, index) => (
          <div key={`${slide.slide_number}-flow-${index}`} className="relative rounded-lg border border-[#d9e2e6] bg-white p-4">
            <div className="mb-4 inline-flex h-8 w-8 items-center justify-center rounded-full bg-[#1f5666] text-[0.72rem] font-bold text-white">
              {step.step || index + 1}
            </div>
            <h4 className="mb-2 text-[clamp(0.75rem,1.1vw,0.95rem)] font-bold leading-tight text-[#1f5666]">{step.label}</h4>
            <p className="text-[clamp(0.62rem,0.95vw,0.78rem)] leading-snug text-[#2b3437]">{step.action}</p>
          </div>
        ))}
      </div>
      {slide.components?.callout_box && <CalloutBox callout={slide.components.callout_box} />}
    </div>
  )
}

function VisualAnchorSlide({ slide, visualUrl }: { slide: SlideDeckSlide; visualUrl: string | null }) {
  const anchor = slide.components?.visual_anchor
  return (
    <div className="grid h-[78%] items-center gap-6 md:grid-cols-[1.35fr_1fr]">
      <VisualAnchorBlock iconKey={anchor?.icon_key || 'workflow'} caption={anchor?.caption || null} visualUrl={visualUrl} />
      <div>
        <h3 className="mb-5 text-[clamp(1.4rem,3vw,2.6rem)] font-bold leading-tight text-[#1f5666]">{slide.title}</h3>
        {slide.subtitle && <p className="text-[clamp(0.85rem,1.5vw,1.16rem)] leading-snug">{slide.subtitle}</p>}
        {slide.components?.callout_box && <div className="mt-6"><CalloutBox callout={slide.components.callout_box} /></div>}
      </div>
    </div>
  )
}

function MetricDashboard({ slide }: { slide: SlideDeckSlide }) {
  const metrics = slide.components?.metrics?.slice(0, 5) ?? []
  return (
    <div className="grid h-[78%] items-center gap-4 md:grid-cols-3">
      {metrics.map((metric, index) => (
        <MetricTile key={`${slide.slide_number}-metric-${index}`} metric={metric} />
      ))}
    </div>
  )
}

function MetricTile({ metric }: { metric: SlideMetricComponent }) {
  return (
    <div className="rounded-lg border border-[#d9e2e6] bg-white p-5">
      <IconBadge iconKey={metric.icon_key || 'gauge'} className="bg-[#eef9fb] text-[#1f5666]" />
      <div className="mt-5 text-[clamp(1.8rem,4vw,3.8rem)] font-bold leading-none text-[#1f5666]">{metric.value}</div>
      <div className="mt-3 text-[clamp(0.8rem,1.25vw,1.02rem)] font-semibold leading-tight">{metric.label}</div>
      <p className="mt-2 text-[clamp(0.65rem,1vw,0.82rem)] leading-snug text-[#586064]">{metric.context}</p>
    </div>
  )
}

function CodeComparison({ slide }: { slide: SlideDeckSlide }) {
  const rows = slide.components?.comparison?.slice(0, 4) ?? []
  return (
    <div className="grid h-[78%] items-center gap-6 md:grid-cols-2">
      <div className="h-full rounded-lg bg-[#202529] p-5 text-white">
        <div className="mb-4 text-[0.72rem] font-bold uppercase tracking-[0.08em] text-[#d89c2b]">Before</div>
        {rows.map((row, index) => (
          <ComparisonSnippet key={`before-${index}`} label={row.label} value={row.left} />
        ))}
      </div>
      <div className="h-full rounded-lg border border-[#d9e2e6] bg-white p-5">
        <div className="mb-4 text-[0.72rem] font-bold uppercase tracking-[0.08em] text-[#1f5666]">After</div>
        {rows.map((row, index) => (
          <ComparisonSnippet key={`after-${index}`} label={row.label} value={row.right} />
        ))}
      </div>
    </div>
  )
}

function ComparisonSnippet({ label, value }: { label?: string; value?: string }) {
  return (
    <div className="mb-4">
      {label && <div className="mb-1 text-[0.62rem] uppercase tracking-[0.08em] text-[#819097]">{label}</div>}
      <p className="font-mono text-[clamp(0.62rem,1vw,0.82rem)] leading-snug">{value}</p>
    </div>
  )
}

function ChecklistSlide({ slide }: { slide: SlideDeckSlide }) {
  const items = slide.components?.checklist?.slice(0, 5) ?? []
  return (
    <div className="flex h-[78%] flex-col justify-center gap-3">
      {items.map((item, index) => (
        <ChecklistRow key={`${slide.slide_number}-check-${index}`} item={item} />
      ))}
    </div>
  )
}

function ChecklistRow({ item }: { item: SlideChecklistComponent }) {
  return (
    <div className="flex items-center gap-4 rounded-lg border border-[#d9e2e6] bg-white px-5 py-4">
      <IconBadge iconKey={item.icon_key || 'check'} className="bg-[#ecfdf5] text-[#059669]" />
      <p className="text-[clamp(0.78rem,1.35vw,1.08rem)] font-semibold leading-snug text-[#2b3437]">{item.text}</p>
    </div>
  )
}

function VisualAnchorBlock({ iconKey, caption, visualUrl }: { iconKey: SlideIconKey | string; caption: string | null; visualUrl: string | null }) {
  return (
    <div className="flex h-full flex-col items-center justify-center rounded-lg border border-[#d9e2e6] bg-white p-6">
      {visualUrl ? (
        <img src={visualUrl} alt={caption || ''} className="max-h-[78%] max-w-full object-contain" />
      ) : (
        <div className="flex h-36 w-36 items-center justify-center rounded-full bg-[#eef9fb] text-[#1f5666]">
          <SlideIcon iconKey={iconKey} className="h-16 w-16" />
        </div>
      )}
      {caption && <p className="mt-5 max-w-[88%] text-center text-[clamp(0.72rem,1.2vw,0.95rem)] leading-snug text-[#586064]">{caption}</p>}
    </div>
  )
}

function CalloutBox({ callout }: { callout: SlideCalloutComponent }) {
  const style = calloutStyle(callout.type)
  return (
    <div className={`flex items-start gap-4 rounded-lg border px-5 py-4 ${style.shell}`}>
      <IconBadge iconKey={style.iconKey} className={style.icon} />
      <div>
        <div className={`mb-1 text-[0.68rem] font-bold uppercase tracking-[0.08em] ${style.label}`}>{callout.type || 'INSIGHT'}</div>
        <p className={`text-[clamp(0.72rem,1.15vw,0.95rem)] font-semibold leading-snug ${style.text}`}>{callout.text}</p>
      </div>
    </div>
  )
}

function IconBadge({ iconKey, className }: { iconKey: SlideIconKey | string; className?: string }) {
  return (
    <span className={`inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${className || 'bg-[#eef9fb] text-[#1f5666]'}`}>
      <SlideIcon iconKey={iconKey} className="h-5 w-5" />
    </span>
  )
}

function SlideIcon({ iconKey, className }: { iconKey: SlideIconKey | string; className?: string }) {
  const Icon = ICON_MAP[iconKey as SlideIconKey] || CheckCircle2
  return <Icon className={className} />
}

const ICON_MAP: Record<SlideIconKey, LucideIcon> = {
  cpu: Cpu,
  globe: Globe2,
  gauge: Gauge,
  database: Database,
  layers: Layers,
  box: Box,
  route: Route,
  workflow: Workflow,
  warning: TriangleAlert,
  check: CheckCircle2,
  rocket: Rocket,
  zap: Zap,
  code: Code2,
  palette: Palette,
  gamepad: Gamepad2,
  package: Package,
  server: Server,
  shield: ShieldCheck,
  search: Search,
  'list-checks': ListChecks,
  repeat: Repeat2,
  timer: Timer,
  network: Network,
}

function tagStyle(tag: SlideCardComponent['tag']) {
  if (tag === 'RECOMMENDED') {
    return { shell: 'border-emerald-500/40 bg-emerald-500/5', icon: 'bg-emerald-500/10 text-emerald-600', label: 'text-emerald-600' }
  }
  if (tag === 'WARNING') {
    return { shell: 'border-amber-500/45 bg-amber-500/10', icon: 'bg-amber-500/15 text-amber-700', label: 'text-amber-700' }
  }
  if (tag === 'INSIGHT') {
    return { shell: 'border-cyan-600/30 bg-cyan-500/5', icon: 'bg-cyan-500/10 text-cyan-700', label: 'text-cyan-700' }
  }
  if (tag === 'LEGACY') {
    return { shell: 'border-slate-400/45 bg-slate-50', icon: 'bg-slate-200 text-slate-700', label: 'text-slate-600' }
  }
  if (tag === 'MID_LEVEL') {
    return { shell: 'border-violet-500/30 bg-violet-500/5', icon: 'bg-violet-500/10 text-violet-700', label: 'text-violet-700' }
  }
  return { shell: 'border-[#d9e2e6] bg-white', icon: 'bg-[#eef9fb] text-[#1f5666]', label: 'text-[#1f5666]' }
}

function calloutStyle(type: SlideCalloutComponent['type']) {
  if (type === 'WARNING') {
    return { shell: 'border-amber-500 bg-[#2b250f] text-[#fff4cf]', icon: 'bg-amber-500/20 text-amber-300', label: 'text-amber-300', text: 'text-[#fff4cf]', iconKey: 'warning' as const }
  }
  if (type === 'RECOMMENDED') {
    return { shell: 'border-emerald-500/40 bg-emerald-500/5', icon: 'bg-emerald-500/10 text-emerald-600', label: 'text-emerald-600', text: 'text-emerald-800', iconKey: 'check' as const }
  }
  return { shell: 'border-cyan-600/30 bg-cyan-500/5', icon: 'bg-cyan-500/10 text-cyan-700', label: 'text-cyan-700', text: 'text-[#1f5666]', iconKey: 'zap' as const }
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

function SummarySlide({ slide }: { slide: SlideDeckSlide }) {
  const bullets = slide.bullets?.length ? slide.bullets.slice(0, 3) : visibleStrings(slide.content).slice(0, 3)
  return (
    <div className="flex h-[78%] flex-col justify-center">
      <h3 className="mb-8 max-w-[78%] text-[clamp(1.3rem,3vw,2.6rem)] font-bold leading-tight text-[#1f5666]">{slide.title}</h3>
      <div className="grid gap-4 md:grid-cols-3">
        {bullets.map((bullet, index) => (
          <div key={`${slide.slide_number}-summary-${index}`} className="min-h-40 rounded-lg border border-[#d9e2e6] bg-white p-5">
            <div className="mb-5 inline-flex h-8 w-8 items-center justify-center rounded-full bg-[#d89c2b] text-[0.75rem] font-bold text-white">{index + 1}</div>
            <p className="text-[clamp(0.8rem,1.35vw,1.08rem)] font-semibold leading-snug text-[#1f5666]">{bullet}</p>
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

function TimelineSlide({ content }: { content: Record<string, unknown> }) {
  const steps = Array.isArray(content.steps)
    ? content.steps.slice(0, 4)
    : visibleStrings(content)
        .slice(0, 4)
        .map((text, index) => ({ title: `Step ${index + 1}`, text }))
  return (
    <div className="flex h-[78%] items-center">
      <div className="relative grid w-full gap-4 md:grid-cols-4">
        <div className="absolute left-[8%] right-[8%] top-10 hidden h-1 bg-[#c7d5da] md:block" />
        {steps.map((step, index) => {
          const item = step && typeof step === 'object' ? (step as Record<string, unknown>) : {}
          return (
            <div key={`timeline-${index}`} className="relative">
              <div className="mb-5 inline-flex h-12 w-12 items-center justify-center rounded-full bg-[#1f5666] text-sm font-bold text-white">{index + 1}</div>
              <h4 className="mb-3 text-[clamp(0.9rem,1.5vw,1.22rem)] font-bold leading-tight text-[#1f5666]">{String(item.title || '')}</h4>
              <p className="text-[clamp(0.72rem,1.2vw,0.95rem)] leading-snug text-[#2b3437]">{String(item.text || '')}</p>
            </div>
          )
        })}
      </div>
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

function HighlightCard({ slide, visualUrl }: { slide: SlideDeckSlide; visualUrl: string | null }) {
  const content = slide.content ?? {}
  return (
    <div className={`grid h-[78%] items-center gap-6 ${visualUrl ? 'md:grid-cols-[1.05fr_1fr]' : ''}`}>
      {visualUrl && (
        <div className="flex h-full items-center justify-center rounded-lg border border-[#d9e2e6] bg-white">
          <img src={visualUrl} alt={slide.visual?.alt || ''} className="max-h-full max-w-full object-contain" />
        </div>
      )}
      <div className="rounded-lg border border-[#d9e2e6] bg-white p-8">
        <div className="mb-4 text-[clamp(0.72rem,1.1vw,0.9rem)] font-semibold uppercase tracking-[0.08em] text-[#d89c2b]">{String(content.label || 'Key idea')}</div>
        <h3 className="mb-5 text-[clamp(1.4rem,3vw,2.6rem)] font-bold leading-tight text-[#1f5666]">{slide.title}</h3>
        <p className="text-[clamp(0.85rem,1.5vw,1.16rem)] leading-snug">{String(content.context || '')}</p>
        {content.takeaway ? <p className="mt-5 text-[clamp(0.75rem,1.25vw,0.98rem)] leading-snug text-[#586064]">{String(content.takeaway)}</p> : null}
      </div>
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
