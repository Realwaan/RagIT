import { BookOpen, CheckCircle2, RefreshCw } from 'lucide-react';
import type { DiscrepancyFinding, DiscrepancyReport, Source } from '../types';
import { cn } from './ui';

type Props = {
  activeFilename?: string;
  loading: boolean;
  useLlmDiscrepancy: boolean;
  onToggleLlm: (checked: boolean) => void;
  discrepancyReport?: DiscrepancyReport;
  onRunDiscrepancies: (force?: boolean) => void;
  onOpenSource: (source: Source) => void;
};

export function DiscrepancyView({
  activeFilename,
  loading,
  useLlmDiscrepancy,
  onToggleLlm,
  discrepancyReport,
  onRunDiscrepancies,
  onOpenSource,
}: Props) {
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

  return (
    <div className="audit-body">
      <div className="audit-discrepancy-controls">
        <label className="flex items-center gap-2 text-xs cursor-pointer">
          <input
            type="checkbox"
            checked={useLlmDiscrepancy}
            onChange={e => onToggleLlm(e.target.checked)}
          />
          <span>
            Include AI cross-modal semantic check (compares prose claims with tables & charts)
          </span>
        </label>
        <button
          type="button"
          className="secondary flex items-center gap-1.5 text-xs py-1.5 px-3"
          disabled={loading}
          onClick={() => onRunDiscrepancies(true)}
        >
          <RefreshCw size={14} />
          <span>{loading ? 'Scanning…' : 'Re-scan document'}</span>
        </button>
      </div>

      {loading && (
        <div className="library-loading my-4" role="status">
          <p className="muted text-sm mb-2">Scanning text-to-visual links in {activeFilename}…</p>
          {[0, 1].map(i => (
            <div key={i} className="skeleton-row" />
          ))}
        </div>
      )}

      {!loading && discrepancyReport && (
        <>
          <div className="audit-scorecard" aria-label="Discrepancy scorecard">
            <div className="audit-score-main">
              <span className="audit-score-number tabular-nums">
                {discrepancyReport.consistency_score}%
              </span>
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
                  {discrepancyReport.aligned_count} aligned ·{' '}
                  {discrepancyReport.contradictions_count} contradictions
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

                  <div className="flex flex-wrap items-center justify-between gap-2 mt-3 pt-2 border-t border-line">
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
  );
}
