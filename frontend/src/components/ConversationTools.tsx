import { useEffect, useState } from 'react';
import { useAui, useAuiState } from '@assistant-ui/react';

export function ActivityStatus({ label }: { label: string }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => { const start = Date.now(); const timer = setInterval(() => setSeconds(Math.floor((Date.now() - start) / 1000)), 1000); return () => clearInterval(timer); }, []);
  return <div className="activity"><span role="status">{label}</span><span className="muted" aria-label="Elapsed time"> · {seconds}s</span><progress aria-label="Processing" /></div>;
}

export function ConversationSearch() {
  const messages = useAuiState(s => s.thread.messages);
  const [query, setQuery] = useState('');
  const matches = query.trim() ? messages.filter(m => m.content.some(p => p.type === 'text' && p.text.toLowerCase().includes(query.trim().toLowerCase()))) : [];
  return <details className="conversation-search"><summary>Search this conversation</summary><input aria-label="Search messages" placeholder="Find words in this conversation" value={query} onChange={e => setQuery(e.target.value)} />{query.trim() && <><p role="status">{matches.length} matching messages</p><div className="search-results">{matches.map(m => <button key={m.id} onClick={() => { const target = document.getElementById(`message-${m.id}`); target?.scrollIntoView({ block: 'center', behavior: 'instant' }); target?.focus({ preventScroll: true }); }}>{m.role === 'user' ? 'You' : 'RagIT'}: {m.content.filter(p => p.type === 'text').map(p => p.text).join(' ').slice(0, 180)}</button>)}</div></>}</details>;
}

export function QuoteSelection({ messageId }: { messageId: string }) {
  const runtime = useAui();
  const [quote, setQuote] = useState('');
  useEffect(() => {
    const update = () => { const selection = window.getSelection(); const root = document.getElementById(`message-${messageId}`); setQuote(selection && root?.contains(selection.anchorNode) && root.contains(selection.focusNode) ? selection.toString().trim().slice(0, 4000) : ''); };
    document.addEventListener('selectionchange', update);
    return () => document.removeEventListener('selectionchange', update);
  }, [messageId]);
  return <button className="secondary" disabled={!quote} title="Select text in this answer first" onMouseDown={e => e.preventDefault()} onClick={() => { const draft = runtime.composer.getState().text; runtime.composer.setText(`${draft ? draft + '\n\n' : ''}${quote.split('\n').map(line => '> ' + line).join('\n')}\n\n`); document.querySelector<HTMLTextAreaElement>('.composer-input')?.focus(); }}>Quote selection</button>;
}

