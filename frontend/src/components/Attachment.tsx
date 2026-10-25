import { AttachmentPrimitive, useAuiState } from '@assistant-ui/react';
import { FileText, X } from 'lucide-react';

export function Attachment() {
  const state = useAuiState(s => s.attachment);
  return <AttachmentPrimitive.Root className="attachment" data-error={state.status.type === 'incomplete'}><FileText size={18}/><div><AttachmentPrimitive.Name/><span role={state.status.type === 'incomplete' ? 'alert' : 'status'}>{state.status.type === 'running' ? 'Processing document…' : state.status.type === 'incomplete' ? state.status.message || 'Upload failed. Remove and retry.' : 'Ready'}</span></div><AttachmentPrimitive.Remove className="icon-button" aria-label="Remove attachment"><X size={14}/></AttachmentPrimitive.Remove></AttachmentPrimitive.Root>;
}
