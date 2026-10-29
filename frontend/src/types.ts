export type Source = { citation_id: number; filename: string; page: number; parent_text: string; doc_id?: string; image_url?: string; visual_id?: string; caption?: string; bbox?: number[]; crop_scope?: string; evidence_origin?: 'extracted' | 'ai_interpretation'; verification_status?: string; linked_visuals?: {title: string; image_url?: string; page?: number}[] };
export type Result = { query: string; answer: string; status: string; sources: Source[]; generation_mode?: string; evaluation?: {retrieval_score?: number; claim_support?: string; claims?: {text: string; status: string; reason: string}[]; citation_verified?: boolean; visual_support?: string}; classification?: Record<string, unknown>; total_ms?: number };
export type VisualProgress = { status: string; completed: number; failed: number; total: number };
export type Document = { doc_id: string; filename: string; pages?: number; visual_analysis?: VisualProgress; total_chunks?: number; classification?: { label?: string }; background_indexing?: { status: string }; cache_warning?: string };
export type Session = { id: string; title: string; customTitle?: boolean; updated: number; doc?: Document; repository?: unknown; draft?: string };

let tokenProvider: (() => Promise<string | null>) | undefined;
export function setTokenProvider(provider: typeof tokenProvider) { tokenProvider = provider; }

async function resolveToken(): Promise<string | null> {
  if (!tokenProvider) return null;
  try {
    let token = await tokenProvider();
    if (!token) {
      await new Promise((r) => setTimeout(r, 150));
      token = await tokenProvider();
    }
    return token;
  } catch (err) {
    console.warn("Failed resolving token from Clerk session:", err);
    return null;
  }
}

export async function request(path: string, init?: RequestInit) {
  const headers = new Headers(init?.headers);
  const token = await resolveToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  let response = await fetch(path, { ...init, headers, credentials: 'include' });
  if (response.status === 401 && tokenProvider) {
    await new Promise((r) => setTimeout(r, 250));
    const retryToken = await resolveToken();
    if (retryToken) {
      headers.set("Authorization", `Bearer ${retryToken}`);
    }
    response = await fetch(path, { ...init, headers, credentials: 'include' });
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const detail = typeof error.detail === 'string' ? error.detail : Array.isArray(error.detail)
      ? error.detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join(' ') : '';
    throw new Error(detail || (response.status === 413 ? 'This file exceeds the upload limit. Choose a smaller document.' : 'Request failed. Please try again.'));
  }
  return response;
}
