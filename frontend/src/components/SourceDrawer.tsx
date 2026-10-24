import * as Dialog from '@radix-ui/react-dialog';
import { BookOpen, X } from 'lucide-react';
import type { Source } from '../types';

export function SourceDrawer({ source, onClose }: { source?: Source; onClose: () => void }) {
  return (

    <Dialog.Root open={!!source} onOpenChange={open => { if (!open) onClose(); }}><Dialog.Portal><Dialog.Overlay className="overlay"/><Dialog.Content className="source-drawer"><div className="drawer-heading"><BookOpen size={20}/><Dialog.Title>Source evidence</Dialog.Title><Dialog.Close className="icon-button" aria-label="Close source"><X size={20}/></Dialog.Close></div><Dialog.Description className="muted">{source?.filename} · Page {source?.page}</Dialog.Description><div className="source-quote">{source?.parent_text}</div>{source?.image_url && <a href={source.image_url} target="_blank" rel="noreferrer"><img src={source.image_url} alt={`Document evidence, page ${source.page}`} /></a>}{source?.linked_visuals?.filter(v => v.image_url && v.image_url !== source.image_url).map((visual, i) => <figure key={i}><img src={visual.image_url} alt={visual.title}/><figcaption>{visual.title}</figcaption></figure>)}</Dialog.Content></Dialog.Portal></Dialog.Root>
  );
}
