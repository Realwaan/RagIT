export type Source = { citation_id: number; filename: string; page: number; parent_text: string; doc_id?: string; image_url?: string; visual_id?: string; caption?: string; bbox?: number[]; crop_scope?: string; evidence_origin?: 'extracted' | 'ai_interpretation'; verification_status?: string; linked_visuals?: {id?: string; title: string; image_url?: string; page?: number; bbox?: number[]}[] };
export type TokenTelemetry = { grounded_prompt_tokens?: number; grounded_completion_tokens?: number; grounded_total_tokens?: number; total_tokens?: number; generation_mode?: string; model_used?: string; total_ast_nodes?: number; cross_modal_links?: number; indexing_duration_ms?: number };
export type Result = { query: string; answer: string; status: string; sources: Source[]; generation_mode?: string; model_used?: string; retrieval_ms?: number; total_ms?: number; token_telemetry?: TokenTelemetry; evaluation?: {retrieval_score?: number; claim_support?: string; claims?: {text: string; status: string; reason: string}[]; citation_verified?: boolean; visual_support?: string}; classification?: Record<string, unknown> };
export type VisualProgress = { status: string; completed: number; failed: number; total: number };
export type Document = { doc_id: string; filename: string; pages?: number; visual_analysis?: VisualProgress; total_chunks?: number; classification?: { label?: string }; background_indexing?: { status: string }; cache_warning?: string };
export type Session = { id: string; title: string; customTitle?: boolean; updated: number; doc?: Document; repository?: unknown; draft?: string; uploadJob?: { id: string; filename: string } };

export type ComplianceControlResult = {
  id: string;
  control: string;
  category: string;
  title: string;
  criticality: string;
  status: 'PASS' | 'GAP';
  badge: string;
  retrieval_score: number;
  matched_terms: string[];
  clause_excerpt: string;
  excerpt: string;
  full_clause: string;
  page: number | null;
  image_url: string;
  citation_id: number | null;
  finding: string;
  remediation_clause: string;
  redline_diff: string | null;
  action_plan: string;
  rationale: string;
};

export type ComplianceAuditReport = {
  doc_id: string;
  filename: string;
  framework: string;
  framework_name: string;
  overall_score: number;
  total_checks: number;
  passed_count: number;
  gaps_count: number;
  verdict: string;
  verdict_color: 'emerald' | 'amber' | 'red';
  checklist: ComplianceControlResult[];
  classification?: Record<string, unknown>;
};

export type DiscrepancyFinding = {
  paragraph_id: string;
  visual_id: string;
  page: number;
  image_url?: string;
  status: 'CONTRADICTION' | 'CAUTION' | 'ALIGN';
  title: string;
  text_claim: string;
  visual_fact: string;
  discrepancy_delta: string;
  confidence: number;
};

export type DiscrepancyReport = {
  doc_id: string;
  filename: string;
  total_pairs_audited: number;
  contradictions_count: number;
  caution_count: number;
  aligned_count: number;
  consistency_score: number;
  verdict: 'FLAGGED' | 'CAUTION' | 'CONSISTENT';
  findings: DiscrepancyFinding[];
};

export type CustomCheckDraft = {
  id: string;
  title: string;
  query: string;
  category: string;
  criticality: 'CRITICAL' | 'HIGH' | 'MEDIUM';
  required_terms: string[];
  standard_clause?: string;
  action_required?: string;
};

export class RequestError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

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
    throw new RequestError(detail || (response.status === 413 ? 'This file exceeds the upload limit. Choose a smaller document.' : 'Request failed. Please try again.'), response.status);
  }
  return response;
}
