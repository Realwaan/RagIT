import { FeedbackDialog } from './FeedbackDialog';
import { ActivityStatus, QuoteSelection } from './ConversationTools';
import { lazy, Suspense, useContext } from 'react';
import { ThreadPrimitive, MessagePrimitive, ActionBarPrimitive, BranchPickerPrimitive, ErrorPrimitive, useAuiState } from '@assistant-ui/react';
import * as Dropdown from '@radix-ui/react-dropdown-menu';
import { Activity, Sparkles, BookOpen, Check, ChevronDown, ChevronLeft, ChevronRight, Copy, Download, Pencil, RefreshCw, ThumbsDown, ThumbsUp, Volume2, VolumeX, AlertCircle } from 'lucide-react';
import { EvidenceContext } from '../EvidenceContext';
const LazyMarkdown = lazy(() => import('../Markdown').then(module => ({ default: module.Markdown })));
function Markdown() {
  return <Suspense fallback={<p role="status">Formatting answer…</p>}><LazyMarkdown /></Suspense>;
}
import type { Result } from '../types';
import { useReportExport } from '../reportExport';
import { Attachment } from './Attachment';
import { UIContext } from './AssistantContext';
import { cn, Tip } from './ui';

function Branches() { return <BranchPickerPrimitive.Root hideWhenSingleBranch className="branches"><BranchPickerPrimitive.Previous className="icon-button" aria-label="Previous response version"><ChevronLeft size={14}/></BranchPickerPrimitive.Previous><BranchPickerPrimitive.Number/> / <BranchPickerPrimitive.Count/><BranchPickerPrimitive.Next className="icon-button" aria-label="Next response version"><ChevronRight size={14}/></BranchPickerPrimitive.Next></BranchPickerPrimitive.Root>; }
export function UserMessage() { const message = useAuiState(s => s.message); return <MessagePrimitive.Root className="user-message group" id={`message-${message.id}`} tabIndex={-1}><div className="user-bubble"><MessagePrimitive.Attachments components={{ Attachment }}/><MessagePrimitive.Content/></div><div className="user-actions opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity"><ActionBarPrimitive.Edit className="icon-button user-edit-btn" aria-label="Edit message"><Pencil size={13}/></ActionBarPrimitive.Edit><Branches/></div></MessagePrimitive.Root>; }
export function AssistantMessage() {
  const message = useAuiState(s => s.message);
  const { openSource } = useContext(UIContext);
  const { exporting, exportError, exportReport: runExport } = useReportExport();
  const result = message.metadata.custom?.result as Result | undefined;
  const running = message.status?.type === 'running';
  const stopped = message.status?.type === 'incomplete' && message.status.reason === 'cancelled';
  const activity = message.metadata.custom?.activity as string | undefined;
  const speaking = message.speech != null;
  const sources = result?.sources || [];
  const hasTelemetry = !running && !!result && (
    result.total_ms !== undefined ||
    result.retrieval_ms !== undefined ||
    result.evaluation?.retrieval_score !== undefined ||
    result.model_used !== undefined ||
    result.token_telemetry !== undefined
  );
  const modelName = result?.token_telemetry?.model_used || result?.model_used || result?.generation_mode;
  const totalTokens = result?.token_telemetry?.total_tokens;
  const exportReport = (format: string) => {
    if (!result) return;
    void runExport({ ...result, format }, `ragit-answer.${format}`);
  };
  return <MessagePrimitive.Root className="assistant-message" id={`message-${message.id}`} tabIndex={-1}><div className="assistant-label"><span className="logo small"><Sparkles size={14}/></span><strong>RagIT</strong>{result && <span className={cn('answer-status', result.status === 'REFUSE' && 'unverified')}>{result.status === 'REFUSE' ? 'Answer not verified' : 'Document-based answer'}</span>}</div>
    {running && <p className="activity" role="status">{activity || 'Preparing answer…'}</p>}
    <EvidenceContext.Provider value={{ sources, open: openSource }}><MessagePrimitive.Content components={{ Text: Markdown }}/></EvidenceContext.Provider>
    <MessagePrimitive.Error><ErrorPrimitive.Root className="message-error"><ErrorPrimitive.Message/><ActionBarPrimitive.Reload className="secondary">Retry answer</ActionBarPrimitive.Reload></ErrorPrimitive.Root></MessagePrimitive.Error>
    {stopped && <p className="muted text-sm mt-3">Response stopped. Your partial answer is preserved. Regenerate below to try again.</p>}
    <div className="assistant-meta-row">
      {result?.evaluation?.claim_support === 'needs_review' && (
        <details className="source-list claim-review-details">
          <summary><AlertCircle size={13} className="text-amber-500"/><span>Some claims need source review</span><ChevronDown size={13}/></summary>
          <div className="claim-review-body">
            <p className="claim-review-intro">Citation links identify passages; some claims are syntheses or need review.</p>
            {result.evaluation.claims?.filter(c => c.status !== 'supported').map((claim, i) => (
              <p key={i} className="claim-review-item"><strong>{claim.status === 'unsupported' ? 'No valid citation' : 'Support uncertain'}:</strong> {claim.text}</p>
            ))}
          </div>
        </details>
      )}
      {!!sources.length && <details className="source-list"><summary><BookOpen size={13}/><span>{sources.length} sources</span><ChevronDown size={13}/></summary><div className="source-cards">{sources.map(source => <button key={source.citation_id} onClick={() => openSource(source)}><span className="source-number">{source.citation_id}</span><span><strong>{source.filename}</strong><small>Page {source.page}</small></span></button>)}</div></details>}
      {hasTelemetry && (
        <details className="source-list telemetry-details">
          <summary aria-label="Retrieval and answer telemetry">
            <Activity size={14}/>
            <span>Telemetry</span>
            {result?.total_ms !== undefined && <span className="tabular-nums">· {Math.round(result.total_ms)} ms</span>}
            <ChevronDown size={13}/>
          </summary>
          <div className="telemetry-grid" role="region" aria-label="Answer telemetry metrics">
            {result?.total_ms !== undefined && (
              <div className="telemetry-item">
                <span>Total latency</span>
                <strong className="tabular-nums">{result.total_ms} ms</strong>
              </div>
            )}
            {result?.retrieval_ms !== undefined && (
              <div className="telemetry-item">
                <span>Retrieval latency</span>
                <strong className="tabular-nums">{result.retrieval_ms} ms</strong>
              </div>
            )}
            {result?.evaluation?.retrieval_score !== undefined && (
              <div className="telemetry-item">
                <span>Retrieval score</span>
                <strong className="tabular-nums">{result.evaluation.retrieval_score}</strong>
              </div>
            )}
            <div className="telemetry-item">
              <span>Citation check</span>
              <strong>{result?.evaluation?.citation_verified ? 'Verified' : result?.evaluation?.claim_support || 'Checked'}</strong>
            </div>
            {modelName && (
              <div className="telemetry-item">
                <span>Model / mode</span>
                <strong>{modelName}</strong>
              </div>
            )}
            {totalTokens !== undefined && (
              <div className="telemetry-item">
                <span>Tokens</span>
                <strong className="tabular-nums">{totalTokens}</strong>
              </div>
            )}
          </div>
        </details>
      )}
    </div>
    <ActionBarPrimitive.Root hideWhenRunning className="message-actions"><QuoteSelection messageId={message.id}/><Tip label="Copy answer"><ActionBarPrimitive.Copy className="icon-button copy-action" aria-label="Copy answer"><Copy size={16} className="copy-icon"/><Check size={16} className="check-icon"/></ActionBarPrimitive.Copy></Tip><Tip label="Regenerate answer"><ActionBarPrimitive.Reload className="icon-button" aria-label="Regenerate answer"><RefreshCw size={16}/></ActionBarPrimitive.Reload></Tip>
      {'speechSynthesis' in window && (speaking ? <ActionBarPrimitive.StopSpeaking className="icon-button" aria-label="Stop reading"><VolumeX size={16}/></ActionBarPrimitive.StopSpeaking> : <Tip label="Read aloud"><ActionBarPrimitive.Speak className="icon-button" aria-label="Read aloud"><Volume2 size={16}/></ActionBarPrimitive.Speak></Tip>)}
      <Tip label="Helpful (saved on this device)"><ActionBarPrimitive.FeedbackPositive className="icon-button" aria-label="Helpful answer"><ThumbsUp size={15}/></ActionBarPrimitive.FeedbackPositive></Tip><FeedbackDialog messageId={message.id}/>
      <Dropdown.Root><Dropdown.Trigger className="icon-button" aria-label="Export answer" disabled={exporting}><Download size={16}/></Dropdown.Trigger><Dropdown.Portal><Dropdown.Content className="menu" sideOffset={5}><ActionBarPrimitive.ExportMarkdown asChild><Dropdown.Item className="menu-item">Markdown</Dropdown.Item></ActionBarPrimitive.ExportMarkdown>{['pdf','docx','csv','json'].map(format => <Dropdown.Item key={format} disabled={!result} className="menu-item" onSelect={() => exportReport(format)}>{format.toUpperCase()}</Dropdown.Item>)}</Dropdown.Content></Dropdown.Portal></Dropdown.Root><Branches/>
    </ActionBarPrimitive.Root>
    {exporting && <p className="muted text-xs mt-2" role="status">Preparing download…</p>}
    {exportError && <p className="export-error" role="alert">{exportError} Use Export answer to retry.</p>}
    {message.isLast && result?.status === 'SUCCESS' && !running && <div className="followups" aria-label="Continue exploring"><ThreadPrimitive.Suggestion prompt={`Explain the conditions and exceptions related to: ${result.query}`} method="replace" className="followup"><span>Explain conditions</span><ChevronRight size={13}/></ThreadPrimitive.Suggestion><ThreadPrimitive.Suggestion prompt={`Which exact passages support the answer to: ${result.query}`} method="replace" className="followup"><span>Show supporting passages</span><ChevronRight size={13}/></ThreadPrimitive.Suggestion></div>}
  </MessagePrimitive.Root>;
}
