import { useEffect, useState } from 'react';
import { ExternalLink, RotateCcw, ZoomIn, ZoomOut } from 'lucide-react';
import { request } from '../types';
import { IconButton } from './ui';

export function EvidenceImage({ url, label }: { url: string; label: string }) {
  const [zoom, setZoom] = useState(100);
  const [status, setStatus] = useState<'loading' | 'ready' | 'failed'>('loading');
  const [attempt, setAttempt] = useState(0);
  const [blobUrl, setBlobUrl] = useState('');
  const imageUrl = attempt ? `${url}${url.includes('?') ? '&' : '?'}retry=${attempt}` : url;

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
      <div className="flex items-center gap-1">
        <IconButton label="Zoom out" disabled={zoom <= 100 || status !== 'ready'} onClick={() => setZoom(z => z - 25)}><ZoomOut size={17}/></IconButton>
        <span className="text-xs tabular-nums" aria-live="polite">{zoom}%</span>
        <IconButton label="Zoom in" disabled={zoom >= 300 || status !== 'ready'} onClick={() => setZoom(z => z + 25)}><ZoomIn size={17}/></IconButton>
        <button className="text-xs px-2 py-1" disabled={zoom === 100} onClick={() => setZoom(100)}>Fit</button>
      </div>
      <a href={url} target="_blank" rel="noreferrer" className="evidence-link">Open original <ExternalLink size={14}/><span className="sr-only"> in a new tab</span></a>
    </div>
    {status === 'failed' ? <div className="evidence-error" role="alert">
      <p>This image could not load. Retry to request it again.</p>
      <button className="secondary" onClick={() => { setStatus('loading'); setAttempt(n => n + 1); }}><RotateCcw size={14}/> Retry image</button>
    </div> : <>
      {status === 'loading' && <div className="evidence-skeleton" role="status">Loading source image...</div>}
      <div className="evidence-canvas" tabIndex={0} aria-label={`${label}. Scroll to inspect when zoomed.`} hidden={status !== 'ready'}>
        {blobUrl && <img key={imageUrl} src={blobUrl} alt={label} style={{ width: `${zoom}%` }} onLoad={() => setStatus('ready')} onError={() => setStatus('failed')}/>}
      </div>
    </>}
  </section>;
}
