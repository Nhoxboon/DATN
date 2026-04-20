import { Paperclip, Send } from 'lucide-react'
import { useState } from 'react'

interface ChatComposerProps {
  disabled?: boolean
  onSubmit: (value: string) => void
}

export function ChatComposer({ disabled = false, onSubmit }: ChatComposerProps) {
  const [value, setValue] = useState('')

  const handleSubmit = () => {
    if (!value.trim()) {
      return
    }

    onSubmit(value)
    setValue('')
  }

  return (
    <div className="border-t border-black/10 bg-white px-5 py-5">
      <div className="flex items-center gap-3 rounded-[18px] bg-surface-low px-4 py-3.5">
        <button type="button" className="text-muted transition hover:text-ink">
          <Paperclip className="h-4 w-4" />
        </button>
        <label className="flex-1">
          <span className="sr-only">Ask Scholar Script</span>
          <input
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder="Ask a question about your sources..."
            className="w-full bg-transparent text-[0.92rem] text-ink outline-none placeholder:text-muted"
          />
        </label>
        <button
          type="button"
          onClick={handleSubmit}
          disabled={disabled}
          className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-primary text-white transition hover:brightness-105 disabled:opacity-60"
        >
          <Send className="h-4.5 w-4.5" />
        </button>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-4 px-2 pt-3 text-[0.66rem] text-muted">
        <span>Drafting context enabled</span>
        <span>Sources cited automatically</span>
      </div>
    </div>
  )
}
