const MAX_BYTES = 5 * 1024 * 1024

/** Client-side gate before upload; the server re-validates. Returns the
 * user-facing message (what's wrong + what to do), or null when acceptable. */
export function contractFileProblem(file: Pick<File, 'name' | 'type' | 'size'>): string | null {
  if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
    return `“${file.name}” isn't a PDF. Export the contract as PDF, or try the demo contract.`
  }
  if (file.size > MAX_BYTES) {
    return `“${file.name}” is ${(file.size / 1024 / 1024).toFixed(1)} MB. The limit is 5 MB.`
  }
  return null
}
