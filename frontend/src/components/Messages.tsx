import { useContext, useState } from 'react';
import { ThreadPrimitive, MessagePrimitive, ActionBarPrimitive, BranchPickerPrimitive, ErrorPrimitive, useAuiState } from '@assistant-ui/react';
import * as Dropdown from '@radix-ui/react-dropdown-menu';
import { Sparkles, BookOpen, Check, ChevronDown, ChevronLeft, ChevronRight, Copy, Download, Pencil, RefreshCw, ThumbsDown, ThumbsUp, Volume2, VolumeX } from 'lucide-react';
import { Markdown, EvidenceContext } from '../Markdown';
import { request, type Result } from '../types';
import { Attachment } from './Attachment';
import { UIContext } from './AssistantContext';
import { cn, Tip } from './ui';

function Branches() { return <BranchPickerPrimitive.Root hideWhenSingleBranch className="branches"><BranchPickerPrimitive.Previous className="icon-button" aria-label="Previous response version"><ChevronLeft size={14}/></BranchPickerPrimitive.Previous><BranchPickerPrimitive.Number/> / <BranchPickerPrimitive.Count/><BranchPickerPrimitive.Next className="icon-button" aria-label="Next response version"><ChevronRight size={14}/></BranchPickerPrimitive.Next></BranchPickerPrimitive.Root>; }
export function UserMessage() { return <MessagePrimitive.Root className="user-message"><div className="user-bubble"><MessagePrimitive.Attachments components={{ Attachment }}/><MessagePrimitive.Content/></div><div className="user-actions"><ActionBarPrimitive.Edit className="icon-button" aria-label="Edit message"><Pencil size={14}/></ActionBarPrimitive.Edit><Branches/></div></MessagePrimitive.Root>; }
export function AssistantMessage() {
  const message = useAuiState(s => s.message);
  const { openSource } = useContext(UIContext);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState('');
  const result = message.metadata.custom?.result as Result | undefined;
  const running = message.status?.type === 'running';
  const stopped = message.status?.type === 'incomplete' && message.status.reason === 'cancelled';
  const activity = message.metadata.custom?.activity as string | undefined;
  const speaking = message.speech != null;
  const sources = result?.sources || [];
  const exportReport = async (format: string) => { if (!result || exporting) return; setExporting(true); setExportError(''); try {
    const response = await request('/export-report', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...result, format }) });
    const url = URL.createObjectURL(await response.blob()); const a = document.createElement('a'); a.href = url; a.download = `ragit-answer.${format}`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) { setExportError((e as Error).message); } finally { setExporting(false); } };
  return <MessagePrimitive.Root className="assistant-message"><div className="assistant-label"><span className="logo small"><Sparkles size={14}/></span><strong>RagIT</strong>{result && <span className={cn('answer-status', result.status === 'REFUSE' && 'unverified')}>{result.status === 'REFUSE' ? 'Answer not verified' : 'Document-based answer'}</span>}</div>
    {running && <p className="activity" role="status">{activity || 'Preparing answer…'}</p>}
    <EvidenceContext.Provider value={{ sources, open: openSource }}><MessagePrimitive.Content components={{ Text: Markdown }}/></EvidenceContext.Provider>
    {result?.evaluation?.claim_support === 'needs_review' && <details className="source-list"><summary>Some claims need source review</summary><p>Citation links identify passages; they do not establish that every claim is supported.</p>{result.evaluation.claims?.filter(c => c.status !== 'supported').map((claim, i) => <p key={i}><strong>{claim.status === 'unsupported' ? 'No valid citation' : 'Support uncertain'}:</strong> {claim.text}</p>)}</details>}
    <MessagePrimitive.Error><ErrorPrimitive.Root className="message-error"><ErrorPrimitive.Message/></ErrorPrimitive.Root></MessagePrimitive.Error>
    {stopped && <p className="muted text-sm mt-3">Response stopped. You can retry below.</p>}
    {!!sources.length && <details className="source-list"><summary><BookOpen size={14}/>{sources.length} sources <ChevronDown size={13}/></summary><div className="source-cards">{sources.map(source => <button key={source.citation_id} onClick={() => openSource(source)}><span className="source-number">{source.citation_id}</span><span><strong>{source.filename}</strong><small>Page {source.page}</small></span></button>)}</div></details>}
    <ActionBarPrimitive.Root hideWhenRunning className="message-actions"><Tip label="Copy answer"><ActionBarPrimitive.Copy className="icon-button copy-action" aria-label="Copy answer"><Copy size={16} className="copy-icon"/><Check size={16} className="check-icon"/></ActionBarPrimitive.Copy></Tip><Tip label="Regenerate answer"><ActionBarPrimitive.Reload className="icon-button" aria-label="Regenerate answer"><RefreshCw size={16}/></ActionBarPrimitive.Reload></Tip>
      {'speechSynthesis' in window && (speaking ? <ActionBarPrimitive.StopSpeaking className="icon-button" aria-label="Stop reading"><VolumeX size={16}/></ActionBarPrimitive.StopSpeaking> : <Tip label="Read aloud"><ActionBarPrimitive.Speak className="icon-button" aria-label="Read aloud"><Volume2 size={16}/></ActionBarPrimitive.Speak></Tip>)}
      <Tip label="Helpful (saved on this device)"><ActionBarPrimitive.FeedbackPositive className="icon-button" aria-label="Helpful answer"><ThumbsUp size={15}/></ActionBarPrimitive.FeedbackPositive></Tip><Tip label="Not helpful (saved on this device)"><ActionBarPrimitive.FeedbackNegative className="icon-button" aria-label="Answer needs improvement"><ThumbsDown size={15}/></ActionBarPrimitive.FeedbackNegative></Tip>
      <Dropdown.Root><Dropdown.Trigger className="icon-button" aria-label="Export answer" disabled={exporting}><Download size={16}/></Dropdown.Trigger><Dropdown.Portal><Dropdown.Content className="menu" sideOffset={5}><ActionBarPrimitive.ExportMarkdown asChild><Dropdown.Item className="menu-item">Markdown</Dropdown.Item></ActionBarPrimitive.ExportMarkdown>{['pdf','docx','csv','json'].map(format => <Dropdown.Item key={format} disabled={!result} className="menu-item" onSelect={() => exportReport(format)}>{format.toUpperCase()}</Dropdown.Item>)}</Dropdown.Content></Dropdown.Portal></Dropdown.Root><Branches/>
    </ActionBarPrimitive.Root>
    {exporting && <p className="muted text-xs mt-2" role="status">Preparing download…</p>}
    {exportError && <p className="export-error" role="alert">{exportError} Use Export answer to retry.</p>}
    {message.isLast && result?.status === 'SUCCESS' && !running && <div className="followups" aria-label="Continue exploring"><ThreadPrimitive.Suggestion prompt={`Explain the conditions and exceptions related to: ${result.query}`} method="replace" className="followup">Explain the conditions <ChevronRight size={13}/></ThreadPrimitive.Suggestion><ThreadPrimitive.Suggestion prompt={`Which exact passages support the answer to: ${result.query}`} method="replace" className="followup">Show supporting passages <ChevronRight size={13}/></ThreadPrimitive.Suggestion></div>}
  </MessagePrimitive.Root>;
}
