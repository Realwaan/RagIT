import { useEffect, useMemo, useState } from 'react';
import { ExternalLink, Focus, RotateCcw, ZoomIn, ZoomOut } from 'lucide-react';
import { request } from '../types';
import { cn, IconButton } from './ui';

function computeHighlightStyle(bbox?: number[], naturalSize?: { width: number; height: number }) {
  if (!bbox || bbox.length !== 4) return undefined;
  const [x0, y0, x1, y1] = bbox.map(Number);
  if ([x0, y0, x1, y1].some(v => Number.isNaN(v)) || x1 <= x0 || y1 <= y0) return undefined;

  // Normalized [0..1] coordinates (top-left origin)
  if (x0 >= 0 && y0 >= 0 && x1 <= 1 && y1 <= 1) {
    const left = Math.max(0, Math.min(96, x0 * 100));
    const top = Math.max(0, Math.min(96, y0 * 100));
    const width = Math.max(4, Math.min(100 - left, (x1 - x0) * 100));
    const height = Math.max(4, Math.min(100 - top, (y1 - y0) * 100));
    return { left: `${left.toFixed(2)}%`, top: `${top.toFixed(2)}%`, width: `${width.toFixed(2)}%`, height: `${height.toFixed(2)}%` };
  }

  // PDF points (bottom-left origin, rendered at scale=1.5 in get_or_render_page_image)
  const pageWidthPt = naturalSize && naturalSize.width > 100 ? naturalSize.width / 1.5 : 612;
  const pageHeightPt = naturalSize && naturalSize.height > 100 ? naturalSize.height / 1.5 : 792;
  const left = Math.max(0, Math.min(96, (x0 / pageWidthPt) * 100));
  const width = Math.max(4, Math.min(100 - left, ((x1 - x0) / pageWidthPt) * 100));
  const top = Math.max(0, Math.min(96, ((pageHeightPt - y1) / pageHeightPt) * 100));
  const height = Math.max(4, Math.min(100 - top, ((y1 - y0) / pageHeightPt) * 100));
  return { left: `${left.toFixed(2)}%`, top: `${top.toFixed(2)}%`, width: `${width.toFixed(2)}%`, height: `${height.toFixed(2)}%` };
}

export function EvidenceImage({ url, label, bbox }: { url: string; label: string; bbox?: number[] }) {
  const [zoom, setZoom] = useState(100);
  const [status, setStatus] = useState<'loading' | 'ready' | 'failed'>('loading');
  const [attempt, setAttempt] = useState(0);
  const [blobUrl, setBlobUrl] = useState('');
  const [naturalSize, setNaturalSize] = useState<{ width: number; height: number }>();
  const [showHighlight, setShowHighlight] = useState(true);
  const imageUrl = attempt ? `${url}${url.includes('?') ? '&' : '?'}retry=${attempt}` : url;
  const highlightStyle = useMemo(() => computeHighlightStyle(bbox, naturalSize), [bbox, naturalSize]);

  useEffect(() => {
    let cancelled = false;
    let objectUrl = '';
    setStatus('loading');
    request(imageUrl)
      .then(res => res.blob())
      .then(blob => {
        if (cancelled) return;
        if (!blob.size) {
          setStatus('failed');
          return;
        }
        objectUrl = URL.createObjectURL(blob);
        setBlobUrl(objectUrl);
      })
      .catch(() => {
        if (!cancelled) setStatus('failed');
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [imageUrl]);

  return <section aria-label="Evidence image" className="evidence-image">
    <div className="evidence-toolbar">
      <div className="flex flex-wrap items-center gap-1">
        <IconButton label="Zoom out" disabled={zoom <= 100 || status !== 'ready'} onClick={() => setZoom(z => z - 25)}><ZoomOut size={17}/></IconButton>
        <span className="text-xs tabular-nums" aria-live="polite">{zoom}%</span>
        <IconButton label="Zoom in" disabled={zoom >= 300 || status !== 'ready'} onClick={() => setZoom(z => z + 25)}><ZoomIn size={17}/></IconButton>
        <button className="text-xs px-2 py-1" disabled={zoom === 100} onClick={() => setZoom(100)}>Fit</button>
        {highlightStyle && (
          <button
            type="button"
            className={cn('highlight-toggle text-xs px-2 py-1', showHighlight && 'selected')}
            aria-pressed={showHighlight}
            onClick={() => setShowHighlight(v => !v)}
          >
            <Focus size={13}/>
            <span>Highlight region</span>
          </button>
        )}
      </div>
      <a href={url} target="_blank" rel="noreferrer" className="evidence-link">Open original <ExternalLink size={14}/><span className="sr-only"> in a new tab</span></a>
    </div>
    {status === 'failed' ? <div className="evidence-error" role="alert">
      <p>This image could not load. Retry to request it again.</p>
      <button className="secondary" onClick={() => { setStatus('loading'); setAttempt(n => n + 1); }}><RotateCcw size={14}/> Retry image</button>
    </div> : <>
      {status === 'loading' && <div className="evidence-skeleton" role="status">Loading source image...</div>}
      <div className="evidence-canvas" tabIndex={0} aria-label={`${label}. Scroll to inspect when zoomed.`} hidden={status !== 'ready'}>
        {blobUrl && (
          <div className="evidence-stage" style={{ width: `${zoom}%` }}>
            <img
              key={imageUrl}
              src={blobUrl}
              alt={label}
              style={{ width: '100%' }}
              onLoad={e => {
                const img = e.currentTarget;
                setNaturalSize({ width: img.naturalWidth, height: img.naturalHeight });
                setStatus('ready');
              }}
              onError={() => setStatus('failed')}
            />
            {status === 'ready' && showHighlight && highlightStyle && (
              <div
                className="evidence-bbox"
                data-testid="evidence-bbox"
                role="region"
                aria-label="Cited evidence region"
                style={highlightStyle}
              />
            )}
          </div>
        )}
      </div>
    </>}
  </section>;
}
