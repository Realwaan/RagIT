import { useEffect, useState } from 'react';
import { useAui, useAuiState } from '@assistant-ui/react';
import { Search, Quote, X } from 'lucide-react';

export function ActivityStatus({ label }: { label: string }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => { const start = Date.now(); const timer = setInterval(() => setSeconds(Math.floor((Date.now() - start) / 1000)), 1000); return () => clearInterval(timer); }, []);
  return <div className="activity"><span role="status">{label}</span><span className="muted" aria-label="Elapsed time"> · {seconds}s</span><progress aria-label="Processing" /></div>;
}

export function ConversationSearch() {
  const messages = useAuiState(s => s.thread.messages);
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const matches = query.trim() ? messages.filter(m => m.content.some(p => p.type === 'text' && p.text.toLowerCase().includes(query.trim().toLowerCase()))) : [];
  if (messages.length <= 1) return null;

  return (
    <div className="conversation-search-wrapper">
      <details className="conversation-search" open={open} onToggle={e => setOpen((e.target as HTMLDetailsElement).open)}>
        <summary className="conversation-search-summary">
          <Search size={13} />
          <span>Search in conversation</span>
          {query.trim() && matches.length > 0 && <span className="search-match-count">{matches.length}</span>}
        </summary>
        <div className="conversation-search-body">
          <div className="conversation-search-input-wrap">
            <Search size={13} className="text-muted shrink-0" />
            <input aria-label="Search messages" placeholder="Find words in this conversation…" value={query} onChange={e => setQuery(e.target.value)} autoFocus />
            {query && <button type="button" className="icon-button size-5" onClick={() => setQuery('')} aria-label="Clear search"><X size={12} /></button>}
          </div>
          {query.trim() && (
            <div className="search-results">
              <p className="search-status-label" role="status">{matches.length} matching message{matches.length === 1 ? '' : 's'}</p>
              {matches.map(m => (
                <button key={m.id} type="button" className="search-result-item" onClick={() => { const target = document.getElementById(`message-${m.id}`); target?.scrollIntoView({ block: 'center', behavior: 'smooth' }); target?.focus({ preventScroll: true }); }}>
                  <span className="search-result-role">{m.role === 'user' ? 'You' : 'RagIT'}</span>
                  <span className="search-result-text">{m.content.filter(p => p.type === 'text').map(p => p.text).join(' ').slice(0, 160)}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </details>
    </div>
  );
}

export function QuoteSelection({ messageId }: { messageId: string }) {
  const runtime = useAui();
  const [quote, setQuote] = useState('');
  useEffect(() => {
    const update = () => { const selection = window.getSelection(); const root = document.getElementById(`message-${messageId}`); setQuote(selection && root?.contains(selection.anchorNode) && root.contains(selection.focusNode) ? selection.toString().trim().slice(0, 4000) : ''); };
    document.addEventListener('selectionchange', update);
    return () => document.removeEventListener('selectionchange', update);
  }, [messageId]);

  if (!quote) return null;

  return (
    <button
      type="button"
      className="quote-action-btn"
      title="Quote selected text into composer"
      onMouseDown={e => e.preventDefault()}
      onClick={() => {
        const draft = runtime.composer.getState().text;
        runtime.composer.setText(`${draft ? draft + '\n\n' : ''}${quote.split('\n').map(line => '> ' + line).join('\n')}\n\n`);
        document.querySelector<HTMLTextAreaElement>('.composer-input')?.focus();
      }}
    >
      <Quote size={13} />
      <span>Quote selection</span>
    </button>
  );
}

