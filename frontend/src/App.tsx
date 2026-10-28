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
import { DocumentLibrary } from './components/DocumentLibrary';
import { IconButton } from './components/ui';

const STORAGE = 'ragit_assistant_sessions_v1';
const fresh = (): Session => ({ id: crypto.randomUUID(), title: 'New conversation', updated: Date.now() });
function stored(key: string) { try { return localStorage.getItem(key); } catch { return null; } }
function restore(storage: string): Session[] { try { const value = JSON.parse(stored(storage) || '[]'); return Array.isArray(value) ? value.filter(s => s && typeof s.id === 'string' && typeof s.title === 'string').slice(0, 100) : []; } catch { return []; } }

export function App({ ownerId = "local" }: { ownerId?: string }) {
  const storage = `${STORAGE}:${ownerId}`;
  const activeStorage = `ragit_active_session:${ownerId}`;
  const [sessions, setSessions] = useState<Session[]>(() => { const saved = restore(storage); return saved.length ? saved : [fresh()]; });
  const [activeId, setActiveId] = useState(() => sessions.find(s => s.id === stored(activeStorage))?.id || sessions[0].id);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(true);
  const [documentsError, setDocumentsError] = useState('');
  const [source, setSource] = useState<Source>();
  const [sidebar, setSidebar] = useState(false);
  const [filter, setFilter] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [deleting, setDeleting] = useState<string>();
  const [library, setLibrary] = useState(false);
  const [theme, setTheme] = useState(() => stored('ragit_theme') === 'dark' ? 'dark' : 'light');
  const active = sessions.find(s => s.id === activeId) || sessions[0];
  const unavailable = !!active.doc && !documentsLoading && !documentsError && !documents.some(doc => doc.doc_id === active.doc?.doc_id);
  useEffect(() => { document.documentElement.dataset.theme = theme; try { localStorage.setItem('ragit_theme', theme); } catch { /* Theme still works for this visit. */ } }, [theme]);
  useEffect(() => { try { localStorage.setItem(activeStorage, activeId); } catch { /* The session remains available in memory. */ } }, [activeId]);
  useEffect(() => { try { localStorage.setItem(storage, JSON.stringify(sessions)); } catch { setNotice('Browser storage is full. Export important answers before leaving.'); } }, [sessions]);
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
  const newChat = () => { const next = fresh(); next.doc = unavailable ? undefined : active.doc; setSessions(all => [next, ...all]); setActiveId(next.id); setSidebar(false); setFilter(''); setNotice(''); };
  const selectDoc = (doc: Document) => {
    const hasMessages = !!(active.repository as { messages?: unknown[] } | undefined)?.messages?.length;
    if (hasMessages && active.doc?.doc_id !== doc.doc_id) {
      const next = { ...fresh(), doc };
      setSessions(all => [next, ...all]); setActiveId(next.id); setFilter('');
    } else updateSession(active.id, { doc });
    setSidebar(false); setLibrary(false); setSource(undefined); setNotice('');
  };
  const navigation = <WorkspaceNavigation sessions={sessions} active={active} documents={documents}
    busy={busy} filter={filter} setFilter={setFilter} newChat={newChat} selectDoc={selectDoc}
    onSelect={id => { setActiveId(id); setSidebar(false); setNotice(''); }} setDeleting={setDeleting} onRename={(id, title) => updateSession(id, { title, customTitle: true })}
    onOpenLibrary={() => { setSidebar(false); setLibrary(true); }}
    documentsLoading={documentsLoading} documentsError={documentsError} onRetry={refreshDocs}/>;
  return <Tooltip.Provider delayDuration={300}><Dialog.Root open={library} onOpenChange={setLibrary}><div className="app-shell">
    <aside className="desktop-sidebar">{navigation}</aside>
    <Dialog.Root open={sidebar} onOpenChange={setSidebar}><Dialog.Portal><Dialog.Overlay className="overlay"/><Dialog.Content className="mobile-sidebar"><Dialog.Title className="sr-only">Workspace navigation</Dialog.Title><Dialog.Description className="sr-only">Choose a conversation or document.</Dialog.Description><Dialog.Close className="mobile-close icon-button" aria-label="Close navigation"><X size={18}/></Dialog.Close>{navigation}</Dialog.Content></Dialog.Portal></Dialog.Root>
    <main className="main"><WorkspaceHeader doc={active.doc} documents={documents} loading={documentsLoading}
      error={documentsError} busy={busy} theme={theme} onOpenNavigation={() => setSidebar(true)}
      onSelectDocument={selectDoc} onRetryDocuments={refreshDocs}
      onOpenLibrary={() => setLibrary(true)}
      onToggleTheme={() => setTheme(theme === 'light' ? 'dark' : 'light')}/>
      {notice && <div className="notice" role="alert">{notice}<IconButton label="Dismiss notice" onClick={() => setNotice('')}><X size={14}/></IconButton></div>}
      {unavailable && <div className="notice" role="status"><span>This conversation’s document is no longer loaded. Reattach it or choose a file from the library to continue.</span><button className="secondary" onClick={() => setLibrary(true)}>Choose file</button></div>}
      <UIContext.Provider value={{ openSource: setSource, doc: active.doc, error: setNotice }}><ChatSession key={active.id} session={active} unavailable={unavailable} onChange={change => {
        if (change.doc && change.doc.doc_id !== active.doc?.doc_id && (active.repository as { messages?: unknown[] } | undefined)?.messages?.length) selectDoc(change.doc);
        else updateSession(active.id, change);
      }} onBusy={setBusy} onDocuments={refreshDocs}/></UIContext.Provider>
    </main>
    <SourceDrawer source={source} onClose={() => setSource(undefined)}/>
    {library && <DocumentLibrary documents={documents} currentId={active.doc?.doc_id} loading={documentsLoading} error={documentsError} busy={busy} onRetry={refreshDocs} onSelect={selectDoc} onClose={() => setLibrary(false)}/>}
    <DeleteConversationDialog open={!!deleting} onClose={() => setDeleting(undefined)} onConfirm={() => {
      const remaining = sessions.filter(s => s.id !== deleting);
      if (!remaining.length) remaining.push(fresh());
      setSessions(remaining);
      if (deleting === activeId) setActiveId(remaining[0].id);
      setDeleting(undefined);
    }}/>
  </div></Dialog.Root></Tooltip.Provider>;
}
