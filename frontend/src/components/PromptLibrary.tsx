import { useRef, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { useAui } from '@assistant-ui/react';

const prompts = [
  ['Summarize', 'Summarize the key points, obligations, and exceptions in this document. Cite the supporting passages.'],
  ['Extract deadlines', 'List every deadline, responsible party, and associated obligation in a table. Cite each entry and flag missing dates.'],
  ['Compare claims', 'Identify conflicting claims or figures in this document. Compare the passages side by side and cite each source.'],
  ['Check requirements', 'Create a checklist of requirements in this document, with conditions, exceptions, and source citations.'],
  ['Prepare a report', 'Write a structured report covering the document’s purpose, main findings, requirements, risks, and open questions. Cite evidence and clearly identify missing information.'],
];
export function PromptLibrary({ disabled }: { disabled: boolean }) {
  const aui = useAui();
  const inserted = useRef(false);
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const filtered = prompts.filter(p => p.join(' ').toLowerCase().includes(search.toLowerCase()));
  return <Dialog.Root open={open} onOpenChange={setOpen}><Dialog.Trigger className="secondary" disabled={disabled}>Prompts</Dialog.Trigger><Dialog.Portal><Dialog.Overlay className="overlay"/><Dialog.Content className="confirm-dialog prompt-dialog" onCloseAutoFocus={event => { if (inserted.current) { event.preventDefault(); inserted.current = false; document.querySelector<HTMLTextAreaElement>('.composer-input')?.focus(); } }}><Dialog.Title>Prompt library</Dialog.Title><Dialog.Description>Choose a task, then edit the prompt before sending. Your current draft is kept.</Dialog.Description><input className="text-field" aria-label="Search prompts" placeholder="Search tasks" value={search} onChange={e => setSearch(e.target.value)}/><div className="prompt-list">{filtered.map(([title, prompt]) => <button className="prompt-card" key={title} onClick={() => { const draft = aui.composer.getState().text; aui.composer.setText(`${draft ? draft + '\n\n' : ''}${prompt}`); inserted.current = true; setOpen(false); }}><strong>{title}</strong><span>{prompt}</span></button>)}{!filtered.length && <p role="status">No matching prompts.</p>}</div><Dialog.Close className="secondary">Close</Dialog.Close></Dialog.Content></Dialog.Portal></Dialog.Root>;
}
