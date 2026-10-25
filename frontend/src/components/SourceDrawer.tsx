import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { BookOpen, X, ImageIcon } from 'lucide-react';
import type { Source } from '../types';
import { EvidenceImage } from './EvidenceImage';
import { cn } from './ui';

// Evidence is served by this application; do not turn source text into arbitrary links.
function localImage(url?: string) {
  return url && /^\/(?:api\/(?:crop|preview)\/|static\/)/.test(url) && !url.includes('\\') ? url : undefined;
}

function Evidence({ source }: { source: Source }) {
  const [selected, setSelected] = useState(0);
  const [fullPage, setFullPage] = useState(false);
  const primaryVisual = source.linked_visuals?.find(v => v.image_url === source.image_url);
  const visuals = [
    ...(localImage(source.image_url) ? [{ url: source.image_url!, title: primaryVisual?.title || source.caption || 'Cited image', page: primaryVisual?.page ?? source.page }] : []),
    ...(source.linked_visuals || []).filter(v => localImage(v.image_url) && v.image_url !== source.image_url)
      .map(v => ({ url: v.image_url!, title: v.title, page: v.page })),
  ];
  const visual = visuals[selected];
  const docId = source.doc_id || visual?.url.match(/^\/api\/crop\/([^/]+)\//)?.[1];
  const pageUrl = docId && visual?.page && /\.pdf$/i.test(source.filename) ? `/api/preview/${encodeURIComponent(docId)}/${visual.page}` : undefined;
  const url = fullPage && pageUrl ? pageUrl : visual?.url;
  const interpreted = source.evidence_origin === 'ai_interpretation';
  return <>
    <Dialog.Description className="muted break-words">{source.filename} · Page {source.page}</Dialog.Description>
    {source.evidence_origin && <p className="evidence-origin">
      {interpreted ? 'AI interpretation of the image' : 'Extracted document text'}
      {source.verification_status === 'model_checked' && ' / Checked against the original image'}
    </p>}
    {source.caption && <h3 className="evidence-caption">{source.caption}</h3>}
    {!!visuals.length && <>
      {visuals.length > 1 && <div className="evidence-choices" aria-label="Choose visual evidence">
        {visuals.map((item, index) => <button key={item.url} aria-pressed={index === selected} className={cn('evidence-choice', index === selected && 'selected')}
          onClick={() => { setSelected(index); setFullPage(false); }}><ImageIcon size={15}/><span>{item.title}{item.page && ` · Page ${item.page}`}</span></button>)}
      </div>}
      <div className="evidence-view-options">
        <span className="muted text-xs">{visual.page ? `Page ${visual.page}` : 'Linked visual'}{source.crop_scope === 'full_page' && ' · Full-page evidence'}</span>
        {pageUrl && <div className="flex gap-1" aria-label="Evidence view">
          <button className={cn('view-option', !fullPage && 'selected')} aria-pressed={!fullPage} onClick={() => setFullPage(false)}>Image crop</button>
          <button className={cn('view-option', fullPage && 'selected')} aria-pressed={fullPage} onClick={() => setFullPage(true)}>Full page</button>
        </div>}
      </div>
      {url && <EvidenceImage key={url} url={url} label={`${visual.title}${visual.page ? `, page ${visual.page}` : ''}`}/>}
    </>}
    {!visuals.length && source.visual_id && <p className="evidence-empty">The image preview is unavailable. Reattach the original document to restore it.</p>}
    <h3 className="evidence-caption">{interpreted ? 'Supported observations' : 'Source excerpt'}</h3>
    <div className="source-quote">{source.parent_text || 'No text excerpt is available for this source.'}</div>
    {interpreted && <p className="muted text-sm text-pretty">Compare the observations with the original image. An AI check can still miss details.</p>}
  </>;
}

export function SourceDrawer({ source, onClose }: { source?: Source; onClose: () => void }) {
  return <Dialog.Root open={!!source} onOpenChange={open => { if (!open) onClose(); }}><Dialog.Portal>
    <Dialog.Overlay className="overlay"/><Dialog.Content className="source-drawer">
      <div className="drawer-heading"><BookOpen size={20}/><Dialog.Title>Source evidence</Dialog.Title>
        <Dialog.Close className="icon-button" aria-label="Close source"><X size={20}/></Dialog.Close></div>
      {source && <Evidence key={`${source.filename}:${source.page}:${source.citation_id}:${source.image_url || ''}`} source={source}/>}
    </Dialog.Content>
  </Dialog.Portal></Dialog.Root>;
}
