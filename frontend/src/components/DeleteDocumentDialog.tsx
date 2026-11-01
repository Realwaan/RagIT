import * as AlertDialog from '@radix-ui/react-alert-dialog';
import type { Document } from '../types';

type Props = {
  document?: Document;
  deleting: boolean;
  onClose: () => void;
  onConfirm: (doc: Document) => void;
};

export function DeleteDocumentDialog({ document, deleting, onClose, onConfirm }: Props) {
  return (
    <AlertDialog.Root open={!!document} onOpenChange={value => { if (!value && !deleting) onClose(); }}>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="overlay" />
        <AlertDialog.Content className="confirm-dialog">
          <AlertDialog.Title>Delete this document?</AlertDialog.Title>
          <AlertDialog.Description>
            “{document?.filename}” and its cached pages, preview images, and search index will be removed from your vault.
          </AlertDialog.Description>
          <div className="flex justify-end gap-2 mt-6">
            <AlertDialog.Cancel className="secondary" disabled={deleting}>
              Keep document
            </AlertDialog.Cancel>
            <AlertDialog.Action
              className="danger"
              disabled={deleting}
              onClick={event => {
                event.preventDefault();
                if (document) onConfirm(document);
              }}
            >
              {deleting ? 'Deleting…' : 'Delete document'}
            </AlertDialog.Action>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}
