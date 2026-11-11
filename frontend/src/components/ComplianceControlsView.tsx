import { useState } from 'react';
import * as Dropdown from '@radix-ui/react-dropdown-menu';
import { BookOpen, Check, CheckCircle2, Copy, Download, RefreshCw, ShieldAlert } from 'lucide-react';
import type { ComplianceAuditReport, ComplianceControlResult, CustomCheckDraft, Source } from '../types';
import { buildComplianceExportPayload, useReportExport } from '../reportExport';
import { FRAMEWORKS, FRAMEWORK_IDS, type ControlFilter } from '../useComplianceAudit';
import { CustomRulesBuilder } from './CustomRulesBuilder';
import { cn, handleRovingKeyDown, IconButton } from './ui';

type Props = {
  activeFilename?: string;
  framework: string;
  onSelectFramework: (fw: string) => void;
  filter: ControlFilter;
  onSelectFilter: (f: ControlFilter) => void;
  loading: boolean;
  auditReport?: ComplianceAuditReport;
  filteredControls: ComplianceControlResult[];
  customChecks: CustomCheckDraft[];
  onAddCustomRule: (draft: Omit<CustomCheckDraft, 'id'>) => void;
  onRemoveCustomRule: (id: string) => void;
  onRunCompliance: (force?: boolean) => void;
  onOpenSource: (source: Source) => void;
  onCopyError: (msg: string) => void;
};

export function ComplianceControlsView({
  activeFilename, framework, onSelectFramework, filter, onSelectFilter, loading,
  auditReport, filteredControls, customChecks, onAddCustomRule, onRemoveCustomRule,
  onRunCompliance, onOpenSource, onCopyError,
}: Props) {
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const { exporting, exportError, exportReport } = useReportExport();

  const copyClause = async (id: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(id);
      setTimeout(() => setCopiedId(prev => (prev === id ? null : prev)), 2000);
    } catch {
      onCopyError('Could not copy to clipboard.');
    }
  };

  const handleExport = (format: string) => {
    if (!auditReport) return;
    const ext = format === 'markdown' ? 'md' : format;
    void exportReport(buildComplianceExportPayload(auditReport, format), `ragit-compliance-${auditReport.framework}.${ext}`);
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

  return (
    <div className="audit-body">
      <div
        className="framework-grid"
        role="radiogroup"
        aria-label="Compliance framework"
        onKeyDown={e => handleRovingKeyDown(e, FRAMEWORK_IDS, framework as typeof FRAMEWORK_IDS[number], onSelectFramework)}
      >
        {FRAMEWORKS.map(fw => {
          const selected = framework === fw.id;
          return (
            <button key={fw.id} type="button" role="radio" aria-checked={selected} tabIndex={selected ? 0 : -1}
              className={cn('framework-card', selected && 'selected')} onClick={() => onSelectFramework(fw.id)}>
              <strong>{fw.label}</strong>
              <span>{fw.summary}</span>
            </button>
          );
        })}
      </div>

      {framework === 'custom' && (
        <CustomRulesBuilder customChecks={customChecks} loading={loading}
          onRunAudit={() => onRunCompliance(true)} onAddRule={onAddCustomRule} onRemoveRule={onRemoveCustomRule} />
      )}

      {loading && (
        <div className="library-loading my-4" role="status">
          <p className="muted text-sm mb-2">Running compliance checks against {activeFilename}…</p>
          {[0, 1, 2].map(i => <div key={i} className="skeleton-row" />)}
        </div>
      )}

      {!loading && auditReport && (
        <>
          <div className="audit-scorecard" aria-label="Compliance scorecard">
            <div className="audit-score-main">
              <span className="audit-score-number tabular-nums">{auditReport.overall_score}%</span>
              <div>
                <span className={cn('audit-verdict-pill', auditReport.verdict_color === 'emerald' ? 'pass' : auditReport.verdict_color === 'amber' ? 'warn' : 'fail')}>
                  {auditReport.verdict}
                </span>
                <p className="muted text-xs mt-1">
                  {auditReport.framework_name} · {auditReport.passed_count} of {auditReport.total_checks} controls verified
                </p>
              </div>
            </div>

            <div className="audit-score-actions">
              <div className="flex gap-1" role="group" aria-label="Filter controls">
                <button type="button" className={cn('view-option', filter === 'all' && 'selected')} aria-pressed={filter === 'all'} onClick={() => onSelectFilter('all')}>
                  All ({auditReport.total_checks})
                </button>
                <button type="button" className={cn('view-option', filter === 'gap' && 'selected')} aria-pressed={filter === 'gap'} onClick={() => onSelectFilter('gap')}>
                  Gaps ({auditReport.gaps_count})
                </button>
                <button type="button" className={cn('view-option', filter === 'pass' && 'selected')} aria-pressed={filter === 'pass'} onClick={() => onSelectFilter('pass')}>
                  Passed ({auditReport.passed_count})
                </button>
              </div>

              <div className="flex items-center gap-1">
                <IconButton label="Re-run compliance audit" disabled={loading} onClick={() => onRunCompliance(true)}>
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
                        <Dropdown.Item key={fmt} className="menu-item" onSelect={() => handleExport(fmt)}>
                          {fmt.toUpperCase()}
                        </Dropdown.Item>
                      ))}
                    </Dropdown.Content>
                  </Dropdown.Portal>
                </Dropdown.Root>
              </div>
            </div>
          </div>

          {exportError && <p className="export-error" role="alert">{exportError}</p>}

          <div className="audit-checklist" aria-label="Compliance controls list">
            {filteredControls.map(item => (
              <article key={item.id} className={cn('audit-control-card', item.status === 'GAP' ? 'gap' : 'pass')}>
                <div className="audit-control-header">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="audit-badge-neutral">{item.id}</span>
                    <span className="audit-crit-tag">{item.criticality}</span>
                    <span className="muted text-xs">{item.category}</span>
                  </div>
                  <span className={cn('audit-status-pill', item.status === 'PASS' ? 'pass' : 'fail')}>
                    {item.status === 'PASS' ? <><CheckCircle2 size={13} /> PASS</> : <><ShieldAlert size={13} /> GAP DETECTED</>}
                  </span>
                </div>
                <h4 className="text-sm font-semibold mt-2">{item.title}</h4>
                <p className="muted text-xs mt-1">{item.finding}</p>
                {item.status === 'PASS' ? (
                  <div className="audit-evidence-box">
                    <p className="text-xs italic">“{item.clause_excerpt}”</p>
                    <div className="flex flex-wrap items-center justify-between gap-2 mt-2">
                      <span className="muted text-xs tabular-nums">Page {item.page ?? 1} · Matched: {item.matched_terms.join(', ') || 'verified'}</span>
                      <button type="button" className="evidence-link" onClick={() => openControlSource(item)}>
                        <BookOpen size={13} /> View source evidence
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="audit-remediation-box">
                    <p className="text-xs"><strong>Action required:</strong> {item.action_plan}</p>
                    <p className="muted text-xs mt-1"><strong>Rationale:</strong> {item.rationale}</p>
                    <div className="audit-clause-snippet">
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <span className="text-xs font-medium">Recommended standard clause</span>
                        <button type="button" className="evidence-link" aria-label={`Copy remediation clause for ${item.id}`}
                          onClick={() => void copyClause(item.id, item.remediation_clause)}>
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
            {!filteredControls.length && <p className="muted text-center py-6 text-sm">No controls match the selected filter.</p>}
          </div>
        </>
      )}
    </div>
  );
}
