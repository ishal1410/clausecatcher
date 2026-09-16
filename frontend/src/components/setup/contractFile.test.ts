import { describe, expect, it } from 'vitest'
import { contractFileProblem } from './contractFile'

describe('contractFileProblem', () => {
  it('accepts a PDF by mime type or by extension', () => {
    expect(contractFileProblem({ name: 'msa.pdf', type: 'application/pdf', size: 1000 })).toBeNull()
    expect(contractFileProblem({ name: 'MSA.PDF', type: '', size: 1000 })).toBeNull()
  })
  it('rejects non-PDFs, naming the file', () => {
    expect(contractFileProblem({ name: 'notes.txt', type: 'text/plain', size: 10 })).toMatch(/notes\.txt.*isn't a PDF/)
  })
  it('rejects files over 5 MB', () => {
    expect(contractFileProblem({ name: 'big.pdf', type: 'application/pdf', size: 5 * 1024 * 1024 + 1 })).toMatch(/5\.0 MB.*limit is 5 MB/)
    expect(contractFileProblem({ name: 'edge.pdf', type: 'application/pdf', size: 5 * 1024 * 1024 })).toBeNull()
  })
})
