import * as Dialog from '@radix-ui/react-dialog';
import { AlertTriangle, FileText, Scale, ShieldCheck, X } from 'lucide-react';
import type { Document, Source } from '../types';
import { AUDIT_TABS, useComplianceAudit } from '../useComplianceAudit';
import { ComplianceControlsView } from './ComplianceControlsView';
import { DiscrepancyView } from './DiscrepancyView';
import { cn, handleRovingKeyDown } from './ui';

type Props = {
  open: boolean;
  documents: Document[];
  currentDoc?: Document;
  onClose: () => void;
  onOpenSource: (source: Source) => void;
};

export function ComplianceDialog({
  open,
  documents,
  currentDoc,
  onClose,
  onOpenSource,
}: Props) {
  const {
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
  } = useComplianceAudit({ open, documents, currentDoc });

  return (
    <Dialog.Root
      open={open}
      onOpenChange={value => {
        if (!value) onClose();
      }}
    >
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
              <p>
                Attach a PDF, TXT, or Markdown file in the conversation first to run compliance and discrepancy checks.
              </p>
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
                    onChange={e => selectDocument(e.target.value)}
                  >
                    {documents.map(doc => (
                      <option key={doc.doc_id} value={doc.doc_id}>
                        {doc.filename}
                      </option>
                    ))}
                  </select>
                </label>

                <div
                  className="audit-tabs"
                  role="tablist"
                  aria-label="Audit mode"
                  onKeyDown={e => handleRovingKeyDown(e, AUDIT_TABS, tab, setTab)}
                >
                  <button
                    type="button"
                    role="tab"
                    aria-selected={tab === 'compliance'}
                    tabIndex={tab === 'compliance' ? 0 : -1}
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
                    tabIndex={tab === 'discrepancies' ? 0 : -1}
                    className={cn('audit-tab', tab === 'discrepancies' && 'selected')}
                    onClick={() => setTab('discrepancies')}
                  >
                    <AlertTriangle size={15} />
                    <span>Cross-modal discrepancies</span>
                  </button>
                </div>
              </div>

              {error && (
                <div
                  className="document-error my-3 flex items-center justify-between gap-3 rounded-xl border p-3"
                  role="alert"
                >
                  <span>{error}</span>
                  <button
                    type="button"
                    className="secondary shrink-0"
                    onClick={() =>
                      void (tab === 'compliance' ? runCompliance(true) : runDiscrepancies(true))
                    }
                  >
                    Retry
                  </button>
                </div>
              )}

              {tab === 'compliance' ? (
                <ComplianceControlsView
                  activeFilename={activeDoc?.filename}
                  framework={framework}
                  onSelectFramework={selectFramework}
                  filter={filter}
                  onSelectFilter={setFilter}
                  loading={loading}
                  auditReport={auditReport}
                  filteredControls={filteredControls}
                  customChecks={customChecks}
                  onAddCustomRule={addCustomRule}
                  onRemoveCustomRule={removeCustomRule}
                  onRunCompliance={force => void runCompliance(force)}
                  onOpenSource={onOpenSource}
                  onCopyError={setError}
                />
              ) : (
                <DiscrepancyView
                  activeFilename={activeDoc?.filename}
                  loading={loading}
                  useLlmDiscrepancy={useLlmDiscrepancy}
                  onToggleLlm={setUseLlmDiscrepancy}
                  discrepancyReport={discrepancyReport}
                  onRunDiscrepancies={force => void runDiscrepancies(force)}
                  onOpenSource={onOpenSource}
                />
              )}
            </>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
