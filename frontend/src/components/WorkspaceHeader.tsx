import * as Dropdown from '@radix-ui/react-dropdown-menu';
import * as Dialog from '@radix-ui/react-dialog';
import { PanelLeft, FileText, Check, ChevronDown, Sun, Moon, FolderOpen } from 'lucide-react';
import type { Document } from '../types';
import { IconButton } from './ui';

type Props = {
  doc?: Document;
  documents: Document[];
  loading: boolean;
  error: string;
  busy: boolean;
  theme: string;
  onOpenNavigation: () => void;
  onSelectDocument: (doc: Document) => void;
  onRetryDocuments: () => void;
  onToggleTheme: () => void;
  onOpenLibrary: () => void;
};

export function WorkspaceHeader({ doc, documents, loading, error, busy, theme, onOpenNavigation, onSelectDocument, onRetryDocuments, onToggleTheme, onOpenLibrary }: Props) {
  return (
    <header className="topbar">
      <IconButton label="Open navigation" className="mobile-toggle" onClick={onOpenNavigation}><PanelLeft size={18}/></IconButton>
      <div className="topbar-title"><span>Document assistant</span><span className="muted">Answers grounded in your files</span></div>
      <div className="header-actions">
        <Dialog.Trigger asChild><IconButton label="Open document library" onClick={onOpenLibrary}><FolderOpen size={18}/></IconButton></Dialog.Trigger>
        <Dropdown.Root>
          <Dropdown.Trigger className="context-picker" disabled={busy}>
            <FileText size={15}/><span>{doc?.filename || 'Choose document'}</span><ChevronDown size={14}/>
          </Dropdown.Trigger>
          <Dropdown.Portal>
            <Dropdown.Content className="menu" align="end" sideOffset={8}>
              <Dropdown.RadioGroup value={doc?.doc_id || ''} onValueChange={id => {
                const selected = documents.find(item => item.doc_id === id);
                if (selected) onSelectDocument(selected);
              }}>
                {documents.map(item => (
                  <Dropdown.RadioItem key={item.doc_id} value={item.doc_id} className="menu-item">
                    {item.filename}<Dropdown.ItemIndicator><Check size={14}/></Dropdown.ItemIndicator>
                  </Dropdown.RadioItem>
                ))}
              </Dropdown.RadioGroup>
              {loading && <p className="p-3 text-sm muted" role="status">Loading documents…</p>}
              {error && <>
                <p className="document-error p-3" role="alert">{error}</p>
                <Dropdown.Item className="menu-item" onSelect={event => { event.preventDefault(); onRetryDocuments(); }}>Retry documents</Dropdown.Item>
              </>}
              {!loading && !error && !documents.length && <div className="p-3 text-sm muted">Attach a file using the paperclip.</div>}
            </Dropdown.Content>
          </Dropdown.Portal>
        </Dropdown.Root>
        <IconButton label={theme === 'light' ? 'Use dark theme' : 'Use light theme'} onClick={onToggleTheme}>
          {theme === 'light' ? <Moon size={17}/> : <Sun size={17}/>}
        </IconButton>
      </div>
    </header>
  );
}
