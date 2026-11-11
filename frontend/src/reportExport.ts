import { useCallback, useState } from 'react';
import { request, type ComplianceAuditReport } from './types';

export function triggerBlobDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function downloadTextFile(
  content: string,
  filename: string,
  mimeType = 'text/markdown;charset=utf-8'
) {
  const blob = new Blob([content], { type: mimeType });
  triggerBlobDownload(blob, filename);
}

export function formatAuditMarkdown(report: ComplianceAuditReport): string {
  const lines = [
    `### ${report.framework_name}`,
    `**Verdict:** ${report.verdict} — **Overall Score:** ${report.overall_score}% (${report.passed_count}/${report.total_checks} controls passed, ${report.gaps_count} gaps detected)`,
    '',
  ];
  for (const item of report.checklist) {
    lines.push(
      `#### ${item.id}: ${item.title} (${item.status})`,
      `- **Category:** ${item.category} · **Criticality:** ${item.criticality}`,
      `- **Finding:** ${item.finding}`
    );
    if (item.status === 'PASS' && item.clause_excerpt) {
      lines.push(`- **Evidence (Page ${item.page ?? 1}):** "${item.clause_excerpt}"`);
    } else if (item.status === 'GAP') {
      lines.push(
        `- **Action Required:** ${item.action_plan}`,
        `- **Standard Remediation Clause:** ${item.remediation_clause}`
      );
    }
    lines.push('');
  }
  return lines.join('\n');
}

export function buildComplianceExportPayload(report: ComplianceAuditReport, format: string) {
  const sources = report.checklist
    .filter(item => item.status === 'PASS' && item.page)
    .map((item, idx) => ({
      citation_id: idx + 1,
      filename: report.filename,
      page: item.page || 1,
      parent_text: item.full_clause || item.clause_excerpt,
    }));

  return {
    query: `Compliance Audit: ${report.framework_name} (${report.filename})`,
    answer: formatAuditMarkdown(report),
    sources,
    classification: report.classification || {},
    evaluation: {
      status: report.gaps_count === 0 ? 'SYNTHESIZE' : 'REVIEW',
      retrieval_score: report.overall_score / 100,
    },
    format,
  };
}

export function useReportExport() {
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState('');

  const clearExportError = useCallback(() => setExportError(''), []);

  const exportReport = useCallback(
    async (payload: Record<string, unknown>, filename: string) => {
      if (exporting) return;
      setExporting(true);
      setExportError('');
      try {
        const response = await request('/export-report', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const blob = await response.blob();
        triggerBlobDownload(blob, filename);
      } catch (e) {
        setExportError((e as Error).message);
      } finally {
        setExporting(false);
      }
    },
    [exporting]
  );

  return {
    exporting,
    exportError,
    clearExportError,
    exportReport,
  };
}
