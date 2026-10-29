import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { Check, ChevronLeft, ChevronRight, FileText, Search, Trash2, X } from 'lucide-react';
import type { Document } from '../types';
import { EvidenceImage } from './EvidenceImage';
import { cn, IconButton } from './ui';

type Props = {
  documents: Document[];
  currentId?: string;
  loading: boolean;
  error: string;
  busy: boolean;
  onRetry: () => void;
  onSelect: (doc: Document) => void;
  onDelete?: (doc: Document) => Promise<void>;
  onClose: () => void;
};

export function DocumentLibrary({ documents, currentId, loading, error, busy, onRetry, onSelect, onDelete, onClose }: Props) {
  const [filter, setFilter] = useState('');
  const [selectedId, setSelectedId] = useState(currentId || documents[0]?.doc_id);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const filtered = documents.filter(doc => doc.filename.toLowerCase().includes(filter.toLowerCase()));
  const selected = documents.find(doc => doc.doc_id === selectedId) || filtered[0] || documents[0];
  return <Dialog.Portal>
    <Dialog.Overlay className="overlay"/><Dialog.Content className="library-dialog">
      <div className="drawer-heading"><span className="logo"><FileText size={18}/></span><Dialog.Title>Document library</Dialog.Title><Dialog.Close className="icon-button" aria-label="Close document library"><X size={19}/></Dialog.Close></div>
      <Dialog.Description className="muted text-sm text-pretty">Browse your files, inspect a page, and choose what to discuss.</Dialog.Description>
      <label className="library-search"><Search size={17}/><input aria-label="Search documents" placeholder="Search by filename" value={filter} onChange={event => setFilter(event.target.value)}/></label>
      {error && <div className="document-error" role="alert"><p>{error}</p><button className="secondary mt-2" onClick={onRetry}>Retry library</button></div>}
      {loading && !documents.length && <div className="library-loading" role="status"><span className="sr-only">Loading documents</span>{[0,1,2].map(i => <div key={i} className="skeleton-row"/>)}</div>}
      {!loading && !error && !documents.length && <div className="library-empty"><FileText size={32}/><h3>No documents yet</h3><p>Attach a PDF, TXT, or Markdown file in the conversation to add it here.</p><button className="primary" onClick={onClose}>Return to conversation</button></div>}
      {!!documents.length && <div className="library-body">
        <div className="library-list" aria-label="Documents">
          <p className="muted text-xs tabular-nums">{filtered.length} of {documents.length} documents</p>
          {filtered.map(doc => <button key={doc.doc_id} className={cn('library-document', selected?.doc_id === doc.doc_id && 'selected')} aria-pressed={selected?.doc_id === doc.doc_id} onClick={() => { setSelectedId(doc.doc_id); setPage(1); }}>
            <FileText size={18}/><span><strong>{doc.filename}</strong><small>{doc.pages ? `${doc.pages} ${doc.pages === 1 ? 'page' : 'pages'}` : 'Ready for questions'}</small></span>{currentId === doc.doc_id && <Check size={15} aria-label="Current document"/>}
          </button>)}
          {!filtered.length && <div className="library-empty compact"><p>No documents match “{filter}”.</p><button className="secondary" onClick={() => setFilter('')}>Clear search</button></div>}
        </div>
        <section className="library-detail" aria-label="Document details">
          {selected ? <>
            <h3>{selected.filename}</h3>
            {selected.classification?.label && <p className="muted text-sm">{selected.classification.label}</p>}
            <div className="document-facts"><span>Text ready for questions</span>{selected.visual_analysis?.status === 'ready' && !!selected.visual_analysis.total && <span>{selected.visual_analysis.completed} visuals searchable</span>}{selected.visual_analysis?.status === 'analyzing' && <span>Analyzing visuals</span>}</div>
            {selected.cache_warning && <p className="muted text-sm">This document is available now, but could not be saved for reuse.</p>}
            {/\.pdf$/i.test(selected.filename) ? <>
              <div className="page-controls" aria-label="Page navigation">
                <IconButton label="Previous PDF page" disabled={page <= 1} onClick={() => setPage(p => p - 1)}><ChevronLeft size={18}/></IconButton>
                <label>Page <select aria-label="PDF page" value={page} onChange={event => setPage(Number(event.target.value))}>{Array.from({ length: selected.pages || 1 }, (_, i) => <option key={i + 1}>{i + 1}</option>)}</select> <span className="muted tabular-nums">of {selected.pages || 1}</span></label>
                <IconButton label="Next PDF page" disabled={page >= (selected.pages || 1)} onClick={() => setPage(p => p + 1)}><ChevronRight size={18}/></IconButton>
              </div>
              <EvidenceImage key={`${selected.doc_id}:${page}`} url={`/api/preview/${encodeURIComponent(selected.doc_id)}/${page}`} label={`${selected.filename}, page ${page}`}/>
            </> : <div className="text-document-preview"><FileText size={32}/><p>Text document</p><span>Ask a question to explore its contents and cited passages.</span></div>}
            <div className="flex gap-2 mt-4">
              <button className="primary flex-1" disabled={busy || deletingId === selected.doc_id} onClick={() => onSelect(selected)}>{selected.doc_id === currentId ? 'Return to conversation' : 'Ask about this document'}</button>
              {onDelete && <button className="danger flex items-center justify-center gap-1.5 px-3" disabled={busy || deletingId === selected.doc_id} aria-label="Delete document" onClick={async () => {
                if (!window.confirm(`Delete "${selected.filename}" from your vault? This removes cached pages, preview images, and vector indices.`)) return;
                setDeletingId(selected.doc_id);
                try {
                  await onDelete(selected);
                } finally {
                  setDeletingId(null);
                }
              }}><Trash2 size={16}/><span>{deletingId === selected.doc_id ? 'Deleting...' : 'Delete'}</span></button>}
            </div>
          </> : <p className="muted">Select a document to see its details.</p>}
        </section>
      </div>}
    </Dialog.Content>
  </Dialog.Portal>;
}
