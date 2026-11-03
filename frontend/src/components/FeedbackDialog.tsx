import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { ThumbsDown } from 'lucide-react';

export function FeedbackDialog({ messageId }: { messageId: string }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('Incorrect answer');
  const [notes, setNotes] = useState('');
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  return <><Dialog.Root open={open} onOpenChange={setOpen}><Dialog.Trigger className="icon-button" aria-label="Answer needs improvement"><ThumbsDown size={15}/></Dialog.Trigger><Dialog.Portal><Dialog.Overlay className="overlay"/><Dialog.Content className="confirm-dialog"><Dialog.Title>What needs improvement?</Dialog.Title><Dialog.Description>Your feedback is saved on this device only.</Dialog.Description><form onSubmit={e => { e.preventDefault(); try { localStorage.setItem(`ragit_feedback_detail_${messageId}`, JSON.stringify({ reason, notes: notes.trim(), savedAt: Date.now() })); localStorage.setItem(`ragit_feedback_${messageId}`, 'negative'); setStatus('Feedback saved on this device.'); setError(''); setOpen(false); } catch { setError('Feedback could not be saved. Free up browser storage and try again.'); } }}><label className="field-label">Reason<select aria-label="Reason" className="text-field" value={reason} onChange={e => setReason(e.target.value)}>{['Incorrect answer', 'Incomplete answer', 'Poorly sourced', 'Hard to understand', 'Other'].map(r => <option key={r}>{r}</option>)}</select></label><label className="field-label">Additional details (optional)<textarea className="text-field" rows={4} maxLength={2000} value={notes} onChange={e => setNotes(e.target.value)}/></label>{error && <p role="alert">{error}</p>}<div className="flex justify-end gap-2 mt-6"><Dialog.Close type="button" className="secondary">Cancel</Dialog.Close><button className="primary">Save feedback</button></div></form></Dialog.Content></Dialog.Portal></Dialog.Root>{status && <span className="muted text-xs" role="status">{status}</span>}</>;
}
