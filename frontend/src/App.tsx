import { useState, useEffect, useMemo, useRef, createContext, useContext, type ReactElement } from 'react';
import {
  AssistantRuntimeProvider, useLocalRuntime, useAuiState,
  ThreadPrimitive, ComposerPrimitive, MessagePrimitive, ActionBarPrimitive, BranchPickerPrimitive,
  AttachmentPrimitive, ErrorPrimitive, WebSpeechSynthesisAdapter, WebSpeechDictationAdapter,
  type AttachmentAdapter, type ExportedMessageRepository,
} from '@assistant-ui/react';
import * as Dialog from '@radix-ui/react-dialog';
import * as Tooltip from '@radix-ui/react-tooltip';
import * as Dropdown from '@radix-ui/react-dropdown-menu';
import * as AlertDialog from '@radix-ui/react-alert-dialog';
import { Sparkles, Plus, PanelLeft, Search, MessageSquare, FileText, ArrowUp, ArrowDown, Square, Paperclip, X, Copy, Check, RefreshCw, Pencil, ChevronLeft, ChevronRight, ChevronDown, Download, Volume2, VolumeX, Mic, ThumbsUp, ThumbsDown, Sun, Moon, Trash2, BookOpen, ShieldCheck } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { createAdapter } from './transport';
import { Markdown, EvidenceContext } from './Markdown';
import { request, type Document, type Session, type Source, type Result } from './types';

const cn = (...values: ClassValue[]) => twMerge(clsx(values));
const STORAGE = 'ragit_assistant_sessions_v1';
const fresh = (): Session => ({ id: crypto.randomUUID(), title: 'New conversation', updated: Date.now() });
function restore(): Session[] { try { const value = JSON.parse(localStorage.getItem(STORAGE) || '[]'); return Array.isArray(value) ? value.filter(s => s.id && s.title).slice(0, 100) : []; } catch { return []; } }
const UIContext = createContext<{ openSource: (source: Source) => void; doc?: Document; error: (text: string) => void }>({ openSource: () => {}, error: () => {} });
function Tip({ label, children }: { label: string; children: ReactElement }) {
  return <Tooltip.Root><Tooltip.Trigger asChild>{children}</Tooltip.Trigger><Tooltip.Portal><Tooltip.Content className="tooltip" sideOffset={6}>{label}<Tooltip.Arrow /></Tooltip.Content></Tooltip.Portal></Tooltip.Root>;
}
function IconButton({ label, children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return <Tip label={label}><button {...props} type="button" aria-label={label} className={cn('icon-button', props.className)}>{children}</button></Tip>;
}

export function App() {
  const [sessions, setSessions] = useState<Session[]>(() => { const saved = restore(); return saved.length ? saved : [fresh()]; });
  const [activeId, setActiveId] = useState(() => sessions[0].id);
  const [documents, setDocuments] = useState<Document[]>([]);
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
  const refreshDocs = () => request('/vault').then(r => r.json()).then(data => setDocuments(data.vault)).catch(e => setNotice(e.message));
  useEffect(() => { refreshDocs(); }, []);
  const updateSession = (id: string, change: Partial<Session>) => setSessions(all => all.map(s => s.id === id ? { ...s, ...change } : s));
  const newChat = () => { const next = fresh(); next.doc = active.doc; setSessions(all => [next, ...all]); setActiveId(next.id); setSidebar(false); };
  const selectDoc = (doc: Document) => { updateSession(active.id, { doc }); setSidebar(false); };
  const navigation = <>
    <div className="sidebar-brand"><span className="logo"><Sparkles size={19}/></span><strong>RagIT</strong><span className="muted text-xs">Workspace</span></div>
    <button className="new-chat" onClick={newChat} disabled={busy}><Plus size={17}/> New conversation</button>
    <label className="search"><Search size={15}/><input aria-label="Search conversations" placeholder="Search conversations" value={filter} onChange={e => setFilter(e.target.value)}/></label>
    <div className="sidebar-label">CONVERSATIONS</div>
    <nav className="conversation-list" aria-label="Conversations">{sessions.filter(s => s.title.toLowerCase().includes(filter.toLowerCase())).map(s => <div key={s.id} className={cn('conversation-row', active.id === s.id && 'selected')}>
      <button disabled={busy} onClick={() => { setActiveId(s.id); setSidebar(false); setNotice(''); }} aria-current={active.id === s.id ? 'page' : undefined}><MessageSquare size={15}/><span>{s.title}</span></button>
      <IconButton label={`Delete ${s.title}`} disabled={busy} onClick={() => setDeleting(s.id)}><Trash2 size={14}/></IconButton>
    </div>)}{!sessions.some(s => s.title.toLowerCase().includes(filter.toLowerCase())) && <p className="muted p-3 text-sm">No matching conversations.</p>}</nav>
    <div className="sidebar-documents"><div className="sidebar-label">DOCUMENTS <span>{documents.length}</span></div>{documents.map(doc => <button key={doc.doc_id} disabled={busy} className={cn('document-row', doc.doc_id === active.doc?.doc_id && 'selected')} onClick={() => selectDoc(doc)}><FileText size={16}/><span>{doc.filename}</span>{doc.doc_id === active.doc?.doc_id && <Check size={14}/>}</button>)}{!documents.length && <p className="muted text-xs px-2">Attach a PDF, text, or Markdown file to get started.</p>}</div>
    <footer className="sidebar-footer"><ShieldCheck size={16}/><span>Conversations saved on this device</span><a href="/classic">Classic view</a></footer>
  </>;
  return <Tooltip.Provider delayDuration={300}><div className="app-shell">
    <aside className="desktop-sidebar">{navigation}</aside>
    <Dialog.Root open={sidebar} onOpenChange={setSidebar}><Dialog.Portal><Dialog.Overlay className="overlay"/><Dialog.Content className="mobile-sidebar"><Dialog.Title className="sr-only">Workspace navigation</Dialog.Title><Dialog.Description className="sr-only">Choose a conversation or document.</Dialog.Description><Dialog.Close className="mobile-close icon-button" aria-label="Close navigation"><X size={18}/></Dialog.Close>{navigation}</Dialog.Content></Dialog.Portal></Dialog.Root>
    <main className="main"><header className="topbar"><IconButton label="Open navigation" className="mobile-toggle" onClick={() => setSidebar(true)}><PanelLeft size={18}/></IconButton><div className="topbar-title"><span>Document assistant</span><span className="muted">Answers grounded in your files</span></div><div className="header-actions">
      <Dropdown.Root><Dropdown.Trigger className="context-picker" disabled={busy}><FileText size={15}/><span>{active.doc?.filename || 'Choose document'}</span><ChevronDown size={14}/></Dropdown.Trigger><Dropdown.Portal><Dropdown.Content className="menu" align="end" sideOffset={8}>{documents.length ? documents.map(doc => <Dropdown.Item key={doc.doc_id} className="menu-item" onSelect={() => selectDoc(doc)}>{doc.filename}{active.doc?.doc_id === doc.doc_id && <Check size={14}/>}</Dropdown.Item>) : <div className="p-3 text-sm muted">Attach a file using the paperclip.</div>}</Dropdown.Content></Dropdown.Portal></Dropdown.Root>
      <IconButton label={theme === 'light' ? 'Use dark theme' : 'Use light theme'} onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}>{theme === 'light' ? <Moon size={17}/> : <Sun size={17}/>}</IconButton></div></header>
      {notice && <div className="notice" role="alert">{notice}<IconButton label="Dismiss notice" onClick={() => setNotice('')}><X size={14}/></IconButton></div>}
      <UIContext.Provider value={{ openSource: setSource, doc: active.doc, error: setNotice }}><ChatSession key={active.id} session={active} onChange={change => updateSession(active.id, change)} onBusy={setBusy} onDocuments={refreshDocs}/></UIContext.Provider>
    </main>
    <Dialog.Root open={!!source} onOpenChange={open => { if (!open) setSource(undefined); }}><Dialog.Portal><Dialog.Overlay className="overlay"/><Dialog.Content className="source-drawer"><div className="drawer-heading"><BookOpen size={20}/><Dialog.Title>Source evidence</Dialog.Title><Dialog.Close className="icon-button" aria-label="Close source"><X size={20}/></Dialog.Close></div><Dialog.Description className="muted">{source?.filename} · Page {source?.page}</Dialog.Description><div className="source-quote">{source?.parent_text}</div>{source?.image_url && <a href={source.image_url} target="_blank" rel="noreferrer"><img src={source.image_url} alt={`Document evidence, page ${source.page}`} /></a>}{source?.linked_visuals?.filter(v => v.image_url && v.image_url !== source.image_url).map((visual, i) => <figure key={i}><img src={visual.image_url} alt={visual.title}/><figcaption>{visual.title}</figcaption></figure>)}</Dialog.Content></Dialog.Portal></Dialog.Root>
    <AlertDialog.Root open={!!deleting} onOpenChange={open => { if (!open) setDeleting(undefined); }}><AlertDialog.Portal><AlertDialog.Overlay className="overlay"/><AlertDialog.Content className="confirm-dialog"><AlertDialog.Title>Delete this conversation?</AlertDialog.Title><AlertDialog.Description>The saved messages and response versions will be removed from this browser. Your documents stay available.</AlertDialog.Description><div className="flex justify-end gap-2 mt-6"><AlertDialog.Cancel className="secondary">Keep conversation</AlertDialog.Cancel><AlertDialog.Action className="danger" onClick={() => { const remaining = sessions.filter(s => s.id !== deleting); if (!remaining.length) remaining.push(fresh()); setSessions(remaining); if (deleting === activeId) setActiveId(remaining[0].id); setDeleting(undefined); }}>Delete</AlertDialog.Action></div></AlertDialog.Content></AlertDialog.Portal></AlertDialog.Root>
  </div></Tooltip.Provider>;
}

function ChatSession({ session, onChange, onBusy, onDocuments }: { session: Session; onChange: (s: Partial<Session>) => void; onBusy: (busy: boolean) => void; onDocuments: () => void }) {
  const docRef = useRef(session.doc); docRef.current = session.doc;
  const callbacks = useRef({ onChange, onDocuments }); callbacks.current = { onChange, onDocuments };
  const error = useContext(UIContext).error;
  const pending = useRef(new Set<string>());
  const adapter = useMemo(() => createAdapter(() => docRef.current), []);
  const attachments = useMemo<AttachmentAdapter>(() => ({
    accept: '.pdf,.txt,.md',
    async *add({ file }) {
      if (pending.current.size) throw new Error('Attach one document at a time. Remove the current attachment first.');
      if (!/\.(pdf|txt|md)$/i.test(file.name)) throw new Error('Choose a PDF, TXT, or Markdown file.');
      if (file.size > 500 * 1024 * 1024) throw new Error('The file must be smaller than 500 MB.');
      const id = crypto.randomUUID(); pending.current.add(id);
      const base = { id, type: 'document', name: file.name, contentType: file.type, file };
      yield { ...base, status: { type: 'running', reason: 'uploading', progress: 0 } };
      try {
        const form = new FormData(); form.append('file', file);
        const data = await (await request('/upload', { method: 'POST', body: form })).json();
        const doc = { doc_id: data.doc_id, filename: data.filename, pages: data.pages_processed };
        docRef.current = doc; callbacks.current.onChange({ doc }); callbacks.current.onDocuments();
        yield { ...base, status: { type: 'requires-action', reason: 'composer-send' } };
      } catch (e) { pending.current.delete(id); yield { ...base, status: { type: 'incomplete', reason: 'error', message: (e as Error).message } }; }
    },
    async remove(attachment) { pending.current.delete(attachment.id); },
    async send(attachment) { pending.current.delete(attachment.id); return { ...attachment, status: { type: 'complete' }, content: [] }; },
  }), []);
  const runtime = useLocalRuntime(adapter, { adapters: { attachments,
    speech: 'speechSynthesis' in window ? new WebSpeechSynthesisAdapter() : undefined,
    dictation: ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window) ? new WebSpeechDictationAdapter() : undefined,
    feedback: { async submit({ message, type }) { try { localStorage.setItem(`ragit_feedback_${message.id}`, type); } catch { error('Feedback could not be saved on this device.'); } } },
  } });
  useEffect(() => {
    try {
      if (session.repository) {
        const repository = structuredClone(session.repository) as ExportedMessageRepository;
        for (const item of repository.messages) item.message = { ...item.message, createdAt: new Date(item.message.createdAt) };
        runtime.thread.import(repository);
      }
      if (session.draft) runtime.thread.composer.setText(session.draft);
    } catch { error('This conversation could not be restored. Start a new conversation to continue.'); }
    const save = () => {
      const state = runtime.thread.getState();
      if (state.isRunning) return;
      const first = state.messages.find(m => m.role === 'user');
      const title = first?.content.filter(p => p.type === 'text').map(p => p.text).join(' ').slice(0, 70) || session.title;
      callbacks.current.onChange({ title, repository: runtime.thread.export(), updated: Date.now() });
    };
    const unsubscribe = runtime.thread.subscribe(save);
    let timer: ReturnType<typeof setTimeout>;
    const unsubscribeDraft = runtime.thread.composer.subscribe(() => { clearTimeout(timer); timer = setTimeout(() => callbacks.current.onChange({ draft: runtime.thread.composer.getState().text }), 300); });
    return () => { clearTimeout(timer); unsubscribeDraft(); unsubscribe(); runtime.thread.cancelRun(); };
  }, [runtime]);
  return <AssistantRuntimeProvider runtime={runtime}><ActivitySync onBusy={onBusy}/><ThreadPrimitive.Root className="thread">
    <ThreadPrimitive.Viewport className="thread-viewport"><div className="thread-content"><ThreadPrimitive.Empty><Welcome onSample={async () => { try { onBusy(true); const data = await (await request('/load-sample', { method: 'POST' })).json(); const doc = { doc_id: data.doc_id, filename: data.filename }; docRef.current = doc; onChange({ doc }); onDocuments(); } catch (e) { error((e as Error).message); } finally { onBusy(false); } }}/></ThreadPrimitive.Empty><ThreadPrimitive.Messages components={{ UserMessage, AssistantMessage, EditComposer }}/></div><ThreadPrimitive.ViewportFooter className="composer-footer"><ThreadPrimitive.ScrollToBottom className="scroll-bottom" aria-label="Jump to latest message"><ArrowDown size={17}/></ThreadPrimitive.ScrollToBottom><ChatComposer/></ThreadPrimitive.ViewportFooter></ThreadPrimitive.Viewport>
  </ThreadPrimitive.Root></AssistantRuntimeProvider>;
}

function ActivitySync({ onBusy }: { onBusy: (b: boolean) => void }) {
  const running = useAuiState(s => s.thread.isRunning);
  const uploading = useAuiState(s => s.composer.attachments.some(a => a.status.type === 'running'));
  useEffect(() => { onBusy(running || uploading); return () => onBusy(false); }, [running, uploading, onBusy]);
  return null;
}
function Welcome({ onSample }: { onSample: () => void }) {
  const { doc } = useContext(UIContext);
  return <section className="welcome"><div className="welcome-icon"><Sparkles size={28}/></div><p className="eyebrow">YOUR DOCUMENTS, MADE CLEAR</p><h1>What would you like<br/>to understand?</h1><p className="welcome-subtitle">Find the answer, see the evidence, and keep the conversation going.</p><div className="suggestions">{[
    ['Find the essentials', 'Summarize the key requirements in this document.'],
    ['Check the details', 'What deadlines and obligations should I know about?'],
    ['Compare the evidence', 'Are there conflicting claims or figures in this document?'],
  ].map(([title, prompt]) => <ThreadPrimitive.Suggestion key={title} prompt={prompt} method="replace" autoSend={!!doc} className="suggestion"><BookOpen size={18}/><strong>{title}</strong><span>{prompt}</span></ThreadPrimitive.Suggestion>)}</div>{!doc && <button className="sample-button" onClick={onSample}>Explore with a sample document <ChevronRight size={14}/></button>}</section>;
}
function Attachment() {
  const state = useAuiState(s => s.attachment);
  return <AttachmentPrimitive.Root className="attachment"><FileText size={18}/><div><AttachmentPrimitive.Name/><span>{state.status.type === 'running' ? 'Processing document…' : state.status.type === 'incomplete' ? state.status.message || 'Upload failed. Remove and retry.' : 'Ready'}</span></div><AttachmentPrimitive.Remove className="icon-button" aria-label="Remove attachment"><X size={14}/></AttachmentPrimitive.Remove></AttachmentPrimitive.Root>;
}
function ChatComposer() {
  const running = useAuiState(s => s.thread.isRunning);
  const dictating = useAuiState(s => s.composer.dictation != null);
  const { doc } = useContext(UIContext);
  return <><ComposerPrimitive.Root className="composer"><ComposerPrimitive.AttachmentDropzone className="dropzone"><div className="attachments"><ComposerPrimitive.Attachments components={{ Attachment }}/></div><ComposerPrimitive.Input className="composer-input" aria-label="Message RagIT" placeholder={doc ? 'Ask a question about your document…' : 'Attach a document, then ask anything…'} rows={2}/><div className="composer-toolbar"><div className="flex items-center gap-2"><Tip label="Attach PDF, TXT, or Markdown"><ComposerPrimitive.AddAttachment className="icon-button" aria-label="Attach document"><Paperclip size={19}/></ComposerPrimitive.AddAttachment></Tip><span className="composer-context"><FileText size={13}/>{doc?.filename || 'PDF, TXT, MD'}</span></div><div className="flex items-center gap-2">{('SpeechRecognition' in window || 'webkitSpeechRecognition' in window) && (dictating ? <ComposerPrimitive.StopDictation className="icon-button" aria-label="Stop dictation"><Square size={16}/></ComposerPrimitive.StopDictation> : <Tip label="Dictate message"><ComposerPrimitive.Dictate className="icon-button" aria-label="Dictate message"><Mic size={18}/></ComposerPrimitive.Dictate></Tip>)}{running ? <ComposerPrimitive.Cancel className="send" aria-label="Stop response"><Square size={16}/></ComposerPrimitive.Cancel> : <ComposerPrimitive.Send className="send" aria-label="Send message"><ArrowUp size={20}/></ComposerPrimitive.Send>}</div></div></ComposerPrimitive.AttachmentDropzone></ComposerPrimitive.Root><p className="composer-hint">Answers are grounded in your document. Check the sources for important details.</p></>;
}
function Branches() { return <BranchPickerPrimitive.Root hideWhenSingleBranch className="branches"><BranchPickerPrimitive.Previous className="icon-button" aria-label="Previous response version"><ChevronLeft size={14}/></BranchPickerPrimitive.Previous><BranchPickerPrimitive.Number/> / <BranchPickerPrimitive.Count/><BranchPickerPrimitive.Next className="icon-button" aria-label="Next response version"><ChevronRight size={14}/></BranchPickerPrimitive.Next></BranchPickerPrimitive.Root>; }
function UserMessage() { return <MessagePrimitive.Root className="user-message"><div className="user-bubble"><MessagePrimitive.Attachments components={{ Attachment }}/><MessagePrimitive.Content/></div><div className="user-actions"><ActionBarPrimitive.Edit className="icon-button" aria-label="Edit message"><Pencil size={14}/></ActionBarPrimitive.Edit><Branches/></div></MessagePrimitive.Root>; }
function EditComposer() { return <ComposerPrimitive.Root className="edit-composer"><ComposerPrimitive.Input aria-label="Edit your message"/><div className="flex justify-end gap-2"><ComposerPrimitive.Cancel className="secondary">Cancel</ComposerPrimitive.Cancel><ComposerPrimitive.Send className="primary">Save and resend</ComposerPrimitive.Send></div></ComposerPrimitive.Root>; }
function AssistantMessage() {
  const message = useAuiState(s => s.message);
  const { openSource, error } = useContext(UIContext);
  const result = message.metadata.custom?.result as Result | undefined;
  const running = message.status?.type === 'running';
  const stopped = message.status?.type === 'incomplete' && message.status.reason === 'cancelled';
  const activity = message.metadata.custom?.activity as string | undefined;
  const speaking = message.speech != null;
  const sources = result?.sources || [];
  const exportReport = async (format: string) => { if (!result) return; try {
    const response = await request('/export-report', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...result, format }) });
    const url = URL.createObjectURL(await response.blob()); const a = document.createElement('a'); a.href = url; a.download = `ragit-answer.${format}`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) { error((e as Error).message); } };
  return <MessagePrimitive.Root className="assistant-message"><div className="assistant-label"><span className="logo small"><Sparkles size={14}/></span><strong>RagIT</strong>{result && <span className={cn('answer-status', result.status === 'REFUSE' && 'unverified')}>{result.status === 'REFUSE' ? 'Not found in document' : 'Document-based answer'}</span>}</div>
    {running && <p className="activity" role="status">{activity || 'Preparing answer…'}</p>}
    <EvidenceContext.Provider value={{ sources, open: openSource }}><MessagePrimitive.Content components={{ Text: Markdown }}/></EvidenceContext.Provider>
    <MessagePrimitive.Error><ErrorPrimitive.Root className="message-error"><ErrorPrimitive.Message/></ErrorPrimitive.Root></MessagePrimitive.Error>
    {stopped && <p className="muted text-sm mt-3">Response stopped. You can retry below.</p>}
    {!!sources.length && <details className="source-list"><summary><BookOpen size={14}/>{sources.length} sources <ChevronDown size={13}/></summary><div className="source-cards">{sources.map(source => <button key={source.citation_id} onClick={() => openSource(source)}><span className="source-number">{source.citation_id}</span><span><strong>{source.filename}</strong><small>Page {source.page}</small></span></button>)}</div></details>}
    <ActionBarPrimitive.Root hideWhenRunning className="message-actions"><Tip label="Copy answer"><ActionBarPrimitive.Copy className="icon-button copy-action" aria-label="Copy answer"><Copy size={16} className="copy-icon"/><Check size={16} className="check-icon"/></ActionBarPrimitive.Copy></Tip><Tip label="Regenerate answer"><ActionBarPrimitive.Reload className="icon-button" aria-label="Regenerate answer"><RefreshCw size={16}/></ActionBarPrimitive.Reload></Tip>
      {'speechSynthesis' in window && (speaking ? <ActionBarPrimitive.StopSpeaking className="icon-button" aria-label="Stop reading"><VolumeX size={16}/></ActionBarPrimitive.StopSpeaking> : <Tip label="Read aloud"><ActionBarPrimitive.Speak className="icon-button" aria-label="Read aloud"><Volume2 size={16}/></ActionBarPrimitive.Speak></Tip>)}
      <Tip label="Helpful (saved on this device)"><ActionBarPrimitive.FeedbackPositive className="icon-button" aria-label="Helpful answer"><ThumbsUp size={15}/></ActionBarPrimitive.FeedbackPositive></Tip><Tip label="Not helpful (saved on this device)"><ActionBarPrimitive.FeedbackNegative className="icon-button" aria-label="Answer needs improvement"><ThumbsDown size={15}/></ActionBarPrimitive.FeedbackNegative></Tip>
      <Dropdown.Root><Dropdown.Trigger className="icon-button" aria-label="Export answer"><Download size={16}/></Dropdown.Trigger><Dropdown.Portal><Dropdown.Content className="menu" sideOffset={5}><ActionBarPrimitive.ExportMarkdown asChild><Dropdown.Item className="menu-item">Markdown</Dropdown.Item></ActionBarPrimitive.ExportMarkdown>{['pdf','docx','csv','json'].map(format => <Dropdown.Item key={format} disabled={!result} className="menu-item" onSelect={() => exportReport(format)}>{format.toUpperCase()}</Dropdown.Item>)}</Dropdown.Content></Dropdown.Portal></Dropdown.Root><Branches/>
    </ActionBarPrimitive.Root>
    {message.isLast && result?.status === 'SUCCESS' && !running && <div className="followups" aria-label="Continue exploring"><ThreadPrimitive.Suggestion prompt={`Explain the conditions and exceptions related to: ${result.query}`} method="replace" className="followup">Explain the conditions <ChevronRight size={13}/></ThreadPrimitive.Suggestion><ThreadPrimitive.Suggestion prompt={`Which exact passages support the answer to: ${result.query}`} method="replace" className="followup">Show supporting passages <ChevronRight size={13}/></ThreadPrimitive.Suggestion></div>}
  </MessagePrimitive.Root>;
}
