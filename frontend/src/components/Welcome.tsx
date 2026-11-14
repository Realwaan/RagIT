import { useContext } from 'react';
import { ThreadPrimitive, useAuiState } from '@assistant-ui/react';
import { Sparkles, BookOpen, CalendarClock, Scale, ChevronRight, FileCheck2 } from 'lucide-react';
import { UIContext } from './AssistantContext';

const SUGGESTIONS = [
  {
    title: 'Find the essentials',
    prompt: 'Summarize the key requirements in this document.',
    Icon: BookOpen,
  },
  {
    title: 'Check the details',
    prompt: 'What deadlines and obligations should I know about?',
    Icon: CalendarClock,
  },
  {
    title: 'Compare the evidence',
    prompt: 'Are there conflicting claims or figures in this document?',
    Icon: Scale,
  },
] as const;

export function Welcome({ onSample, loading, error, unavailable }: { onSample: () => void; loading: boolean; error: string; unavailable: boolean }) {
  const uploading = useAuiState(s => s.composer.attachments.some(a => a.status.type === 'running'));
  const busy = loading || uploading || unavailable;
  const { doc } = useContext(UIContext);
  return (
    <section className="welcome">
      <div className="welcome-icon"><Sparkles size={26} /></div>
      <p className="eyebrow">YOUR DOCUMENTS, MADE CLEAR</p>
      <h1>What would you like<br />to understand?</h1>
      <p className="welcome-subtitle">Find the answer, see the evidence, and keep the conversation going.</p>
      {doc && (
        <div className="welcome-doc-pill" role="status">
          <FileCheck2 size={14} />
          <span className="welcome-doc-name">{doc.filename}</span>
          {doc.pages ? <span className="welcome-doc-meta">{doc.pages} {doc.pages === 1 ? 'page' : 'pages'}</span> : <span className="welcome-doc-meta">Ready</span>}
        </div>
      )}
      <div className="suggestions">
        {SUGGESTIONS.map(({ title, prompt, Icon }) => (
          <ThreadPrimitive.Suggestion disabled={busy} key={title} prompt={prompt} method="replace" autoSend={!!doc} className="suggestion">
            <span className="suggestion-icon"><Icon size={17} /></span>
            <strong>{title}</strong>
            <span>{prompt}</span>
          </ThreadPrimitive.Suggestion>
        ))}
      </div>
      {!doc && (
        <button className="sample-button" disabled={busy} onClick={onSample}>
          {loading ? 'Loading sample document...' : 'Explore with a sample document'} <ChevronRight size={14} />
        </button>
      )}
      {loading && <p className="muted text-sm mt-2" role="status">Preparing your sample document...</p>}
      {error && <p className="sample-error" role="alert">{error}</p>}
    </section>
  );
}
