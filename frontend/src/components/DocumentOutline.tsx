import { useEffect, useState } from 'react';
import { request, type Document } from '../types';

type Node = { parent_id?: string; id: string; type: string; title: string; text: string; page: number };
export function DocumentOutline({ document, page, onPage }: { document: Document; page: number; onPage: (page: number) => void }) {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [section, setSection] = useState<Node>();
  const pdf = /\.pdf$/i.test(document.filename);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(''); setNodes([]); setSection(undefined);
    request(`/api/ast/${encodeURIComponent(document.doc_id)}`, { signal: controller.signal })
      .then(response => response.json()).then(data => { if (!controller.signal.aborted) setNodes(Object.values(data.nodes || {})); })
      .catch(() => { if (!controller.signal.aborted) setError('Document outline could not be loaded.'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [document.doc_id, attempt]);
  const headings = nodes.filter(node => node.type === 'section' && node.title && Number.isInteger(node.page) && node.page > 0).sort((a, b) => a.page - b.page);
  const belongsToSection = (node: Node) => {
    const visited = new Set<string>();
    let parent = node.parent_id;
    while (parent && !visited.has(parent)) {
      if (parent === section?.id) return true;
      visited.add(parent); parent = nodes.find(item => item.id === parent)?.parent_id;
    }
    return false;
  };
  return <details className="document-outline" open><summary>Document outline</summary>
    {loading && <p role="status">Loading headings...</p>}
    {error && <p role="alert">{error} <button className="secondary" onClick={() => setAttempt(n => n + 1)}>Retry outline</button></p>}
    {!loading && !error && !headings.length && <p className="muted">No headings detected.{pdf ? ' Use the page controls to browse.' : ''}</p>}
    <nav aria-label="Document headings">{headings.map(node => <button key={node.id} aria-current={section?.id === node.id ? 'location' : undefined} onClick={() => { setSection(node); if (pdf) onPage(Math.min(node.page, document.pages || node.page)); }}><span>{node.title}</span><small>Page {node.page}</small></button>)}</nav>
    {section && !pdf && <section aria-label="Selected section"><h4>{section.title}</h4><p className="outline-excerpt">{nodes.filter(node => node.type === 'paragraph' && belongsToSection(node)).map(node => node.text).join('\n\n') || section.text || 'No text available for this section.'}</p></section>}
    {pdf && <p className="muted text-xs">Previewing page {page}</p>}
  </details>;
}
