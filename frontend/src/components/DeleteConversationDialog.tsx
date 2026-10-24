import * as AlertDialog from '@radix-ui/react-alert-dialog';

type Props = { open: boolean; onClose: () => void; onConfirm: () => void };

export function DeleteConversationDialog({ open, onClose, onConfirm }: Props) {
  return (
    <AlertDialog.Root open={open} onOpenChange={value => { if (!value) onClose(); }}>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="overlay" />
        <AlertDialog.Content className="confirm-dialog">
          <AlertDialog.Title>Delete this conversation?</AlertDialog.Title>
          <AlertDialog.Description>
            The saved messages and response versions will be removed from this browser.
            Your documents stay available.
          </AlertDialog.Description>
          <div className="flex justify-end gap-2 mt-6">
            <AlertDialog.Cancel className="secondary">Keep conversation</AlertDialog.Cancel>
            <AlertDialog.Action className="danger" onClick={onConfirm}>Delete</AlertDialog.Action>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}
