'use client'

import { cn } from "@/lib/utils"

interface FilterOption {
  label: string
  value: string
}

interface FilterGroupProps {
  options: FilterOption[]
  value: string
  onChange: (value: string) => void
  className?: string
}

export function FilterGroup({ options, value, onChange, className }: FilterGroupProps) {
  return (
    <div className={cn("flex flex-wrap gap-2", className)}>
      {options.map((option) => (
        <button
          type="button"
          key={option.value}
          onClick={() => onChange(option.value)}
          className={cn(
            "px-3 py-1.5 text-sm font-medium rounded-full border border-border/30 backdrop-blur-sm transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            value === option.value
              ? "bg-primary text-primary-foreground border-primary shadow-sm"
              : "bg-background/80 text-muted-foreground hover:bg-accent hover:text-foreground hover:border-border/60"
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
