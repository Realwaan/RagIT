import { createContext, useContext } from 'react';
import { MarkdownTextPrimitive, type CodeHeaderProps } from '@assistant-ui/react-markdown';
import { useMessagePartText } from '@assistant-ui/react';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Copy, Check } from 'lucide-react';
import { useState } from 'react';
import type { Source } from './types';
import 'katex/dist/katex.min.css';

export const EvidenceContext = createContext<{ sources: Source[]; open: (s: Source) => void }>({ sources: [], open: () => {} });

// Transform text nodes only. Code, links and raw HTML never become citations.
function citations() {
  return (tree: any) => {
    const visit = (node: any) => {
      if (!node.children || ['link', 'code', 'inlineCode', 'html'].includes(node.type)) return;
      node.children = node.children.flatMap((child: any) => {
        if (child.type !== 'text') { visit(child); return [child]; }
        return child.value.split(/(\[\d+\])/g).filter(Boolean).map((value: string) => /^\[\d+\]$/.test(value)
          ? { type: 'link', url: `#source-${value.slice(1, -1)}`, children: [{ type: 'text', value }] }
          : { type: 'text', value });
      });
    };
    visit(tree);
  };
}

function Link({ href, children }: any) {
  const evidence = useContext(EvidenceContext);
  if (href?.startsWith('#source-')) {
    const source = evidence.sources.find(s => s.citation_id === Number(href.slice(8)));
    return <button className="citation" disabled={!source} onClick={() => source && evidence.open(source)} aria-label={`View source ${href.slice(8)}`}>{children}</button>;
  }
  return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
}

function CodeHeader({ language, code }: CodeHeaderProps) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(false);
  return <div className="code-header"><span>{language || 'Code'}</span><button aria-label="Copy code" onClick={async () => {
    try { await navigator.clipboard.writeText(code); setCopied(true); setTimeout(() => setCopied(false), 2000); }
    catch { setError(true); }
  }}>{copied ? <Check size={14} /> : <Copy size={14} />}{error ? 'Select text to copy' : copied ? 'Copied' : 'Copy code'}</button></div>;
}

const components = { a: Link, CodeHeader, table: ({ children }: any) => <div className="table-scroll" role="region" aria-label="Comparison table" tabIndex={0}><table>{children}</table></div> };
const plugins = [remarkGfm, remarkMath, citations];
const rehypePlugins = [rehypeKatex];
const beforeSources = (text: string) => text.split(/\n### Source excerpts\s*\n/)[0];
const onlySources = (text: string) => text.split(/\n### Source excerpts\s*\n/).slice(1).join('\n');

export function Markdown() {
  const { text } = useMessagePartText();
  const hasEvidence = /\n### Source excerpts\s*\n/.test(text);
  return <><MarkdownTextPrimitive className="markdown" smooth={false} remarkPlugins={plugins} rehypePlugins={rehypePlugins} components={components} preprocess={beforeSources} />
    {hasEvidence && <details className="disclosure"><summary>Full source excerpts</summary><MarkdownTextPrimitive className="markdown" smooth={false} remarkPlugins={plugins} rehypePlugins={rehypePlugins} components={components} preprocess={onlySources} /></details>}
  </>;
}
