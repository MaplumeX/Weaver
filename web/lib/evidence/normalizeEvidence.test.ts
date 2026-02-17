import { describe, expect, it } from 'vitest'

import type { components } from '../api-types'
import { groupEvidencePassages } from './normalizeEvidence'

type EvidencePassageItem = components['schemas']['EvidencePassageItem']

describe('groupEvidencePassages', () => {
  it('groups passages by url then heading_path', () => {
    const passages: EvidencePassageItem[] = [
      {
        url: 'https://example.com/a',
        text: 'Alpha',
        start_char: 0,
        end_char: 5,
        heading_path: ['Section A'],
        snippet_hash: 'h1',
      },
      {
        url: 'https://example.com/a',
        text: 'Beta',
        start_char: 10,
        end_char: 14,
        heading_path: ['Section A'],
        snippet_hash: 'h2',
      },
      {
        url: 'https://example.com/a',
        text: 'Gamma',
        start_char: 20,
        end_char: 25,
        heading_path: ['Section B'],
        snippet_hash: 'h3',
      },
      {
        url: 'https://example.com/b',
        text: 'Intro text',
        start_char: 0,
        end_char: 9,
        heading: 'Intro',
        snippet_hash: 'h4',
      },
    ]

    const pages = groupEvidencePassages(passages)
    expect(pages).toHaveLength(2)

    const pageA = pages.find(p => p.url === 'https://example.com/a')
    expect(pageA?.uniquePassages).toBe(3)
    expect(pageA?.totalPassages).toBe(3)
    expect(pageA?.headings.map(h => h.key)).toEqual(['Section A', 'Section B'])
    expect(pageA?.headings[0]?.passages).toHaveLength(2)

    const pageB = pages.find(p => p.url === 'https://example.com/b')
    expect(pageB?.headings.map(h => h.key)).toEqual(['Intro'])
    expect(pageB?.headings[0]?.passages[0]?.text).toBe('Intro text')
  })

  it('dedupes passages within the same url by snippet_hash', () => {
    const passages: EvidencePassageItem[] = [
      {
        url: 'https://example.com/a',
        text: 'Alpha',
        start_char: 0,
        end_char: 5,
        heading_path: ['Section A'],
        snippet_hash: 'same',
      },
      {
        url: 'https://example.com/a',
        text: 'Alpha duplicate',
        start_char: 100,
        end_char: 120,
        heading_path: ['Section A'],
        snippet_hash: 'same',
      },
      {
        url: 'https://example.com/b',
        text: 'Other url same hash',
        start_char: 0,
        end_char: 10,
        heading_path: ['Section A'],
        snippet_hash: 'same',
      },
    ]

    const pages = groupEvidencePassages(passages)

    const pageA = pages.find(p => p.url === 'https://example.com/a')
    expect(pageA?.totalPassages).toBe(2)
    expect(pageA?.uniquePassages).toBe(1)
    expect(pageA?.headings[0]?.passages).toHaveLength(1)

    const pageB = pages.find(p => p.url === 'https://example.com/b')
    expect(pageB?.uniquePassages).toBe(1)
  })
})

