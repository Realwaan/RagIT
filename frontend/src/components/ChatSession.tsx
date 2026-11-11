import { ActivityStatus, ConversationSearch } from './ConversationTools';
import { useContext, useEffect, useMemo, useRef, useState } from 'react';
import { AssistantRuntimeProvider, useLocalRuntime, useAuiState, ThreadPrimitive, WebSpeechSynthesisAdapter, WebSpeechDictationAdapter, type AttachmentAdapter, type ExportedMessageRepository } from '@assistant-ui/react';
import { ArrowDown } from 'lucide-react';
import { createAdapter } from '../transport';
import { request, type Document, type Session } from '../types';
import { UIContext } from './AssistantContext';
import { Welcome } from './Welcome';
import { ChatComposer, EditComposer } from './Composer';
import { UserMessage, AssistantMessage } from './Messages';
import { VisualProgress } from './VisualProgress';
import { cancelUpload, SUPPORTED_UPLOAD_ACCEPT, toUploadedDocument, uploadDocument, UploadJobError, validateUploadFile, waitForUpload } from '../upload';
import type { WorkspaceUploadState } from '../useDocumentUpload';

export function ChatSession({
  session, unavailable, uploadState, onChange, onBusy, onDocuments, onVaultUpdate,
}: {
  session: Session;
  unavailable: boolean;
  uploadState?: WorkspaceUploadState;
  onChange: (s: Partial<Session>) => void;
  onBusy: (busy: boolean) => void;
  onDocuments: () => void;
  onVaultUpdate?: (vault: Document[]) => void;
}) {
  const docRef = useRef(session.doc); docRef.current = session.doc;
  const titleRef = useRef(session); titleRef.current = session;
  const uploadStateRef = useRef(uploadState); uploadStateRef.current = uploadState;
  const callbacks = useRef({ onChange, onDocuments }); callbacks.current = { onChange, onDocuments };
  const error = useContext(UIContext).error;
  const [loadingSample, setLoadingSample] = useState(false);
  const [sampleError, setSampleError] = useState('');
  const [uploadProgress, setUploadProgress] = useState('');
  const [resumingUpload, setResumingUpload] = useState(!!session.uploadJob);
  const initialJob = useRef(session.uploadJob);
  const serverJobs = useRef(new Map<string, string>());
  const samplePending = useRef(false);
  const pending = useRef(new Map<string, AbortController>());
  const adapter = useMemo(() => createAdapter(() => docRef.current), []);
  const attachments = useMemo<AttachmentAdapter>(() => ({
    accept: SUPPORTED_UPLOAD_ACCEPT,
    async *add({ file }) {
      const id = crypto.randomUUID();
      const base = { id, type: 'document', name: file.name, contentType: file.type, file };
      const invalid = validateUploadFile(file, pending.current.size > 0 || Boolean(uploadStateRef.current?.uploading));
      if (invalid) { yield { ...base, status: { type: 'incomplete', reason: 'error', message: invalid } }; return; }
      const controller = new AbortController(); pending.current.set(id, controller);
      yield { ...base, status: { type: 'running', reason: 'uploading', progress: 0 } };
      try {
        const data = await uploadDocument(file, controller.signal, setUploadProgress, jobId => {
          serverJobs.current.set(id, jobId);
          callbacks.current.onChange({ uploadJob: { id: jobId, filename: file.name } });
        });
        if (controller.signal.aborted) return;
        const doc = toUploadedDocument(data);
        docRef.current = doc; callbacks.current.onChange({ doc, uploadJob: undefined }); callbacks.current.onDocuments();
        yield { ...base, status: { type: 'requires-action', reason: 'composer-send' } };
      } catch (e) { pending.current.delete(id); if (e instanceof UploadJobError) callbacks.current.onChange({ uploadJob: undefined }); if (!controller.signal.aborted) yield { ...base, status: { type: 'incomplete', reason: 'error', message: (e as Error).message } }; }
      finally { setUploadProgress(''); }
    },
    async remove(attachment) {
      const job = serverJobs.current.get(attachment.id);
      if (job && pending.current.has(attachment.id)) await cancelUpload(job);
      pending.current.get(attachment.id)?.abort(); pending.current.delete(attachment.id); serverJobs.current.delete(attachment.id);
      callbacks.current.onChange({ uploadJob: undefined });
    },
    async send(attachment) { pending.current.delete(attachment.id); serverJobs.current.delete(attachment.id); return { ...attachment, status: { type: 'complete' }, content: [] }; },
  }), []);

  useEffect(() => {
    const job = initialJob.current;
    if (!job || uploadStateRef.current?.uploading) return;
    const controller = new AbortController();
    pending.current.set(job.id, controller);
    void waitForUpload(job.id, controller.signal, setUploadProgress).then(data => {
      if (controller.signal.aborted) return;
      const doc = toUploadedDocument(data);
      docRef.current = doc;
      callbacks.current.onChange({ doc, uploadJob: undefined }); callbacks.current.onDocuments();
    }).catch(e => {
      if (!controller.signal.aborted) {
        if (e instanceof UploadJobError) callbacks.current.onChange({ uploadJob: undefined });
        error((e as Error).message);
      }
    }).finally(() => { pending.current.delete(job.id); setResumingUpload(false); setUploadProgress(''); });
    return () => controller.abort();
  }, []);

  const runtimeAdapters = useMemo(() => ({
    attachments,
    speech: 'speechSynthesis' in window ? new WebSpeechSynthesisAdapter() : undefined,
    dictation: ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window) ? new WebSpeechDictationAdapter() : undefined,
    feedback: { async submit({ message, type }: { message: { id: string }; type: string }) { try { localStorage.setItem(`ragit_feedback_${message.id}`, type); } catch { error('Feedback could not be saved on this device.'); } } },
  }), [attachments, error]);
  const runtime = useLocalRuntime(adapter, { adapters: runtimeAdapters });

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
      if (state.isRunning || state.isLoading) return;
      const repository = runtime.thread.export();
      if (!repository.messages.length && (titleRef.current.repository as { messages?: unknown[] } | undefined)?.messages?.length) return;
      const first = state.messages.find(m => m.role === 'user');
      const title = titleRef.current.customTitle ? titleRef.current.title : first?.content.filter(p => p.type === 'text').map(p => p.text).join(' ').slice(0, 70) || titleRef.current.title;
      callbacks.current.onChange({ title, repository, updated: Date.now() });
    };
    const unsubscribe = runtime.thread.subscribe(save);
    let lastDraft = runtime.thread.composer.getState().text;
    const unsubscribeDraft = runtime.thread.composer.subscribe(() => {
      const draft = runtime.thread.composer.getState().text;
      if (draft !== lastDraft) { lastDraft = draft; callbacks.current.onChange({ draft }); }
    });
    return () => { unsubscribeDraft(); unsubscribe(); runtime.thread.cancelRun(); pending.current.forEach(controller => controller.abort()); pending.current.clear(); };
  }, [runtime]);

  const loadSample = async () => {
    if (samplePending.current) return;
    samplePending.current = true;
    setLoadingSample(true);
    setSampleError('');
    try {
      const data = await (await request('/load-sample', { method: 'POST' })).json();
      const doc = toUploadedDocument(data);
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

  const activeUploadLabel = uploadProgress || (uploadState?.uploading ? uploadState.uploadStatus : '');
  const isUploadingOrResuming = loadingSample || resumingUpload || Boolean(uploadState?.uploading);

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ActivitySync onBusy={onBusy} loadingSample={isUploadingOrResuming}/>
      {activeUploadLabel && (
        <div className="composer-hint">
          <ActivityStatus label={activeUploadLabel}/>
          {resumingUpload && initialJob.current && (
            <button type="button" className="secondary" onClick={async () => {
              const id = initialJob.current!.id;
              try { await cancelUpload(id); pending.current.get(id)?.abort(); callbacks.current.onChange({ uploadJob: undefined }); }
              catch (e) { error((e as Error).message); }
            }}>Cancel processing</button>
          )}
          {!resumingUpload && uploadState?.uploading && (
            <button type="button" className="secondary" onClick={() => void uploadState.cancelActiveUpload()}>Cancel processing</button>
          )}
        </div>
      )}
      <ThreadPrimitive.Root className="thread"><ConversationSearch/>
        <ThreadPrimitive.Viewport className="thread-viewport">
          <div className="thread-content">
            <ThreadPrimitive.Empty>
              <Welcome onSample={loadSample} loading={isUploadingOrResuming} error={sampleError} unavailable={unavailable}/>
            </ThreadPrimitive.Empty>
            <ThreadPrimitive.Messages components={{ UserMessage, AssistantMessage, EditComposer }}/>
          </div>
          <ThreadPrimitive.ViewportFooter className="composer-footer">
            <VisualProgress docId={session.doc?.doc_id} onVaultUpdate={onVaultUpdate}/>
            <ThreadPrimitive.ScrollToBottom className="scroll-bottom" aria-label="Jump to latest message"><ArrowDown size={17}/></ThreadPrimitive.ScrollToBottom>
            <ChatComposer disabled={isUploadingOrResuming} unavailable={unavailable}/>
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
