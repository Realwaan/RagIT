import { useContext, useEffect, useMemo, useRef, useState } from 'react';
import { AssistantRuntimeProvider, useLocalRuntime, useAuiState, ThreadPrimitive, WebSpeechSynthesisAdapter, WebSpeechDictationAdapter, type AttachmentAdapter, type ExportedMessageRepository } from '@assistant-ui/react';
import { ArrowDown } from 'lucide-react';
import { createAdapter } from '../transport';
import { request, type Session } from '../types';
import { UIContext } from './AssistantContext';
import { Welcome } from './Welcome';
import { ChatComposer, EditComposer } from './Composer';
import { UserMessage, AssistantMessage } from './Messages';

export function ChatSession({ session, onChange, onBusy, onDocuments }: { session: Session; onChange: (s: Partial<Session>) => void; onBusy: (busy: boolean) => void; onDocuments: () => void }) {
  const docRef = useRef(session.doc); docRef.current = session.doc;
  const callbacks = useRef({ onChange, onDocuments }); callbacks.current = { onChange, onDocuments };
  const error = useContext(UIContext).error;
  const [loadingSample, setLoadingSample] = useState(false);
  const [sampleError, setSampleError] = useState('');
  const samplePending = useRef(false);
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
  const loadSample = async () => {
    if (samplePending.current) return;
    samplePending.current = true;
    setLoadingSample(true);
    setSampleError('');
    try {
      const data = await (await request('/load-sample', { method: 'POST' })).json();
      const doc = { doc_id: data.doc_id, filename: data.filename };
      docRef.current = doc;
      callbacks.current.onChange({ doc });
      callbacks.current.onDocuments();
    } catch (e) {
      setSampleError((e as Error).message);
    } finally {
      samplePending.current = false;
      setLoadingSample(false);
    }
  };
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ActivitySync onBusy={onBusy} loadingSample={loadingSample}/>
      <ThreadPrimitive.Root className="thread">
        <ThreadPrimitive.Viewport className="thread-viewport">
          <div className="thread-content">
            <ThreadPrimitive.Empty>
              <Welcome onSample={loadSample} loading={loadingSample} error={sampleError}/>
            </ThreadPrimitive.Empty>
            <ThreadPrimitive.Messages components={{ UserMessage, AssistantMessage, EditComposer }}/>
          </div>
          <ThreadPrimitive.ViewportFooter className="composer-footer">
            <ThreadPrimitive.ScrollToBottom className="scroll-bottom" aria-label="Jump to latest message"><ArrowDown size={17}/></ThreadPrimitive.ScrollToBottom>
            <ChatComposer disabled={loadingSample}/>
          </ThreadPrimitive.ViewportFooter>
        </ThreadPrimitive.Viewport>
      </ThreadPrimitive.Root>
    </AssistantRuntimeProvider>
  );
}

function ActivitySync({ onBusy, loadingSample }: { onBusy: (b: boolean) => void; loadingSample: boolean }) {
  const running = useAuiState(s => s.thread.isRunning);
  const uploading = useAuiState(s => s.composer.attachments.some(a => a.status.type === 'running'));
  useEffect(() => { onBusy(running || uploading || loadingSample); return () => onBusy(false); }, [running, uploading, loadingSample, onBusy]);
  return null;
}
