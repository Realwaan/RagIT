import { useEffect, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import * as Dropdown from '@radix-ui/react-dropdown-menu';
import {
  AlertTriangle,
  BookOpen,
  Check,
  CheckCircle2,
  Copy,
  Download,
  FileText,
  Plus,
  RefreshCw,
  Scale,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';
import {
  request,
  type ComplianceAuditReport,
  type ComplianceControlResult,
  type CustomCheckDraft,
  type DiscrepancyFinding,
  type DiscrepancyReport,
  type Document,
  type Source,
} from '../types';
import { cn, IconButton } from './ui';

type Props = {
  open: boolean;
  documents: Document[];
  currentDoc?: Document;
  onClose: () => void;
  onOpenSource: (source: Source) => void;
};

const FRAMEWORKS = [
  {
    id: 'sla',
    label: 'Cloud SLA',
    summary: 'Uptime guarantees, penalty credits, MFA, incident response & DR',
  },
  {
    id: 'gdpr',
    label: 'GDPR Privacy',
    summary: '72h breach notice, DPO, right to erasure, consent & SCC transfers',
  },
  {
    id: 'financial',
    label: 'Financial & SOX',
    summary: 'Dual wire authorization, segregation of duties & immutable audit logs',
  },
  {
    id: 'custom',
    label: 'Custom Rules',
    summary: 'Define custom contract clauses, policy rules & required terms',
  },
] as const;

const DEFAULT_CUSTOM_CHECKS: CustomCheckDraft[] = [
  {
    id: 'CUST-01',
    title: 'Termination Notice Period',
    query: 'What prior written notice period is required to terminate the agreement for convenience?',
    category: 'Contract Governance',
    criticality: 'HIGH',
    required_terms: ['terminate', 'termination', 'notice', 'days'],
    standard_clause: 'Either party may terminate this Agreement for convenience upon 30 business days prior written notice.',
    action_required: 'Specify a clear written notice period for termination without cause.',
  },
];

function formatAuditMarkdown(report: ComplianceAuditReport): string {
  const lines = [
    `### ${report.framework_name}`,
    `**Verdict:** ${report.verdict} — **Overall Score:** ${report.overall_score}% (${report.passed_count}/${report.total_checks} controls passed, ${report.gaps_count} gaps detected)`,
    '',
  ];
  for (const item of report.checklist) {
    lines.push(
      `#### ${item.id}: ${item.title} (${item.status})`,
      `- **Category:** ${item.category} · **Criticality:** ${item.criticality}`,
      `- **Finding:** ${item.finding}`,
    );
    if (item.status === 'PASS' && item.clause_excerpt) {
      lines.push(`- **Evidence (Page ${item.page ?? 1}):** "${item.clause_excerpt}"`);
    } else if (item.status === 'GAP') {
      lines.push(
        `- **Action Required:** ${item.action_plan}`,
        `- **Standard Remediation Clause:** ${item.remediation_clause}`,
      );
    }
    lines.push('');
  }
  return lines.join('\n');
}

export function ComplianceDialog({ open, documents, currentDoc, onClose, onOpenSource }: Props) {
  const [selectedDocId, setSelectedDocId] = useState(currentDoc?.doc_id || documents[0]?.doc_id || '');
  const [tab, setTab] = useState<'compliance' | 'discrepancies'>('compliance');
  const [framework, setFramework] = useState<string>('sla');
  const [filter, setFilter] = useState<'all' | 'gap' | 'pass'>('all');
  const [auditCache, setAuditCache] = useState<Record<string, ComplianceAuditReport>>({});
  const [discrepancyCache, setDiscrepancyCache] = useState<Record<string, DiscrepancyReport>>({});
  const [useLlmDiscrepancy, setUseLlmDiscrepancy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState('');

  // Custom checks state
  const [customChecks, setCustomChecks] = useState<CustomCheckDraft[]>(DEFAULT_CUSTOM_CHECKS);
  const [newTitle, setNewTitle] = useState('');
  const [newQuery, setNewQuery] = useState('');
  const [newTerms, setNewTerms] = useState('');
  const [newCriticality, setNewCriticality] = useState<'CRITICAL' | 'HIGH' | 'MEDIUM'>('HIGH');
  const [newClause, setNewClause] = useState('');

  const activeDoc = documents.find(d => d.doc_id === selectedDocId) || currentDoc || documents[0];
  const docId = activeDoc?.doc_id || '';
  const auditKey = `${docId}:${framework}`;
  const discrepancyKey = `${docId}:${useLlmDiscrepancy ? 'llm' : 'det'}`;
  const auditReport = auditCache[auditKey];
  const discrepancyReport = discrepancyCache[discrepancyKey];

  useEffect(() => {
    if (open && currentDoc?.doc_id) {
      setSelectedDocId(currentDoc.doc_id);
    } else if (open && !selectedDocId && documents[0]?.doc_id) {
      setSelectedDocId(documents[0].doc_id);
    }
  }, [open, currentDoc?.doc_id, documents]);

  const runCompliance = async (force = false) => {
    if (!docId) return;
    if (!force && auditCache[auditKey] && framework !== 'custom') return;
    if (framework === 'custom' && !customChecks.length) {
      setError('Add at least one custom check rule before running the audit.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      let response: Response;
      if (framework === 'custom') {
        response = await request('/compliance-audit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            doc_id: docId,
            framework: 'custom',
            custom_checks: customChecks,
          }),
        });
      } else {
        response = await request(
          `/compliance-audit?doc_id=${encodeURIComponent(docId)}&framework=${encodeURIComponent(framework)}`
        );
      }
      const data = (await response.json()) as ComplianceAuditReport;
      setAuditCache(prev => ({ ...prev, [auditKey]: data }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const runDiscrepancies = async (force = false) => {
    if (!docId) return;
    if (!force && discrepancyCache[discrepancyKey]) return;
    setLoading(true);
    setError('');
    try {
      const response = await request(
        `/api/discrepancies?doc_id=${encodeURIComponent(docId)}&use_llm=${useLlmDiscrepancy ? 'true' : 'false'}`
      );
      const data = (await response.json()) as DiscrepancyReport;
      setDiscrepancyCache(prev => ({ ...prev, [discrepancyKey]: data }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!open || !docId) return;
    setError('');
    if (tab === 'compliance' && framework !== 'custom' && !auditCache[auditKey]) {
      void runCompliance(false);
    } else if (tab === 'discrepancies' && !discrepancyCache[discrepancyKey]) {
      void runDiscrepancies(false);
    }
  }, [open, docId, tab, framework, useLlmDiscrepancy]);

  const copyClause = async (id: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(id);
      setTimeout(() => setCopiedId(prev => (prev === id ? null : prev)), 2000);
    } catch {
      setError('Could not copy to clipboard.');
    }
  };

  const exportAudit = async (format: string) => {
    if (!auditReport || exporting) return;
    setExporting(true);
    setExportError('');
    try {
      const sources = auditReport.checklist
        .filter(item => item.status === 'PASS' && item.page)
        .map((item, idx) => ({
          citation_id: idx + 1,
          filename: auditReport.filename,
          page: item.page || 1,
          parent_text: item.full_clause || item.clause_excerpt,
        }));
      const response = await request('/export-report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: `Compliance Audit: ${auditReport.framework_name} (${auditReport.filename})`,
          answer: formatAuditMarkdown(auditReport),
          sources,
          classification: auditReport.classification || {},
          evaluation: {
            status: auditReport.gaps_count === 0 ? 'SYNTHESIZE' : 'REVIEW',
            retrieval_score: auditReport.overall_score / 100,
          },
          format,
        }),
      });
      const url = URL.createObjectURL(await response.blob());
      const a = document.createElement('a');
      a.href = url;
      a.download = `ragit-compliance-${auditReport.framework}.${format === 'markdown' ? 'md' : format}`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setExportError((e as Error).message);
    } finally {
      setExporting(false);
    }
  };

  const openControlSource = (item: ComplianceControlResult) => {
    if (!auditReport) return;
    onOpenSource({
      citation_id: item.citation_id || 1,
      filename: auditReport.filename,
      page: item.page || 1,
      parent_text: item.full_clause || item.clause_excerpt,
      doc_id: auditReport.doc_id,
      image_url: item.image_url || undefined,
      caption: `${item.id}: ${item.title}`,
      evidence_origin: 'extracted',
    });
  };

  const openDiscrepancySource = (finding: DiscrepancyFinding, index: number) => {
    if (!discrepancyReport) return;
    onOpenSource({
      citation_id: index + 1,
      filename: discrepancyReport.filename,
      page: finding.page || 1,
      parent_text: `Prose claim:\n${finding.text_claim}\n\nLinked visual/table fact:\n${finding.visual_fact}\n\nVariance:\n${finding.discrepancy_delta}`,
      doc_id: discrepancyReport.doc_id,
      image_url: finding.image_url || undefined,
      caption: finding.title,
      evidence_origin: 'extracted',
    });
  };

  const addCustomRule = (event: React.FormEvent) => {
    event.preventDefault();
    if (!newTitle.trim() || !newQuery.trim()) return;
    const nextId = `CUST-0${customChecks.length + 1}`;
    const terms = newTerms
      .split(',')
      .map(t => t.trim().toLowerCase())
      .filter(Boolean);
    setCustomChecks(prev => [
      ...prev,
      {
        id: nextId,
        title: newTitle.trim(),
        query: newQuery.trim(),
        category: 'Custom Control',
        criticality: newCriticality,
        required_terms: terms,
        standard_clause: newClause.trim() || undefined,
        action_required: `Ensure ${newTitle.trim()} requirement is explicitly addressed in the agreement.`,
      },
    ]);
    setNewTitle('');
    setNewQuery('');
    setNewTerms('');
    setNewClause('');
  };

  const filteredControls = (auditReport?.checklist || []).filter(item => {
    if (filter === 'gap') return item.status === 'GAP';
    if (filter === 'pass') return item.status === 'PASS';
    return true;
  });

  return (
    <Dialog.Root open={open} onOpenChange={value => { if (!value) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="overlay" />
        <Dialog.Content className="audit-dialog">
          <div className="drawer-heading">
            <span className="logo">
              <ShieldCheck size={18} />
            </span>
            <Dialog.Title>Compliance & discrepancy audit</Dialog.Title>
            <Dialog.Close className="icon-button" aria-label="Close compliance audit">
              <X size={19} />
            </Dialog.Close>
          </div>
          <Dialog.Description className="muted text-sm text-pretty">
            Verify document clauses against regulatory frameworks and scan for contradictions between prose and tables.
          </Dialog.Description>

          {!documents.length ? (
            <div className="library-empty">
              <Scale size={32} />
              <h3>No documents loaded</h3>
              <p>Attach a PDF, TXT, or Markdown file in the conversation first to run compliance and discrepancy checks.</p>
              <button className="primary" onClick={onClose}>
                Return to conversation
              </button>
            </div>
          ) : (
            <>
              <div className="audit-toolbar">
                <label className="audit-doc-select">
                  <FileText size={15} />
                  <span className="sr-only">Document to audit</span>
                  <select
                    aria-label="Document to audit"
                    value={docId}
                    onChange={e => {
                      setSelectedDocId(e.target.value);
                      setFilter('all');
                    }}
                  >
                    {documents.map(doc => (
                      <option key={doc.doc_id} value={doc.doc_id}>
                        {doc.filename}
                      </option>
                    ))}
                  </select>
                </label>

                <div className="audit-tabs" role="tablist" aria-label="Audit mode">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={tab === 'compliance'}
                    className={cn('audit-tab', tab === 'compliance' && 'selected')}
                    onClick={() => setTab('compliance')}
                  >
                    <ShieldCheck size={15} />
                    <span>Compliance controls</span>
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={tab === 'discrepancies'}
                    className={cn('audit-tab', tab === 'discrepancies' && 'selected')}
                    onClick={() => setTab('discrepancies')}
                  >
                    <AlertTriangle size={15} />
                    <span>Cross-modal discrepancies</span>
                  </button>
                </div>
              </div>

              {error && (
                <div className="document-error my-3 flex items-center justify-between gap-3 rounded-xl border p-3" role="alert">
                  <span>{error}</span>
                  <button
                    type="button"
                    className="secondary shrink-0"
                    onClick={() => (tab === 'compliance' ? runCompliance(true) : runDiscrepancies(true))}
                  >
                    Retry
                  </button>
                </div>
              )}

              {tab === 'compliance' ? (
                <div className="audit-body">
                  <div className="framework-grid" role="radiogroup" aria-label="Compliance framework">
                    {FRAMEWORKS.map(fw => (
                      <button
                        key={fw.id}
                        type="button"
                        role="radio"
                        aria-checked={framework === fw.id}
                        className={cn('framework-card', framework === fw.id && 'selected')}
                        onClick={() => {
                          setFramework(fw.id);
                          setFilter('all');
                        }}
                      >
                        <strong>{fw.label}</strong>
                        <span>{fw.summary}</span>
                      </button>
                    ))}
                  </div>

                  {framework === 'custom' && (
                    <section className="custom-rules-box" aria-label="Custom compliance rules">
                      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                        <div>
                          <h3 className="text-sm font-semibold">Custom checklist rules ({customChecks.length})</h3>
                          <p className="muted text-xs">Each rule retrieves relevant clauses and verifies required control terms.</p>
                        </div>
                        <button
                          type="button"
                          className="primary flex items-center gap-1.5 text-xs"
                          disabled={loading || !customChecks.length}
                          onClick={() => runCompliance(true)}
                        >
                          <Sparkles size={14} />
                          <span>{loading ? 'Running custom audit…' : 'Run custom audit'}</span>
                        </button>
                      </div>

                      <div className="custom-rule-list">
                        {customChecks.map(rule => (
                          <div key={rule.id} className="custom-rule-item">
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2">
                                <span className="audit-badge-neutral">{rule.id}</span>
                                <strong className="text-xs font-semibold">{rule.title}</strong>
                                <span className="muted text-xs">({rule.criticality})</span>
                              </div>
                              <p className="muted text-xs mt-1 truncate">{rule.query}</p>
                            </div>
                            <IconButton
                              label={`Remove ${rule.title}`}
                              onClick={() => setCustomChecks(prev => prev.filter(c => c.id !== rule.id))}
                            >
                              <Trash2 size={14} />
                            </IconButton>
                          </div>
                        ))}
                      </div>

                      <form className="custom-rule-form" onSubmit={addCustomRule}>
                        <input
                          className="text-field"
                          placeholder="Control title (e.g., Data Encryption at Rest)"
                          aria-label="Custom control title"
                          value={newTitle}
                          onChange={e => setNewTitle(e.target.value)}
                        />
                        <input
                          className="text-field"
                          placeholder="Audit question (e.g., How is customer data encrypted at rest?)"
                          aria-label="Custom control question"
                          value={newQuery}
                          onChange={e => setNewQuery(e.target.value)}
                        />
                        <div className="grid grid-cols-3 gap-2">
                          <input
                            className="text-field col-span-2"
                            placeholder="Required terms, comma-separated (e.g., aes-256, encryption)"
                            aria-label="Required control terms"
                            value={newTerms}
                            onChange={e => setNewTerms(e.target.value)}
                          />
                          <select
                            className="text-field"
                            aria-label="Custom control criticality"
                            value={newCriticality}
                            onChange={e => setNewCriticality(e.target.value as 'CRITICAL' | 'HIGH' | 'MEDIUM')}
                          >
                            <option value="CRITICAL">CRITICAL</option>
                            <option value="HIGH">HIGH</option>
                            <option value="MEDIUM">MEDIUM</option>
                          </select>
                        </div>
                        <div className="flex gap-2">
                          <input
                            className="text-field flex-1"
                            placeholder="Optional standard remediation clause"
                            aria-label="Standard remediation clause"
                            value={newClause}
                            onChange={e => setNewClause(e.target.value)}
                          />
                          <button
                            type="submit"
                            className="secondary flex items-center gap-1 shrink-0"
                            disabled={!newTitle.trim() || !newQuery.trim()}
                          >
                            <Plus size={15} /> Add rule
                          </button>
                        </div>
                      </form>
                    </section>
                  )}

                  {loading && (
                    <div className="library-loading my-4" role="status">
                      <p className="muted text-sm mb-2">Running compliance checks against {activeDoc?.filename}…</p>
                      {[0, 1, 2].map(i => (
                        <div key={i} className="skeleton-row" />
                      ))}
                    </div>
                  )}

                  {!loading && auditReport && (
                    <>
                      <div className="audit-scorecard" aria-label="Compliance scorecard">
                        <div className="audit-score-main">
                          <span className="audit-score-number tabular-nums">{auditReport.overall_score}%</span>
                          <div>
                            <span
                              className={cn(
                                'audit-verdict-pill',
                                auditReport.verdict_color === 'emerald'
                                  ? 'pass'
                                  : auditReport.verdict_color === 'amber'
                                  ? 'warn'
                                  : 'fail'
                              )}
                            >
                              {auditReport.verdict}
                            </span>
                            <p className="muted text-xs mt-1">
                              {auditReport.framework_name} · {auditReport.passed_count} of {auditReport.total_checks} controls verified
                            </p>
                          </div>
                        </div>

                        <div className="audit-score-actions">
                          <div className="flex gap-1" role="group" aria-label="Filter controls">
                            <button
                              type="button"
                              className={cn('view-option', filter === 'all' && 'selected')}
                              aria-pressed={filter === 'all'}
                              onClick={() => setFilter('all')}
                            >
                              All ({auditReport.total_checks})
                            </button>
                            <button
                              type="button"
                              className={cn('view-option', filter === 'gap' && 'selected')}
                              aria-pressed={filter === 'gap'}
                              onClick={() => setFilter('gap')}
                            >
                              Gaps ({auditReport.gaps_count})
                            </button>
                            <button
                              type="button"
                              className={cn('view-option', filter === 'pass' && 'selected')}
                              aria-pressed={filter === 'pass'}
                              onClick={() => setFilter('pass')}
                            >
                              Passed ({auditReport.passed_count})
                            </button>
                          </div>

                          <div className="flex items-center gap-1">
                            <IconButton label="Re-run compliance audit" disabled={loading} onClick={() => runCompliance(true)}>
                              <RefreshCw size={16} />
                            </IconButton>
                            <Dropdown.Root>
                              <Dropdown.Trigger className="secondary flex items-center gap-1.5 text-xs py-1.5 px-2.5" disabled={exporting} aria-label="Export audit report">
                                <Download size={14} />
                                <span>{exporting ? 'Exporting…' : 'Export'}</span>
                              </Dropdown.Trigger>
                              <Dropdown.Portal>
                                <Dropdown.Content className="menu" align="end" sideOffset={5}>
                                  {(['pdf', 'docx', 'csv', 'json', 'markdown'] as const).map(fmt => (
                                    <Dropdown.Item key={fmt} className="menu-item" onSelect={() => exportAudit(fmt)}>
                                      {fmt.toUpperCase()}
                                    </Dropdown.Item>
                                  ))}
                                </Dropdown.Content>
                              </Dropdown.Portal>
                            </Dropdown.Root>
                          </div>
                        </div>
                      </div>

                      {exportError && (
                        <p className="export-error" role="alert">
                          {exportError}
                        </p>
                      )}

                      <div className="audit-checklist" aria-label="Compliance controls list">
                        {filteredControls.map(item => (
                          <article
                            key={item.id}
                            className={cn('audit-control-card', item.status === 'GAP' ? 'gap' : 'pass')}
                          >
                            <div className="audit-control-header">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="audit-badge-neutral">{item.id}</span>
                                <span className="audit-crit-tag">{item.criticality}</span>
                                <span className="muted text-xs">{item.category}</span>
                              </div>
                              <span className={cn('audit-status-pill', item.status === 'PASS' ? 'pass' : 'fail')}>
                                {item.status === 'PASS' ? (
                                  <>
                                    <CheckCircle2 size={13} /> PASS
                                  </>
                                ) : (
                                  <>
                                    <ShieldAlert size={13} /> GAP DETECTED
                                  </>
                                )}
                              </span>
                            </div>

                            <h4 className="text-sm font-semibold mt-2">{item.title}</h4>
                            <p className="muted text-xs mt-1">{item.finding}</p>

                            {item.status === 'PASS' ? (
                              <div className="audit-evidence-box">
                                <p className="text-xs italic">“{item.clause_excerpt}”</p>
                                <div className="flex flex-wrap items-center justify-between gap-2 mt-2">
                                  <span className="muted text-xs tabular-nums">
                                    Page {item.page ?? 1} · Matched: {item.matched_terms.join(', ') || 'verified'}
                                  </span>
                                  <button
                                    type="button"
                                    className="evidence-link"
                                    onClick={() => openControlSource(item)}
                                  >
                                    <BookOpen size={13} /> View source evidence
                                  </button>
                                </div>
                              </div>
                            ) : (
                              <div className="audit-remediation-box">
                                <p className="text-xs">
                                  <strong>Action required:</strong> {item.action_plan}
                                </p>
                                <p className="muted text-xs mt-1">
                                  <strong>Rationale:</strong> {item.rationale}
                                </p>
                                <div className="audit-clause-snippet">
                                  <div className="flex items-center justify-between gap-2 mb-1">
                                    <span className="text-xs font-medium">Recommended standard clause</span>
                                    <button
                                      type="button"
                                      className="evidence-link"
                                      aria-label={`Copy remediation clause for ${item.id}`}
                                      onClick={() => copyClause(item.id, item.remediation_clause)}
                                    >
                                      {copiedId === item.id ? <Check size={13} /> : <Copy size={13} />}
                                      <span>{copiedId === item.id ? 'Copied' : 'Copy clause'}</span>
                                    </button>
                                  </div>
                                  <p className="text-xs">{item.remediation_clause}</p>
                                </div>
                              </div>
                            )}
                          </article>
                        ))}
                        {!filteredControls.length && (
                          <p className="muted text-center py-6 text-sm">No controls match the selected filter.</p>
                        )}
                      </div>
                    </>
                  )}
                </div>
              ) : (
                <div className="audit-body">
                  <div className="audit-discrepancy-controls">
                    <label className="flex items-center gap-2 text-xs cursor-pointer">
                      <input
                        type="checkbox"
                        checked={useLlmDiscrepancy}
                        onChange={e => setUseLlmDiscrepancy(e.target.checked)}
                      />
                      <span>Include AI cross-modal semantic check (compares prose claims with tables & charts)</span>
                    </label>
                    <button
                      type="button"
                      className="secondary flex items-center gap-1.5 text-xs py-1.5 px-3"
                      disabled={loading}
                      onClick={() => runDiscrepancies(true)}
                    >
                      <RefreshCw size={14} />
                      <span>{loading ? 'Scanning…' : 'Re-scan document'}</span>
                    </button>
                  </div>

                  {loading && (
                    <div className="library-loading my-4" role="status">
                      <p className="muted text-sm mb-2">Scanning text-to-visual links in {activeDoc?.filename}…</p>
                      {[0, 1].map(i => (
                        <div key={i} className="skeleton-row" />
                      ))}
                    </div>
                  )}

                  {!loading && discrepancyReport && (
                    <>
                      <div className="audit-scorecard" aria-label="Discrepancy scorecard">
                        <div className="audit-score-main">
                          <span className="audit-score-number tabular-nums">{discrepancyReport.consistency_score}%</span>
                          <div>
                            <span
                              className={cn(
                                'audit-verdict-pill',
                                discrepancyReport.verdict === 'CONSISTENT'
                                  ? 'pass'
                                  : discrepancyReport.verdict === 'CAUTION'
                                  ? 'warn'
                                  : 'fail'
                              )}
                            >
                              {discrepancyReport.verdict === 'FLAGGED'
                                ? `${discrepancyReport.contradictions_count} CONTRADICTIONS FLAGGED`
                                : discrepancyReport.verdict === 'CAUTION'
                                ? 'REVIEW RECOMMENDED'
                                : 'CROSS-MODAL CONSISTENT'}
                            </span>
                            <p className="muted text-xs mt-1">
                              {discrepancyReport.total_pairs_audited} prose-to-visual links audited ·{' '}
                              {discrepancyReport.aligned_count} aligned · {discrepancyReport.contradictions_count} contradictions
                            </p>
                          </div>
                        </div>
                      </div>

                      {!discrepancyReport.findings.length ? (
                        <div className="library-empty compact">
                          <CheckCircle2 size={28} />
                          <h3>No cross-modal discrepancies detected</h3>
                          <p>
                            No conflicting numerical claims or table breaches were found across the document’s linked text and visual nodes.
                          </p>
                        </div>
                      ) : (
                        <div className="audit-checklist" aria-label="Discrepancy findings list">
                          {discrepancyReport.findings.map((finding, idx) => (
                            <article
                              key={`${finding.paragraph_id}:${finding.visual_id}:${idx}`}
                              className={cn(
                                'audit-control-card',
                                finding.status === 'CONTRADICTION' ? 'gap' : 'pass'
                              )}
                            >
                              <div className="audit-control-header">
                                <div className="flex items-center gap-2">
                                  <span className="audit-badge-neutral">Page {finding.page}</span>
                                  <strong className="text-sm">{finding.title}</strong>
                                </div>
                                <span
                                  className={cn(
                                    'audit-status-pill',
                                    finding.status === 'CONTRADICTION'
                                      ? 'fail'
                                      : finding.status === 'CAUTION'
                                      ? 'warn'
                                      : 'pass'
                                  )}
                                >
                                  {finding.status}
                                </span>
                              </div>

                              <div className="discrepancy-comparison">
                                <div className="discrepancy-col">
                                  <span className="text-xs font-semibold muted">Prose claim</span>
                                  <p className="text-xs mt-1">{finding.text_claim}</p>
                                </div>
                                <div className="discrepancy-col">
                                  <span className="text-xs font-semibold muted">Visual / table data</span>
                                  <p className="text-xs mt-1">{finding.visual_fact}</p>
                                </div>
                              </div>

                              <div className="flex flex-wrap items-center justify-between gap-2 mt-3 pt-2 border-t border-[var(--line)]">
                                <p className="text-xs font-medium">{finding.discrepancy_delta}</p>
                                <button
                                  type="button"
                                  className="evidence-link"
                                  onClick={() => openDiscrepancySource(finding, idx)}
                                >
                                  <BookOpen size={13} /> Inspect visual evidence
                                </button>
                              </div>
                            </article>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
            </>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
