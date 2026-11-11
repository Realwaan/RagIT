import { useCallback, useEffect, useState } from 'react';
import {
  request,
  type ComplianceAuditReport,
  type CustomCheckDraft,
  type DiscrepancyReport,
  type Document,
} from './types';

export const FRAMEWORKS = [
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
    id: 'iso27001',
    label: 'ISO 27001 / SOC 2',
    summary: 'AES-256 encryption, zero-trust MFA, pen-testing & supplier governance',
  },
  {
    id: 'hipaa',
    label: 'HIPAA / BAA',
    summary: 'ePHI safeguards, minimum-necessary access, NIST encryption & breach notice',
  },
  {
    id: 'custom',
    label: 'Custom Rules',
    summary: 'Define custom contract clauses, policy rules & required terms',
  },
] as const;

export const FRAMEWORK_IDS = FRAMEWORKS.map(f => f.id);
export const AUDIT_TABS = ['compliance', 'discrepancies'] as const;
export type AuditTab = (typeof AUDIT_TABS)[number];
export type ControlFilter = 'all' | 'gap' | 'pass';

const DEFAULT_CUSTOM_CHECKS: CustomCheckDraft[] = [
  {
    id: 'CUST-01',
    title: 'Termination Notice Period',
    query: 'What prior written notice period is required to terminate the agreement for convenience?',
    category: 'Contract Governance',
    criticality: 'HIGH',
    required_terms: ['terminate', 'termination', 'notice', 'days'],
    standard_clause:
      'Either party may terminate this Agreement for convenience upon 30 business days prior written notice.',
    action_required: 'Specify a clear written notice period for termination without cause.',
  },
];

export function useComplianceAudit({
  open,
  documents,
  currentDoc,
}: {
  open: boolean;
  documents: Document[];
  currentDoc?: Document;
}) {
  const [selectedDocId, setSelectedDocId] = useState(
    currentDoc?.doc_id || documents[0]?.doc_id || ''
  );
  const [tab, setTab] = useState<AuditTab>('compliance');
  const [framework, setFramework] = useState<string>('sla');
  const [filter, setFilter] = useState<ControlFilter>('all');
  const [auditCache, setAuditCache] = useState<Record<string, ComplianceAuditReport>>({});
  const [discrepancyCache, setDiscrepancyCache] = useState<Record<string, DiscrepancyReport>>({});
  const [useLlmDiscrepancy, setUseLlmDiscrepancy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [customChecks, setCustomChecks] = useState<CustomCheckDraft[]>(DEFAULT_CUSTOM_CHECKS);

  const activeDoc =
    documents.find(d => d.doc_id === selectedDocId) || currentDoc || documents[0];
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

  const runCompliance = useCallback(
    async (force = false) => {
      if (!docId) return;
      if (!force && auditCache[auditKey] && framework !== 'custom') return;
      if (framework === 'custom' && !customChecks.length) {
        setError('Add at least one custom check rule before running the audit.');
        return;
      }
      setLoading(true);
      setError('');
      try {
        const response =
          framework === 'custom'
            ? await request('/compliance-audit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  doc_id: docId,
                  framework: 'custom',
                  custom_checks: customChecks,
                }),
              })
            : await request(
                `/compliance-audit?doc_id=${encodeURIComponent(docId)}&framework=${encodeURIComponent(framework)}`
              );
        const data = (await response.json()) as ComplianceAuditReport;
        setAuditCache(prev => ({ ...prev, [auditKey]: data }));
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    },
    [docId, auditCache, auditKey, framework, customChecks]
  );

  const runDiscrepancies = useCallback(
    async (force = false) => {
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
    },
    [docId, discrepancyCache, discrepancyKey, useLlmDiscrepancy]
  );

  useEffect(() => {
    if (!open || !docId) return;
    setError('');
    if (tab === 'compliance' && framework !== 'custom' && !auditCache[auditKey]) {
      void runCompliance(false);
    } else if (tab === 'discrepancies' && !discrepancyCache[discrepancyKey]) {
      void runDiscrepancies(false);
    }
  }, [open, docId, tab, framework, useLlmDiscrepancy]);

  const addCustomRule = useCallback((draft: Omit<CustomCheckDraft, 'id'>) => {
    setCustomChecks(prev => [
      ...prev,
      {
        ...draft,
        id: `CUST-0${prev.length + 1}`,
      },
    ]);
  }, []);

  const removeCustomRule = useCallback((id: string) => {
    setCustomChecks(prev => prev.filter(c => c.id !== id));
  }, []);

  const selectDocument = useCallback((nextDocId: string) => {
    setSelectedDocId(nextDocId);
    setFilter('all');
  }, []);

  const selectFramework = useCallback((nextFramework: string) => {
    setFramework(nextFramework);
    setFilter('all');
  }, []);

  const filteredControls = (auditReport?.checklist || []).filter(item => {
    if (filter === 'gap') return item.status === 'GAP';
    if (filter === 'pass') return item.status === 'PASS';
    return true;
  });

  return {
    activeDoc,
    docId,
    tab,
    setTab,
    framework,
    selectFramework,
    filter,
    setFilter,
    useLlmDiscrepancy,
    setUseLlmDiscrepancy,
    loading,
    error,
    setError,
    auditReport,
    discrepancyReport,
    filteredControls,
    customChecks,
    addCustomRule,
    removeCustomRule,
    selectDocument,
    runCompliance,
    runDiscrepancies,
  };
}
