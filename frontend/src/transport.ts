import type { ChatModelAdapter } from '@assistant-ui/react';
import type { Document, Result } from './types';
import { request } from './types';

// Buffer complete SSE records, including records split across network packets.
export async function* events(response: Response) {
  const reader = response.body?.getReader();
  if (!reader) throw new Error('Streaming is unavailable. Please retry.');
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      buffer = buffer.replace(/\r\n/g, '\n');
      if (done && buffer.trim()) buffer += '\n\n';
      let boundary;
      while ((boundary = buffer.indexOf('\n\n')) >= 0) {
        const record = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
        const data = record.split('\n').filter(l => l.startsWith('data:')).map(l => l.slice(5).trimStart()).join('\n');
        if (data) yield JSON.parse(data);
      }
      if (done) break;
    }
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
}

export function createAdapter(getDocument: () => Document | undefined): ChatModelAdapter {
  return { async *run({ messages, abortSignal }) {
    const doc = getDocument();
    if (!doc) throw new Error('Attach a document or choose one from the sidebar first.');
    const users = messages.filter(m => m.role === 'user');
    const textOf = (m: typeof users[number]) => m?.content.filter(p => p.type === 'text').map(p => p.text).join('\n') || '';
    const query = textOf(users[users.length - 1]);
    const previousAnswer = messages.filter(m => m.role === 'assistant').at(-1);
    const previousDoc = previousAnswer?.metadata.custom?.document as Document | undefined;
    const history = messages
      .slice(0, -1)
      .filter(m => {
        if (m.role === 'assistant') {
          const mDoc = m.metadata?.custom?.document as Document | undefined;
          return !mDoc || mDoc.doc_id === doc.doc_id;
        }
        return true;
      })
      .slice(-6)
      .map(m => {
        const text = m.content
          .filter(p => p.type === 'text')
          .map(p => (p as { text: string }).text)
          .join('\n')
          .trim();
        return { role: m.role, content: text };
      })
      .filter(m => m.content.length > 0);
    let answer = ''; let activity = 'Finding relevant passages'; let result: Result | undefined;
    yield { content: [], metadata: { custom: { activity, document: doc } } };
    const response = await request('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, doc_id: doc.doc_id, previous_question: previousDoc?.doc_id === doc.doc_id ? textOf(users[users.length - 2]) : '', history }), signal: abortSignal });
    let completed = false;
    for await (const event of events(response)) {
      if (abortSignal.aborted) return;
      if (event.type === 'error') throw new Error(event.message);
      if (event.type === 'activity' || event.type === 'sources') activity = event.label;
      if (event.type === 'delta') answer += event.text;
      if (event.type === 'done') { result = { ...event, sources: (event.sources || []).map((source: Result['sources'][number]) => ({ ...source, doc_id: doc.doc_id })) }; answer = event.answer; completed = true; activity = ''; }
      yield { content: answer ? [{ type: 'text', text: answer }] : [], metadata: { custom: { activity, result, document: doc } } };
    }
    if (!completed && !abortSignal.aborted) throw new Error('The connection ended before the answer finished. Retry to continue.');
  } };
}
