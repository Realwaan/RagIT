import { request, RequestError } from './types';

const stageLabels: Record<string, string> = {
  receiving: 'Uploading document', starting: 'Starting processing',
  cache_lookup_ms: 'Checking saved index', extraction_ms: 'Extracting document',
  extracting_pages: 'Reading pages and image text', previews_ms: 'Preparing previews',
  document_tree_ms: 'Organizing document', chunking_ms: 'Preparing searchable passages',
  child_embeddings_ms: 'Building search index', embedding_chunks: 'Indexing passages',
  cache_write_ms: 'Saving search index', retriever_ms: 'Preparing search', saving: 'Saving document',
};

export class UploadJobError extends Error {}

function delay(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal.aborted) { reject(new DOMException('Cancelled', 'AbortError')); return; }
    const abort = () => { clearTimeout(timer); reject(new DOMException('Cancelled', 'AbortError')); };
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, ms);
    signal.addEventListener('abort', abort, { once: true });
  });
}

export async function cancelUpload(id: string) {
  await request(`/upload-jobs/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export async function uploadDocument(file: File, signal: AbortSignal, onProgress: (text: string) => void, onAccepted: (id: string) => void) {
  const form = new FormData(); form.append('file', file);
  onProgress('Uploading document…');
  const job = await (await request('/upload-jobs', { method: 'POST', body: form, signal })).json();
  if (typeof job.id !== 'string') throw new Error('The upload response was invalid. Refresh the document library before retrying.');
  onAccepted(job.id);
  return waitForUpload(job.id, signal, onProgress);
}

export async function waitForUpload(id: string, signal: AbortSignal, onProgress: (text: string) => void) {
    let failures = 0;
    while (!signal.aborted) {
      let state;
      try {
        state = await (await request(`/upload-jobs/${encodeURIComponent(id)}`, { signal })).json();
        failures = 0;
      } catch (error) {
        if (error instanceof RequestError && error.status === 404) throw new UploadJobError('This processing record has expired. Check the document library or attach the file again.');
        if (!signal.aborted && (error instanceof TypeError || (error instanceof RequestError && (error.status >= 500 || error.status === 429)))) {
          onProgress('Connection interrupted. Reconnecting to document processing…');
          await delay(Math.min(30000, 2000 * 2 ** Math.min(failures++, 4)), signal);
          continue;
        }
        throw error;
      }
      if (state.status === 'ready') return state.result;
      if (['failed', 'cancelled', 'interrupted'].includes(state.status)) throw new UploadJobError(state.message);
      const count = state.total ? ` — ${state.completed} / ${state.total}` : '';
      const elapsed = state.elapsed_seconds ? ` (${Math.floor(state.elapsed_seconds)}s)` : '';
      onProgress(`${stageLabels[state.stage] || 'Processing document'}${count}${elapsed}`);
      await delay(2000, signal);
    }
    throw new DOMException('Cancelled', 'AbortError');
}
