import { useEffect, useRef, useState } from 'react';
import { request, type Document, type VisualProgress as Progress } from '../types';

export function VisualProgress({
  docId,
  onVaultUpdate,
}: {
  docId?: string;
  onVaultUpdate?: (vault: Document[]) => void;
}) {
  const [progress, setProgress] = useState<Progress>();
  const onVaultUpdateRef = useRef(onVaultUpdate);
  onVaultUpdateRef.current = onVaultUpdate;

  useEffect(() => {
    setProgress(undefined);
    if (!docId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const data = await (await request('/vault')).json();
        if (cancelled) return;
        const vault = Array.isArray(data.vault) ? (data.vault as Document[]) : [];
        onVaultUpdateRef.current?.(vault);
        const next = vault.find(doc => doc.doc_id === docId)?.visual_analysis;
        setProgress(next);
        if (next && ['queued', 'analyzing'].includes(next.status)) {
          timer = setTimeout(poll, 3000);
        }
      } catch {
        if (!cancelled) timer = setTimeout(poll, 10000);
      }
    };
    void poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [docId]);

  if (!progress?.total) return null;
  const text =
    progress.status === 'unavailable'
      ? 'Image interpretation unavailable. Extracted text is searchable.'
      : progress.status === 'ready'
      ? `${progress.completed} visuals searchable`
      : progress.status === 'partial'
      ? `${progress.completed} visuals searchable; ${progress.failed} could not be analyzed. Reattach to retry.`
      : `Analyzing visuals: ${progress.completed + progress.failed} of ${progress.total}. Text search is ready.`;
  const analyzing = ['queued', 'analyzing'].includes(progress.status);
  return (
    <div className="visual-progress" role="status">
      {analyzing && (
        <progress
          aria-label="Visual analysis progress"
          max={progress.total}
          value={progress.completed + progress.failed}
        />
      )}
      <span>{text}</span>
    </div>
  );
}
