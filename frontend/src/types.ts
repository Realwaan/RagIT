export type Source = { citation_id: number; filename: string; page: number; parent_text: string; doc_id?: string; image_url?: string; visual_id?: string; caption?: string; bbox?: number[]; crop_scope?: string; evidence_origin?: 'extracted' | 'ai_interpretation'; verification_status?: string; linked_visuals?: {title: string; image_url?: string; page?: number}[] };
export type Result = { query: string; answer: string; status: string; sources: Source[]; generation_mode?: string; evaluation?: {confidence?: number; citation_verified?: boolean; visual_support?: string}; classification?: Record<string, unknown>; total_ms?: number };
export type VisualProgress = { status: string; completed: number; failed: number; total: number };
export type Document = { doc_id: string; filename: string; pages?: number; visual_analysis?: VisualProgress; total_chunks?: number; classification?: { label?: string }; background_indexing?: { status: string }; cache_warning?: string };
export type Session = { id: string; title: string; customTitle?: boolean; updated: number; doc?: Document; repository?: unknown; draft?: string };

export async function request(path: string, init?: RequestInit) {
  const response = await fetch(path, init);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const detail = typeof error.detail === 'string' ? error.detail : Array.isArray(error.detail)
      ? error.detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join(' ') : '';
    throw new Error(detail || (response.status === 413 ? 'This file exceeds the upload limit. Choose a smaller document.' : 'Request failed. Please try again.'));
  }
  return response;
}
