import { useEffect, useState } from 'react';
import { request, type VisualProgress as Progress } from '../types';

export function VisualProgress({ docId }: { docId?: string }) {
  const [progress, setProgress] = useState<Progress>();
  useEffect(() => {
    setProgress(undefined);
    if (!docId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const data = await (await request('/vault')).json();
        if (cancelled) return;
        const next = data.vault.find((doc: {doc_id: string}) => doc.doc_id === docId)?.visual_analysis;
        setProgress(next);
        if (next && ['queued', 'analyzing'].includes(next.status)) timer = setTimeout(poll, 3000);
      } catch { if (!cancelled) timer = setTimeout(poll, 10000); }
    };
    poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [docId]);
  if (!progress?.total) return null;
  const text = progress.status === 'unavailable' ? 'Image interpretation unavailable. Extracted text is searchable.'
    : progress.status === 'ready' ? `${progress.completed} visuals searchable`
    : progress.status === 'partial' ? `${progress.completed} visuals searchable; ${progress.failed} could not be analyzed. Reattach to retry.`
    : `Analyzing visuals: ${progress.completed + progress.failed} of ${progress.total}. Text search is ready.`;
  const analyzing = ['queued', 'analyzing'].includes(progress.status);
  return <div className="visual-progress" role="status">{analyzing && <progress aria-label="Visual analysis progress" max={progress.total} value={progress.completed + progress.failed}/>}<span>{text}</span></div>;
}
