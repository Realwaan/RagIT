import { useContext } from 'react';
import { ComposerPrimitive, useAuiState } from '@assistant-ui/react';
import { ArrowUp, FileText, Mic, Paperclip, Square } from 'lucide-react';
import { UIContext } from './AssistantContext';
import { Attachment } from './Attachment';
import { Tip } from './ui';

export function ChatComposer({ disabled = false, unavailable = false }: { disabled?: boolean; unavailable?: boolean }) {
  const running = useAuiState(s => s.thread.isRunning);
  const dictating = useAuiState(s => s.composer.dictation != null);
  const attachments = useAuiState(s => s.composer.attachments);
  const uploading = attachments.some(a => a.status.type === 'running');
  const failed = attachments.some(a => a.status.type === 'incomplete');
  const { doc } = useContext(UIContext);
  const canSend = !!doc && !unavailable && !disabled && !uploading && !failed;
  return <>
    <ComposerPrimitive.Root className="composer" onSubmit={event => { if (!canSend) event.preventDefault(); }}>
      <ComposerPrimitive.AttachmentDropzone disabled={disabled || running} className="dropzone">
        <div className="attachments"><ComposerPrimitive.Attachments components={{ Attachment }}/></div>
        <ComposerPrimitive.Input disabled={disabled} className="composer-input" aria-label="Message RagIT" placeholder={doc && !unavailable ? 'Ask a question about your document…' : 'Attach a document, then ask anything…'} rows={2}/>
        <div className="composer-toolbar">
          <div className="composer-tools">
            <Tip label="Attach PDF, TXT, or Markdown"><ComposerPrimitive.AddAttachment disabled={disabled || running || uploading} className="icon-button" aria-label="Attach document"><Paperclip size={19}/></ComposerPrimitive.AddAttachment></Tip>
            <span className="composer-context" title={doc?.filename}><FileText size={13}/><span>{doc?.filename || 'PDF, TXT, MD'}</span></span>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {('SpeechRecognition' in window || 'webkitSpeechRecognition' in window) && (dictating
              ? <ComposerPrimitive.StopDictation className="icon-button" aria-label="Stop dictation"><Square size={16}/></ComposerPrimitive.StopDictation>
              : <Tip label="Dictate message"><ComposerPrimitive.Dictate disabled={disabled} className="icon-button" aria-label="Dictate message"><Mic size={18}/></ComposerPrimitive.Dictate></Tip>)}
            {running ? <ComposerPrimitive.Cancel className="send" aria-label="Stop response"><Square size={16}/></ComposerPrimitive.Cancel>
              : <ComposerPrimitive.Send disabled={!canSend} className="send" aria-label="Send message"><ArrowUp size={20}/></ComposerPrimitive.Send>}
          </div>
        </div>
      </ComposerPrimitive.AttachmentDropzone>
    </ComposerPrimitive.Root>
    <p className="composer-hint">{!doc ? 'Attach a file or try the sample document to begin.' : 'Answers are grounded in your document. Check the sources for important details.'}</p>
  </>;
}

export function EditComposer() {
  return <ComposerPrimitive.Root className="edit-composer"><ComposerPrimitive.Input aria-label="Edit your message"/><div className="flex justify-end gap-2"><ComposerPrimitive.Cancel className="secondary">Cancel</ComposerPrimitive.Cancel><ComposerPrimitive.Send className="primary">Save and resend</ComposerPrimitive.Send></div></ComposerPrimitive.Root>;
}
