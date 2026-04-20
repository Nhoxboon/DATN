import { Eye, EyeOff } from 'lucide-react'
import { useState } from 'react'

interface AuthFieldProps {
  label: string
  placeholder?: string
  type?: 'text' | 'email' | 'password'
  value: string
  onChange: (value: string) => void
}

export function AuthField({
  label,
  placeholder,
  type = 'text',
  value,
  onChange,
}: AuthFieldProps) {
  const [reveal, setReveal] = useState(false)
  const isPassword = type === 'password'

  return (
    <label className="space-y-2 text-sm font-medium text-ink">
      <span>{label}</span>
      <div className="relative">
        <input
          type={isPassword && reveal ? 'text' : type}
          placeholder={placeholder}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="w-full rounded-[var(--radius-panel)] bg-white px-4 py-3.5 text-sm text-ink shadow-[inset_0_0_0_1px_rgba(171,179,183,0.18)] outline-none transition placeholder:text-muted/80 focus:shadow-[inset_0_0_0_1.5px_var(--primary),0_0_0_4px_rgba(0,91,192,0.08)]"
        />
        {isPassword && (
          <button
            type="button"
            onClick={() => setReveal((current) => !current)}
            className="absolute inset-y-0 right-3 flex items-center text-muted transition hover:text-ink"
            aria-label={reveal ? 'Hide password' : 'Show password'}
          >
            {reveal ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        )}
      </div>
    </label>
  )
}
