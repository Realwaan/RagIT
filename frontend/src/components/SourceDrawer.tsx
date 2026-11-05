import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { BookOpen, X, ImageIcon, ChevronLeft, ChevronRight, Columns } from 'lucide-react';
import type { Source } from '../types';
import { EvidenceImage } from './EvidenceImage';
import { cn } from './ui';

// Evidence is served by this application; do not turn source text into arbitrary links.
function localImage(url?: string) {
  return url && /^\/(?:api\/(?:crop|preview)\/|static\/)/.test(url) && !url.includes('\\') ? url : undefined;
}

export function Evidence({ source, onToggleDock, isDocked }: { source: Source; onToggleDock?: () => void; isDocked?: boolean }) {
  const [selected, setSelected] = useState(0);
  const [fullPage, setFullPage] = useState(false);
  const [currentPage, setCurrentPage] = useState(source.page || 1);

  const primaryVisual = source.linked_visuals?.find(v => v.image_url === source.image_url);
  const visuals = [
    ...(localImage(source.image_url) ? [{ url: source.image_url!, title: primaryVisual?.title || source.caption || 'Cited image', page: primaryVisual?.page ?? source.page, bbox: primaryVisual?.bbox || source.bbox }] : []),
    ...(source.linked_visuals || []).filter(v => localImage(v.image_url) && v.image_url !== source.image_url)
      .map(v => ({ url: v.image_url!, title: v.title, page: v.page, bbox: v.bbox })),
  ];
  const visual = visuals[selected];
  const docId = source.doc_id || visual?.url.match(/^\/api\/crop\/([^/]+)\//)?.[1];
  
  // High-precision page preview URL
  const isPreviewable = /\.(pdf|png|jpe?g|webp|tiff)$/i.test(source.filename);
  const activePage = (fullPage || !visual) ? currentPage : (visual.page ?? currentPage);
  const pageUrl = docId && activePage && isPreviewable ? `/api/preview/${encodeURIComponent(docId)}/${activePage}` : undefined;
  const url = (fullPage || !visual) && pageUrl ? pageUrl : visual?.url;
  const activeBbox = (fullPage || !visual) && activePage === source.page ? (source.bbox || visual?.bbox) : (visual ? visual.bbox : undefined);
  const interpreted = source.evidence_origin === 'ai_interpretation';

  return (
    <>
      <div className="flex items-center justify-between">
        <Dialog.Description className="muted break-words">{source.filename} · Page {activePage}</Dialog.Description>
        {onToggleDock && (
          <button type="button" className="dock-toggle-btn" onClick={onToggleDock} title={isDocked ? "Open as overlay drawer" : "Dock side-by-side"}>
            <Columns size={14}/>
            <span>{isDocked ? "Undock" : "Dock side-by-side"}</span>
          </button>
        )}
      </div>

      {source.evidence_origin && (
        <p className="evidence-origin">
          {interpreted ? 'AI interpretation of the image' : 'Extracted document text'}
          {source.verification_status === 'model_checked' && ' / Checked against the original image'}
        </p>
      )}

      {source.caption && <h3 className="evidence-caption">{source.caption}</h3>}

      {visuals.length > 1 && (
        <div className="evidence-choices" aria-label="Choose visual evidence">
          {visuals.map((item, index) => (
            <button
              key={item.url}
              aria-pressed={index === selected}
              className={cn('evidence-choice', index === selected && 'selected')}
              onClick={() => { setSelected(index); setFullPage(false); }}
            >
              <ImageIcon size={15}/>
              <span>{item.title}{item.page && ` · Page ${item.page}`}</span>
            </button>
          ))}
        </div>
      )}

      <div className="evidence-view-options">
        <span className="muted text-xs">
          {visual && !fullPage ? (visual.page ? `Crop on Page ${visual.page}` : 'Linked visual') : `Document Page ${activePage}`}
          {source.crop_scope === 'full_page' && ' · Full-page evidence'}
        </span>
        <div className="flex gap-1" aria-label="Evidence view">
          {visuals.length > 0 && pageUrl && (
            <>
              <button className={cn('view-option', !fullPage && 'selected')} aria-pressed={!fullPage} onClick={() => setFullPage(false)}>Image crop</button>
              <button className={cn('view-option', fullPage && 'selected')} aria-pressed={fullPage} onClick={() => setFullPage(true)}>Full page</button>
            </>
          )}
        </div>
      </div>

      {pageUrl && (fullPage || visuals.length === 0) && (
        <div className="page-nav-bar">
          <button
            type="button"
            className="page-nav-btn"
            disabled={currentPage <= 1}
            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
          >
            <ChevronLeft size={14}/> Prev Page
          </button>
          <span className="font-medium text-xs">Page {currentPage}</span>
          <button
            type="button"
            className="page-nav-btn"
            onClick={() => setCurrentPage(p => p + 1)}
          >
            Next Page <ChevronRight size={14}/>
          </button>
        </div>
      )}

      {url && (
        <EvidenceImage
          key={url}
          url={url}
          label={`${source.filename}, page ${activePage}`}
          bbox={activeBbox}
        />
      )}

      {!url && !visuals.length && source.visual_id && (
        <p className="evidence-empty">The image preview is unavailable. Reattach the original document to restore it.</p>
      )}

      <h3 className="evidence-caption">{interpreted ? 'Supported observations' : 'Source excerpt'}</h3>
      <div className="source-quote">{source.parent_text || 'No text excerpt is available for this source.'}</div>
      {interpreted && <p className="muted text-sm text-pretty">Compare the observations with the original image. An AI check can still miss details.</p>}
    </>
  );
}

export function SourceDrawer({
  source,
  onClose,
  isDocked,
  onToggleDock,
}: {
  source?: Source;
  onClose: () => void;
  isDocked?: boolean;
  onToggleDock?: () => void;
}) {
  if (isDocked && source) {
    return (
      <aside className="docked-viewer" aria-label="Interactive Document Viewer">
        <div className="drawer-heading">
          <div className="flex items-center gap-2">
            <BookOpen size={18}/>
            <span className="font-semibold text-sm">Interactive Viewer</span>
          </div>
          <div className="flex items-center gap-1">
            {onToggleDock && (
              <button type="button" className="icon-button" onClick={onToggleDock} title="Undock to drawer">
                <Columns size={16}/>
              </button>
            )}
            <button type="button" className="icon-button" aria-label="Close viewer" onClick={onClose}>
              <X size={18}/>
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          <Evidence
            key={`${source.filename}:${source.page}:${source.citation_id}:${source.image_url || ''}`}
            source={source}
            isDocked={isDocked}
            onToggleDock={onToggleDock}
          />
        </div>
      </aside>
    );
  }

  return (
    <Dialog.Root open={!!source} onOpenChange={open => { if (!open) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="overlay"/>
        <Dialog.Content className="source-drawer">
          <div className="drawer-heading">
            <BookOpen size={20}/>
            <Dialog.Title>Source evidence</Dialog.Title>
            <div className="flex items-center gap-1">
              {onToggleDock && (
                <button type="button" className="icon-button" onClick={onToggleDock} title="Dock side-by-side">
                  <Columns size={16}/>
                </button>
              )}
              <Dialog.Close className="icon-button" aria-label="Close source">
                <X size={20}/>
              </Dialog.Close>
            </div>
          </div>
          {source && (
            <Evidence
              key={`${source.filename}:${source.page}:${source.citation_id}:${source.image_url || ''}`}
              source={source}
              isDocked={isDocked}
              onToggleDock={onToggleDock}
            />
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
