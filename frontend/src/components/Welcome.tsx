import { useContext } from 'react';
import { ThreadPrimitive, useAuiState } from '@assistant-ui/react';
import { Sparkles, BookOpen, ChevronRight } from 'lucide-react';
import { UIContext } from './AssistantContext';

export function Welcome({ onSample, loading, error }: { onSample: () => void; loading: boolean; error: string }) {
  const uploading = useAuiState(s => s.composer.attachments.some(a => a.status.type === 'running'));
  const busy = loading || uploading;
  const { doc } = useContext(UIContext);
  return <section className="welcome"><div className="welcome-icon"><Sparkles size={28}/></div><p className="eyebrow">YOUR DOCUMENTS, MADE CLEAR</p><h1>What would you like<br/>to understand?</h1><p className="welcome-subtitle">Find the answer, see the evidence, and keep the conversation going.</p><div className="suggestions">{[
    ['Find the essentials', 'Summarize the key requirements in this document.'],
    ['Check the details', 'What deadlines and obligations should I know about?'],
    ['Compare the evidence', 'Are there conflicting claims or figures in this document?'],
  ].map(([title, prompt]) => <ThreadPrimitive.Suggestion disabled={busy} key={title} prompt={prompt} method="replace" autoSend={!!doc} className="suggestion"><BookOpen size={18}/><strong>{title}</strong><span>{prompt}</span></ThreadPrimitive.Suggestion>)}</div>{!doc && <button className="sample-button" disabled={busy} onClick={onSample}>{loading ? 'Loading sample document...' : 'Explore with a sample document'} <ChevronRight size={14}/></button>}{loading && <p className="muted text-sm" role="status">Preparing your sample document...</p>}{error && <p className="sample-error" role="alert">{error}</p>}</section>;
}
