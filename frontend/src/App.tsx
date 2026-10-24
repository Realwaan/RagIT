import { useState, useEffect } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import * as Tooltip from '@radix-ui/react-tooltip';
import { X } from 'lucide-react';
import { request, type Document, type Session, type Source } from './types';
import { UIContext } from './components/AssistantContext';
import { ChatSession } from './components/ChatSession';
import { WorkspaceNavigation } from './components/WorkspaceNavigation';
import { WorkspaceHeader } from './components/WorkspaceHeader';
import { SourceDrawer } from './components/SourceDrawer';
import { DeleteConversationDialog } from './components/DeleteConversationDialog';
import { IconButton } from './components/ui';

const STORAGE = 'ragit_assistant_sessions_v1';
const fresh = (): Session => ({ id: crypto.randomUUID(), title: 'New conversation', updated: Date.now() });
function restore(): Session[] { try { const value = JSON.parse(localStorage.getItem(STORAGE) || '[]'); return Array.isArray(value) ? value.filter(s => s.id && s.title).slice(0, 100) : []; } catch { return []; } }

export function App() {
  const [sessions, setSessions] = useState<Session[]>(() => { const saved = restore(); return saved.length ? saved : [fresh()]; });
  const [activeId, setActiveId] = useState(() => sessions[0].id);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(true);
  const [documentsError, setDocumentsError] = useState('');
  const [source, setSource] = useState<Source>();
  const [sidebar, setSidebar] = useState(false);
  const [filter, setFilter] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [deleting, setDeleting] = useState<string>();
  const [theme, setTheme] = useState(() => localStorage.getItem('ragit_theme') || 'light');
  const active = sessions.find(s => s.id === activeId) || sessions[0];
  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem('ragit_theme', theme); }, [theme]);
  useEffect(() => { try { localStorage.setItem(STORAGE, JSON.stringify(sessions)); } catch { setNotice('Browser storage is full. Export important answers before leaving.'); } }, [sessions]);
  const refreshDocs = async () => {
    setDocumentsLoading(true);
    setDocumentsError('');
    try {
      const data = await (await request('/vault')).json();
      setDocuments(data.vault);
    } catch (e) {
      setDocumentsError((e as Error).message);
    } finally {
      setDocumentsLoading(false);
    }
  };
  useEffect(() => { refreshDocs(); }, []);
  const updateSession = (id: string, change: Partial<Session>) => setSessions(all => all.map(s => s.id === id ? { ...s, ...change } : s));
  const newChat = () => { const next = fresh(); next.doc = active.doc; setSessions(all => [next, ...all]); setActiveId(next.id); setSidebar(false); };
  const selectDoc = (doc: Document) => { updateSession(active.id, { doc }); setSidebar(false); };
  const navigation = <WorkspaceNavigation sessions={sessions} active={active} documents={documents}
    busy={busy} filter={filter} setFilter={setFilter} newChat={newChat} selectDoc={selectDoc}
    onSelect={id => { setActiveId(id); setSidebar(false); setNotice(''); }} setDeleting={setDeleting}
    documentsLoading={documentsLoading} documentsError={documentsError} onRetry={refreshDocs}/>;
  return <Tooltip.Provider delayDuration={300}><div className="app-shell">
    <aside className="desktop-sidebar">{navigation}</aside>
    <Dialog.Root open={sidebar} onOpenChange={setSidebar}><Dialog.Portal><Dialog.Overlay className="overlay"/><Dialog.Content className="mobile-sidebar"><Dialog.Title className="sr-only">Workspace navigation</Dialog.Title><Dialog.Description className="sr-only">Choose a conversation or document.</Dialog.Description><Dialog.Close className="mobile-close icon-button" aria-label="Close navigation"><X size={18}/></Dialog.Close>{navigation}</Dialog.Content></Dialog.Portal></Dialog.Root>
    <main className="main"><WorkspaceHeader doc={active.doc} documents={documents} loading={documentsLoading}
      error={documentsError} busy={busy} theme={theme} onOpenNavigation={() => setSidebar(true)}
      onSelectDocument={selectDoc} onRetryDocuments={refreshDocs}
      onToggleTheme={() => setTheme(theme === 'light' ? 'dark' : 'light')}/>
      {notice && <div className="notice" role="alert">{notice}<IconButton label="Dismiss notice" onClick={() => setNotice('')}><X size={14}/></IconButton></div>}
      <UIContext.Provider value={{ openSource: setSource, doc: active.doc, error: setNotice }}><ChatSession key={active.id} session={active} onChange={change => updateSession(active.id, change)} onBusy={setBusy} onDocuments={refreshDocs}/></UIContext.Provider>
    </main>
    <SourceDrawer source={source} onClose={() => setSource(undefined)}/>
    <DeleteConversationDialog open={!!deleting} onClose={() => setDeleting(undefined)} onConfirm={() => {
      const remaining = sessions.filter(s => s.id !== deleting);
      if (!remaining.length) remaining.push(fresh());
      setSessions(remaining);
      if (deleting === activeId) setActiveId(remaining[0].id);
      setDeleting(undefined);
    }}/>
  </div></Tooltip.Provider>;
}
