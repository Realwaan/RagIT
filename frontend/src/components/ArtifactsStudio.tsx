import { lazy, Suspense, useState, useEffect } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { Sparkles, X, FileText, Calendar, BookOpen, ShieldAlert, Headphones, RotateCcw, Copy, Check, Download, Loader2 } from 'lucide-react';
import { request, type Document, type GeneratedArtifact, type Source } from '../types';
import { downloadTextFile } from '../reportExport';
import { cn, handleRovingKeyDown } from './ui';

const LazyStandaloneMarkdown = lazy(() => import('../Markdown').then(m => ({ default: m.StandaloneMarkdown })));

const ARTIFACT_TABS = [
  { id: 'executive_briefing', title: 'Executive Briefing', icon: FileText },
  { id: 'chronological_timeline', title: 'Chronology Timeline', icon: Calendar },
  { id: 'study_guide_faq', title: 'Study Guide & FAQ', icon: BookOpen },
  { id: 'entity_risk_matrix', title: 'Entity & Risk Matrix', icon: ShieldAlert },
  { id: 'audio_podcast_script', title: 'Audio Briefing Script', icon: Headphones },
] as const;

const ARTIFACT_TAB_IDS = ARTIFACT_TABS.map(t => t.id);

export function ArtifactsStudio({ open, currentDoc, onClose, onOpenSource }: {
  open: boolean;
  currentDoc?: Document;
  onClose: () => void;
  onOpenSource: (source: Source) => void;
}) {
  const [activeTab, setActiveTab] = useState<string>('executive_briefing');
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState('');
  const [artifacts, setArtifacts] = useState<Record<string, GeneratedArtifact>>({});

  const currentArtifact = artifacts[activeTab];

  const fetchArtifact = async (typeId: string, force = false) => {
    if (!force && artifacts[typeId]) return;
    setLoading(true);
    setError('');
    try {
      const res = await request('/api/artifacts/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ doc_id: currentDoc?.doc_id, artifact_type: typeId }),
      });
      if (!res.ok) throw new Error(`Server returned HTTP ${res.status}`);
      const data: GeneratedArtifact = await res.json();
      setArtifacts(prev => ({ ...prev, [typeId]: data }));
    } catch (e) {
      setError((e as Error).message || 'Failed to generate executive artifact.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { if (open) void fetchArtifact(activeTab); }, [open, activeTab, currentDoc?.doc_id]);

  const copyToClipboard = () => {
    if (!currentArtifact) return;
    navigator.clipboard.writeText(currentArtifact.markdown).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const downloadMarkdown = () => {
    if (!currentArtifact) return;
    downloadTextFile(currentArtifact.markdown, `${currentArtifact.filename || 'document'}_${currentArtifact.artifact_type}.md`);
  };

  return (
    <Dialog.Root open={open} onOpenChange={val => { if (!val) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="overlay"/>
        <Dialog.Content className="artifacts-dialog">
          <div className="flex items-center justify-between pb-3 border-b border-line">
            <div className="flex items-center gap-2">
              <Sparkles className="text-accent" size={22}/>
              <div>
                <Dialog.Title className="text-base font-bold">Executive Artifacts Studio</Dialog.Title>
                <Dialog.Description className="text-xs muted">
                  NotebookLM-style synthesis grounded in {currentDoc?.filename || 'your document library'}
                </Dialog.Description>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <button type="button" className="secondary text-xs flex items-center gap-1.5 px-2.5 py-1.5" disabled={loading} onClick={() => void fetchArtifact(activeTab, true)} title="Regenerate this artifact">
                <RotateCcw size={14} className={cn(loading && 'animate-spin')}/>
                <span>Regenerate</span>
              </button>
              <Dialog.Close className="icon-button" aria-label="Close studio"><X size={20}/></Dialog.Close>
            </div>
          </div>

          <div className="artifacts-tabs mt-3" role="tablist" aria-label="Artifact types"
            onKeyDown={e => handleRovingKeyDown(e, ARTIFACT_TAB_IDS, activeTab, setActiveTab)}>
            {ARTIFACT_TABS.map(tab => {
              const Icon = tab.icon;
              const selected = activeTab === tab.id;
              return (
                <button key={tab.id} type="button" role="tab" aria-selected={selected} tabIndex={selected ? 0 : -1}
                  className={cn('artifacts-tab', selected && 'selected')} onClick={() => setActiveTab(tab.id)}>
                  <Icon size={15}/>
                  <span>{tab.title}</span>
                </button>
              );
            })}
          </div>

          <div className="artifacts-content">
            {loading && !currentArtifact ? (
              <div className="flex flex-col items-center justify-center h-full gap-3 text-muted">
                <Loader2 size={28} className="animate-spin text-accent"/>
                <p className="text-sm">Synthesizing executive artifact from verified document excerpts...</p>
              </div>
            ) : error ? (
              <div className="p-4 rounded-xl border border-danger/30 bg-danger/10 text-danger text-sm">
                <p className="font-semibold">Generation failed</p>
                <p>{error}</p>
                <button className="secondary mt-3 text-xs" onClick={() => void fetchArtifact(activeTab, true)}>Try again</button>
              </div>
            ) : currentArtifact ? (
              <div className="prose max-w-none">
                <Suspense fallback={<p role="status">Formatting artifact…</p>}>
                  <LazyStandaloneMarkdown content={currentArtifact.markdown} sources={currentArtifact.sources || []} onOpenSource={onOpenSource}/>
                </Suspense>
              </div>
            ) : null}
          </div>

          <div className="artifacts-footer">
            <div className="flex items-center gap-2">
              <span className="font-medium text-xs">
                Mode: {currentArtifact?.generation_mode === 'llm_grounded' ? 'LLM Grounded Synthesis' : 'Deterministic Offline Extraction'}
              </span>
              {currentArtifact?.sources && currentArtifact.sources.length > 0 && (
                <span className="muted">· {currentArtifact.sources.length} supporting citations</span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button type="button" className="secondary text-xs flex items-center gap-1.5 px-3 py-1.5" disabled={!currentArtifact || loading} onClick={copyToClipboard}>
                {copied ? <Check size={14} className="text-accent"/> : <Copy size={14}/>}
                <span>{copied ? 'Copied' : 'Copy Markdown'}</span>
              </button>
              <button type="button" className="primary text-xs flex items-center gap-1.5 px-3 py-1.5" disabled={!currentArtifact || loading} onClick={downloadMarkdown}>
                <Download size={14}/>
                <span>Download Report</span>
              </button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
