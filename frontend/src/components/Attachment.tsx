import { AttachmentPrimitive, useAuiState } from '@assistant-ui/react';
import { FileText, X } from 'lucide-react';

export function Attachment() {
  const state = useAuiState(s => s.attachment);
  return <AttachmentPrimitive.Root className="attachment"><FileText size={18}/><div><AttachmentPrimitive.Name/><span>{state.status.type === 'running' ? 'Processing document…' : state.status.type === 'incomplete' ? state.status.message || 'Upload failed. Remove and retry.' : 'Ready'}</span></div><AttachmentPrimitive.Remove className="icon-button" aria-label="Remove attachment"><X size={14}/></AttachmentPrimitive.Remove></AttachmentPrimitive.Root>;
}
