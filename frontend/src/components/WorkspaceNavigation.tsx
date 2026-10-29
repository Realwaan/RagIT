import { Sparkles, Plus, Search, MessageSquare, FileText, Check, Trash2, ShieldCheck, FolderOpen } from 'lucide-react';
import type { Document, Session } from '../types';
import { cn, IconButton } from './ui';
import { RenameConversationDialog } from './RenameConversationDialog';

type Props = {
  sessions: Session[];
  active: Session;
  documents: Document[];
  busy: boolean;
  filter: string;
  setFilter: (value: string) => void;
  newChat: () => void;
  selectDoc: (doc: Document) => void;
  onSelect: (id: string) => void;
  setDeleting: (id: string) => void;
  documentsLoading: boolean;
  documentsError: string;
  onRetry: () => void;
  onRename: (id: string, title: string) => void;
  onOpenLibrary: () => void;
};

export function WorkspaceNavigation({ sessions, active, documents, busy, filter, setFilter, newChat, selectDoc, onSelect, setDeleting, documentsLoading, documentsError, onRetry, onRename, onOpenLibrary }: Props) {

  return <>
    <div className="sidebar-brand"><span className="logo"><Sparkles size={19}/></span><strong>RagIT</strong><span className="muted text-xs">Workspace</span></div>
    <button className="new-chat" onClick={newChat} disabled={busy}><Plus size={17}/> New conversation</button>
    <label className="search"><Search size={15}/><input aria-label="Search conversations" placeholder="Search conversations" value={filter} onChange={e => setFilter(e.target.value)}/></label>
    <div className="sidebar-label">CONVERSATIONS</div>
    <nav className="conversation-list" aria-label="Conversations">{sessions.filter(s => s.title.toLowerCase().includes(filter.toLowerCase())).map(s => <div key={s.id} className={cn('conversation-row', active.id === s.id && 'selected')}>
      <button disabled={busy} onClick={() => onSelect(s.id)} aria-current={active.id === s.id ? 'page' : undefined}><MessageSquare size={15}/><span>{s.title}</span></button>
      <RenameConversationDialog session={s} disabled={busy} onSave={title => onRename(s.id, title)}/>
      <IconButton label={`Delete ${s.title}`} disabled={busy} onClick={() => setDeleting(s.id)}><Trash2 size={14}/></IconButton>
    </div>)}{!sessions.some(s => s.title.toLowerCase().includes(filter.toLowerCase())) && <p className="muted p-3 text-sm">No matching conversations.</p>}</nav>
    <div className="sidebar-documents" aria-busy={documentsLoading}>
      <div className="sidebar-label">DOCUMENTS <button className="library-open" onClick={onOpenLibrary} aria-label="Browse document library"><FolderOpen size={14}/><span className="tabular-nums">{documents.length}</span></button></div>
      {documents.map(doc => <button key={doc.doc_id} disabled={busy} aria-pressed={doc.doc_id === active.doc?.doc_id} className={cn('document-row', doc.doc_id === active.doc?.doc_id && 'selected')} onClick={() => selectDoc(doc)}><FileText size={16}/><span>{doc.filename}</span>{doc.doc_id === active.doc?.doc_id && <Check size={14}/>}</button>)}
      {documentsLoading && <p className="muted text-xs px-2" role="status">Loading documents…</p>}
      {documentsError && <div className="document-error" role="alert"><p>{documentsError}</p><button className="secondary mt-2" onClick={onRetry}>Retry documents</button></div>}
      {!documentsLoading && !documentsError && !documents.length && <p className="muted text-xs px-2">Attach a PDF, text, or Markdown file to get started.</p>}
    </div>
    <footer className="sidebar-footer"><ShieldCheck size={16}/><span>Conversations saved on this device</span></footer>
  </>;
}
