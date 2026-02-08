import { useCallback, useState } from 'react';
import { toast } from 'react-toastify';

export type FileAttachment = {
  file_id: string;
  name: string;
  size: number;
  type: string;
};

/**
 * Custom hook to handle file uploads to the Agentex backend.
 * Returns an upload function and current loading state.
 */
export function useUploadFile() {
  const [isUploading, setIsUploading] = useState(false);

  const uploadFile = useCallback(async (file: File): Promise<FileAttachment | null> => {
    setIsUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const baseURL = process.env.NEXT_PUBLIC_AGENTEX_API_BASE_URL || 'http://localhost:5003';
      const response = await fetch(`${baseURL}/files/upload`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        let errorMessage = 'Upload failed';
        try {
            const errorData = await response.json();
            errorMessage = errorData.detail || errorData.message || errorMessage;
        } catch { /* empty */ }
        throw new Error(errorMessage);
      }

      const data = await response.json();
      return data as FileAttachment;

    } catch (error: any) {
      toast.error(`Upload failed: ${error.message}`);
      return null;
    } finally {
      setIsUploading(false);
    }
  }, []);

  return { uploadFile, isUploading };
}
