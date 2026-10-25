import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { Pencil } from 'lucide-react';
import type { Session } from '../types';
import { IconButton } from './ui';

export function RenameConversationDialog({ session, disabled, onSave }: { session: Session; disabled: boolean; onSave: (title: string) => void }) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState(session.title);
  return <Dialog.Root open={open} onOpenChange={value => { if (value) setTitle(session.title); setOpen(value); }}>
    <Dialog.Trigger asChild><IconButton label={`Rename ${session.title}`} disabled={disabled}><Pencil size={14}/></IconButton></Dialog.Trigger>
    <Dialog.Portal>
    <Dialog.Overlay className="overlay"/><Dialog.Content className="confirm-dialog">
      <Dialog.Title>Rename conversation</Dialog.Title>
      <Dialog.Description>Choose a name you can find again.</Dialog.Description>
      <form onSubmit={event => { event.preventDefault(); if (title.trim()) { onSave(title.trim()); setOpen(false); } }}>
        <label className="field-label" htmlFor="conversation-title">Conversation name</label>
        <input id="conversation-title" className="text-field" maxLength={80} value={title} onChange={event => setTitle(event.target.value)} autoFocus/>
        <div className="flex justify-end gap-2 mt-6"><Dialog.Close className="secondary" type="button">Cancel</Dialog.Close><button className="primary" disabled={!title.trim()}>Save name</button></div>
      </form>
    </Dialog.Content>
  </Dialog.Portal></Dialog.Root>;
}
