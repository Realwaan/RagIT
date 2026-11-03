import type { Session } from './types';

export function conversationMatch(session: Session, query: string): string | undefined {
  const needle = query.trim().toLowerCase();
  if (!needle || session.title.toLowerCase().includes(needle)) return '';
  const repository = session.repository as { messages?: { message?: { content?: { type?: string; text?: string }[] } }[] } | undefined;
  if (!Array.isArray(repository?.messages)) return undefined;
  for (const item of repository.messages) {
    if (!Array.isArray(item?.message?.content)) continue;
    for (const part of item.message.content) {
      if (part.type !== 'text' || typeof part.text !== 'string') continue;
      const at = part.text.toLowerCase().indexOf(needle);
      if (at >= 0) return `${at > 40 ? '…' : ''}${part.text.slice(Math.max(0, at - 40), at + needle.length + 80)}`;
    }
  }
  return undefined;
}

export function conversationGroup(session: Session, now = new Date()): string {
  if (session.pinned) return 'Pinned';
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today); yesterday.setDate(yesterday.getDate() - 1);
  const week = new Date(today); week.setDate(week.getDate() - 7);
  if (session.updated >= today.getTime()) return 'Today';
  if (session.updated >= yesterday.getTime()) return 'Yesterday';
  if (session.updated >= week.getTime()) return 'Previous 7 days';
  return 'Older';
}
