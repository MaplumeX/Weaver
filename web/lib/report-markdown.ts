export function extractCitationNumber(text: string): string | null {
  const match = String(text || '').trim().match(/^\[(\d+)\]$/)
  return match ? match[1] : null
}

export function splitInlineCitations(text: string): Array<{ type: 'text' | 'citation'; value: string }> {
  const parts = String(text || '').split(/(\[\d+\])/g)
  return parts
    .filter((part) => part.length > 0)
    .map((part) => {
      const citation = extractCitationNumber(part)
      if (citation) {
        return { type: 'citation' as const, value: citation }
      }
      return { type: 'text' as const, value: part }
    })
}
