export type Source = { citation_id: number; filename: string; page: number; parent_text: string; image_url?: string; linked_visuals?: {title: string; image_url?: string}[] };
export type Result = { query: string; answer: string; status: string; sources: Source[]; evaluation?: {confidence?: number; citation_verified?: boolean}; classification?: Record<string, unknown>; total_ms?: number };
export type Document = { doc_id: string; filename: string; pages?: number };
export type Session = { id: string; title: string; updated: number; doc?: Document; repository?: unknown; draft?: string };

export async function request(path: string, init?: RequestInit) {
  const response = await fetch(path, init);
  if (!response.ok) { const error = await response.json().catch(() => ({})); throw new Error(error.detail || 'Request failed. Please try again.'); }
  return response;
}
