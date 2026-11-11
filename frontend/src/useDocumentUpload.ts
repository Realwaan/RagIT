import { useCallback, useEffect, useRef, useState } from 'react';
import type { Document } from './types';
import {
  cancelUpload,
  toUploadedDocument,
  uploadDocument,
  UploadJobError,
  validateUploadFile,
} from './upload';

export type WorkspaceUploadState = {
  uploading: boolean;
  uploadStatus: string;
  uploadError: string;
  lastUploadedDoc?: Document;
  clearUploadError: () => void;
  uploadFile: (file?: File) => Promise<Document | undefined>;
  cancelActiveUpload: () => Promise<void>;
};

export function useDocumentUpload({
  onUploaded,
  onJobAccepted,
  onJobCleared,
}: {
  onUploaded: (doc: Document) => void;
  onJobAccepted?: (jobId: string, filename: string) => void;
  onJobCleared?: () => void;
}): WorkspaceUploadState {
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState('');
  const [uploadError, setUploadError] = useState('');
  const [lastUploadedDoc, setLastUploadedDoc] = useState<Document>();
  const controllerRef = useRef<AbortController | null>(null);
  const jobIdRef = useRef<string | null>(null);
  const callbacksRef = useRef({ onUploaded, onJobAccepted, onJobCleared });
  callbacksRef.current = { onUploaded, onJobAccepted, onJobCleared };

  useEffect(() => {
    return () => {
      controllerRef.current?.abort();
    };
  }, []);

  const clearUploadError = useCallback(() => setUploadError(''), []);

  const uploadFile = useCallback(
    async (file?: File): Promise<Document | undefined> => {
      if (!file || uploading) return undefined;
      setUploadError('');
      const invalid = validateUploadFile(file, false);
      if (invalid) {
        setUploadError(invalid);
        return undefined;
      }

      const controller = new AbortController();
      controllerRef.current = controller;
      jobIdRef.current = null;
      setUploading(true);
      setUploadStatus('Uploading document…');
      try {
        const data = await uploadDocument(file, controller.signal, setUploadStatus, jobId => {
          jobIdRef.current = jobId;
          callbacksRef.current.onJobAccepted?.(jobId, file.name);
        });
        if (controller.signal.aborted) return undefined;
        const newDoc = toUploadedDocument(data);
        setLastUploadedDoc(newDoc);
        callbacksRef.current.onUploaded(newDoc);
        return newDoc;
      } catch (e) {
        if (e instanceof UploadJobError) {
          callbacksRef.current.onJobCleared?.();
        }
        if (!controller.signal.aborted) {
          setUploadError((e as Error).message);
        }
        return undefined;
      } finally {
        controllerRef.current = null;
        jobIdRef.current = null;
        setUploading(false);
        setUploadStatus('');
      }
    },
    [uploading]
  );

  const cancelActiveUpload = useCallback(async () => {
    const jobId = jobIdRef.current;
    if (jobId) {
      try {
        await cancelUpload(jobId);
      } catch (e) {
        setUploadError((e as Error).message);
      }
    }
    controllerRef.current?.abort();
    callbacksRef.current.onJobCleared?.();
  }, []);

  return {
    uploading,
    uploadStatus,
    uploadError,
    lastUploadedDoc,
    clearUploadError,
    uploadFile,
    cancelActiveUpload,
  };
}
