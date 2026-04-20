import type {
  ChatMessage,
  NotebookDetail,
  NotebookSummary,
  UploadCandidate,
  UserProfile,
} from '../types'

export const userProfile: UserProfile = {
  id: 'aris-thorne',
  name: 'Prof. Aris Thorne',
  role: 'Curator Workspace',
  avatarLabel: 'AT',
}

export const notebookSummaries: NotebookSummary[] = [
  {
    id: 'historical-analysis',
    category: 'Historical Analysis',
    title: 'The Impact of Renaissance Humanism on Modern Education',
    sourceCount: 12,
    updatedAt: 'Updated Oct 24, 2023',
    description: 'A comparative reading of liberal arts traditions and contemporary pedagogy.',
  },
  {
    id: 'neuroscience',
    category: 'Neuroscience',
    title: 'Neural Plasticity in Adult Language Acquisition',
    sourceCount: 8,
    updatedAt: 'Updated Nov 02, 2023',
    description: 'Research threads linking memory formation, repetition, and late-stage fluency.',
  },
  {
    id: 'ethics-ai',
    category: 'Ethics & AI',
    title: 'Algorithmic Bias in Predictive Policing Systems',
    sourceCount: 24,
    updatedAt: 'Updated Oct 12, 2023',
    description: 'Evidence gathering around disparate impact, procurement, and oversight.',
  },
  {
    id: 'economics',
    category: 'Economics',
    title: 'Decentralized Finance: Risks and Market Efficiency',
    sourceCount: 5,
    updatedAt: 'Updated Nov 15, 2023',
    description: 'A working notebook focused on volatility, governance, and liquidity failures.',
  },
  {
    id: 'philosophy',
    category: 'Philosophy',
    title: 'Stoicism in the Age of Digital Distraction',
    sourceCount: 19,
    updatedAt: 'Updated Yesterday',
    description: 'A synthesis notebook connecting classical practice with modern attention design.',
  },
]

const baseSources = [
  {
    id: 'product-spec',
    name: 'Product_Spec.pdf',
    kind: 'pdf' as const,
    meta: 'PDF Document • 24 pages',
    selected: true,
  },
  {
    id: 'design-guide',
    name: 'Design_Guide.docx',
    kind: 'docx' as const,
    meta: 'Word Doc • 12 pages',
    selected: true,
  },
  {
    id: 'market-analysis',
    name: 'Market_Analysis_2024.pdf',
    kind: 'pdf' as const,
    meta: 'PDF Document • 31 pages',
    selected: false,
  },
]

const baseStudioDocs = [
  {
    id: 'tech-design-note',
    icon: 'description' as const,
    title: 'Tech-Design Alignment Note',
    excerpt:
      'Synthesis of architectural constraints and visual design requirements for the 2024 launch...',
    updatedAt: 'Updated 2h ago',
  },
  {
    id: 'feature-matrix',
    icon: 'table_chart' as const,
    title: 'Feature Comparison Matrix',
    excerpt:
      'Comparison of MVP features against stakeholder requirements from the product spec...',
    updatedAt: 'Updated yesterday',
  },
]

const notebookSpecificCopy: Record<
  string,
  Pick<NotebookDetail, 'synthesisTitle' | 'synthesisBody' | 'synthesisBullets'>
> = {
  'historical-analysis': {
    synthesisTitle: 'Pedagogical Throughline',
    synthesisBody:
      'Humanist schooling centered on rhetoric, civic formation, and close reading. Modern liberal arts curricula preserve that structure, but redistribute authority from canonical mastery toward interdisciplinary interpretation.',
    synthesisBullets: [
      'Curricular continuity: grammar, rhetoric, and moral inquiry remain the backbone of general education.',
      'Institutional shift: elite tutoring becomes scalable classroom methodology through standardized texts.',
      'Editorial note: the strongest sources connect humanism to learner agency, not just canon formation.',
    ],
  },
  neuroscience: {
    synthesisTitle: 'Adult Language Acquisition',
    synthesisBody:
      'The evidence cluster suggests adult learners retain substantial adaptive capacity when practice is high-frequency, feedback-rich, and tied to meaning rather than rote repetition.',
    synthesisBullets: [
      'Plasticity does not disappear; it becomes more dependent on deliberate reinforcement.',
      'Sleep, spaced retrieval, and social conversation all appear as compounding variables.',
      'The notebook should separate laboratory evidence from classroom application in the next draft.',
    ],
  },
  'ethics-ai': {
    synthesisTitle: 'Synthetic Analysis',
    synthesisBody:
      'The core technical requirements outlined in Product_Spec.pdf focus on a modular architecture designed for high throughput. This directly supports the "Digital Atelier" philosophy described in the Design_Guide.docx, which emphasizes fluid workflows and minimal latency.',
    synthesisBullets: [
      'System Response: the specification mandates 100ms response times for all AI-driven UI updates, reinforcing the "Effortless Interaction" principle.',
      'Visual Consistency: technical CSS variable definitions mirror the "No-Line" visual hierarchy rules from the branding guide.',
      'Overall, the technical constraints appear well-integrated with the desired aesthetic outcomes for the platform.',
    ],
  },
  economics: {
    synthesisTitle: 'Liquidity and Trust',
    synthesisBody:
      'Across the collected sources, market efficiency claims collapse first under governance ambiguity and second under reflexive liquidity shocks. Adoption narratives consistently understate those dependencies.',
    synthesisBullets: [
      'Liquidity incentives improve early growth but often hide systemic fragility.',
      'Protocol governance remains the largest qualitative variable across comparable case studies.',
      'The next note should isolate exchange failures from protocol-native failures.',
    ],
  },
  philosophy: {
    synthesisTitle: 'Attention as Practice',
    synthesisBody:
      'The sources agree that stoic discipline maps unusually well onto digital self-regulation, but only when framed as a repeatable practice rather than an abstract ethic of detachment.',
    synthesisBullets: [
      'Marcus Aurelius is cited as reflection methodology, not merely as a moral authority.',
      'Modern distraction research works best when paired with ritual and journaling design patterns.',
      'The synthesis should end with a practical framework for daily rehearsal.',
    ],
  },
  'new-research-project': {
    synthesisTitle: 'Studio Warm Start',
    synthesisBody:
      'This blank workspace is preloaded with the editorial studio shell so you can begin collecting sources and drafting a synthesis immediately.',
    synthesisBullets: [
      'Upload primary material into the left rail before starting a synthesis.',
      'Use the center column to capture arguments, tensions, and citations.',
      'Save refined notes into the studio panel for later presentation work.',
    ],
  },
}

export const notebookDetails: Record<string, NotebookDetail> = Object.fromEntries(
  [
    ...notebookSummaries,
    {
      id: 'new-research-project',
      category: 'Research Studio',
      title: 'New Research Project',
      sourceCount: 0,
      updatedAt: 'Updated just now',
      description: 'Create a blank workspace to start collecting sources.',
    },
  ].map((summary) => {
    const synthesis = notebookSpecificCopy[summary.id] ?? notebookSpecificCopy['ethics-ai']

    return [
      summary.id,
      {
        ...summary,
        synthesisTitle: synthesis.synthesisTitle,
        synthesisBody: synthesis.synthesisBody,
        synthesisBullets: synthesis.synthesisBullets,
        sources: baseSources.map((source, index) => ({
          ...source,
          id: `${summary.id}-${source.id}`,
          selected: index < 2,
        })),
        studioDocuments: baseStudioDocs.map((document) => ({
          ...document,
          id: `${summary.id}-${document.id}`,
        })),
      } satisfies NotebookDetail,
    ]
  }),
)

export const uploadCandidates: UploadCandidate[] = [
  {
    id: 'cognitive-architecture',
    name: 'Cognitive_Architecture_2024.pdf',
    kind: 'pdf',
    sizeLabel: '1.2 MB',
  },
  {
    id: 'research-methods',
    name: 'Research_Methods_Draft.docx',
    kind: 'docx',
    sizeLabel: '840 KB',
  },
  {
    id: 'interview-transcript',
    name: 'Interview_Transcript_V2.pdf',
    kind: 'pdf',
    sizeLabel: '2.1 MB',
  },
]

export const initialChatMessages: Record<string, ChatMessage[]> = {
  default: [
    {
      id: 'assistant-opening',
      role: 'assistant',
      timestamp: '09:14 AM',
      content:
        'Drafting context enabled. Sources cited automatically. I can turn the active source set into a synthesis note, a comparison matrix, or presentation-ready bullets.',
    },
  ],
}
