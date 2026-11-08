import { useEffect, useRef, useState } from 'react';
import { useAui, useAuiState } from '@assistant-ui/react';
import { Search, Quote, X, ChevronUp, ChevronDown } from 'lucide-react';

export function ActivityStatus({ label }: { label: string }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => { const start = Date.now(); const timer = setInterval(() => setSeconds(Math.floor((Date.now() - start) / 1000)), 1000); return () => clearInterval(timer); }, []);
  return <div className="activity"><span role="status">{label}</span><span className="muted" aria-label="Elapsed time"> · {seconds}s</span><progress aria-label="Processing" /></div>;
}

export function ConversationSearch() {
  const messages = useAuiState(s => s.thread.messages);
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const trimmed = query.trim().toLowerCase();
  const matches = trimmed
    ? messages.filter(m => m.content.some(p => p.type === 'text' && p.text.toLowerCase().includes(trimmed)))
    : [];

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
        const activeTag = document.activeElement?.tagName.toLowerCase();
        if (activeTag !== 'textarea') {
          e.preventDefault();
          setOpen(true);
          setTimeout(() => inputRef.current?.focus(), 50);
        }
      }
      if (e.key === 'Escape' && open) {
        setOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open]);

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  const scrollToMatch = (idx: number) => {
    if (!matches[idx]) return;
    const target = document.getElementById(`message-${matches[idx].id}`);
    target?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    target?.focus({ preventScroll: true });
  };

  const nextMatch = () => {
    if (!matches.length) return;
    const next = (activeIndex + 1) % matches.length;
    setActiveIndex(next);
    scrollToMatch(next);
  };

  const prevMatch = () => {
    if (!matches.length) return;
    const prev = (activeIndex - 1 + matches.length) % matches.length;
    setActiveIndex(prev);
    scrollToMatch(prev);
  };

  if (messages.length <= 1) return null;

  if (!open) {
    return (
      <div className="conversation-search-float">
        <button
          type="button"
          className="conversation-search-pill-btn"
          onClick={() => setOpen(true)}
          title="Find in conversation (Ctrl+F)"
          aria-label="Find in conversation"
        >
          <Search size={13} />
          <span>Find in conversation</span>
        </button>
      </div>
    );
  }

  return (
    <div className="conversation-search-float" role="search" aria-label="Find in conversation">
      <div className="conversation-search-bar">
        <Search size={13} className="search-bar-icon" />
        <input
          ref={inputRef}
          type="text"
          placeholder="Find in conversation…"
          value={query}
          onChange={e => {
            const next = e.target.value;
            setQuery(next);
            setActiveIndex(0);
            if (next.trim()) {
              const nextMatches = messages.filter(m => m.content.some(p => p.type === 'text' && p.text.toLowerCase().includes(next.trim().toLowerCase())));
              if (nextMatches.length > 0) {
                const target = document.getElementById(`message-${nextMatches[0].id}`);
                target?.scrollIntoView({ block: 'center', behavior: 'smooth' });
              }
            }
          }}
          onKeyDown={e => {
            if (e.key === 'Enter') {
              e.preventDefault();
              if (e.shiftKey) prevMatch();
              else nextMatch();
            } else if (e.key === 'Escape') {
              setOpen(false);
            }
          }}
          aria-label="Find in conversation"
        />
        {query.trim() && (
          <span className="search-match-badge" role="status">
            {matches.length > 0 ? `${activeIndex + 1} of ${matches.length}` : '0 of 0'}
          </span>
        )}
        {matches.length > 1 && (
          <div className="search-nav-arrows">
            <button type="button" className="search-arrow-btn" onClick={prevMatch} aria-label="Previous match" title="Previous match">
              <ChevronUp size={13} />
            </button>
            <button type="button" className="search-arrow-btn" onClick={nextMatch} aria-label="Next match" title="Next match">
              <ChevronDown size={13} />
            </button>
          </div>
        )}
        <button
          type="button"
          className="search-close-btn"
          onClick={() => { setOpen(false); setQuery(''); }}
          aria-label="Close search"
          title="Close search"
        >
          <X size={13} />
        </button>
      </div>
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
