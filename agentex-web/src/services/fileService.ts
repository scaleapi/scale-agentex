import {FileAttachment} from '@/types/taskMessages';

/**
 * Maximum file size allowed for upload (20MB)
 */
export const MAX_FILE_SIZE = 20 * 1024 * 1024;

/**
 * Allowed file types for upload
 */
export const ALLOWED_FILE_TYPES = [
  'image/*',
  'application/pdf',
  'text/plain',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
];

/**
 * File Service - Handles file operations like upload and validation
 */
class FileService {
  /**
   * Validates a file based on size constraints
   *
   * @param file - The file to validate
   * @returns Whether the file is valid
   */
  validateFile(file: File): {valid: boolean; reason?: string} {
    if (file.size > MAX_FILE_SIZE) {
      return {
        valid: false,
        reason: `File is too large (${(file.size / 1024 / 1024).toFixed(2)}MB). Maximum size is ${
          MAX_FILE_SIZE / 1024 / 1024
        }MB.`,
      };
    }

    return {valid: true};
  }

  /**
   * Validates multiple files and returns only the valid ones
   *
   * @param files - Array of files to validate
   * @returns Object containing valid files and count of invalid files
   */
  validateFiles(files: File[]): {
    validFiles: File[];
    invalidCount: number;
    invalidReasons: string[];
  } {
    const validFiles: File[] = [];
    const invalidReasons: string[] = [];

    files.forEach(file => {
      const {valid, reason} = this.validateFile(file);
      if (valid) {
        validFiles.push(file);
      } else if (reason) {
        invalidReasons.push(`${file.name}: ${reason}`);
      }
    });

    return {
      validFiles,
      invalidCount: files.length - validFiles.length,
      invalidReasons,
    };
  }

  /**
   * Uploads a file to the server
   *
   * @param file - The file to upload
   * @returns Promise with the uploaded file attachment data
   */
  async uploadFile(
    file: File,
    purpose: string = 'capybara-attachment'
  ): Promise<FileAttachment | null> {
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('purpose', purpose);

      const response = await fetch('/api/files/upload', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Upload failed: ${response.statusText}`);
      }

      const result = await response.json();

      if (Array.isArray(result)) {
        const [actualResult] = result;
        if (actualResult === undefined) {
          return null;
        }
        return {
          file_id: actualResult.id || actualResult.file_id,
          name: file.name,
          size: file.size,
          type: file.type,
        };
      }

      // Format response as a FileAttachment
      return {
        file_id: result.id || result.file_id,
        name: file.name,
        size: file.size,
        type: file.type,
      };
    } catch (error) {
      console.error('Error uploading file:', error);
      return null;
    }
  }

  /**
   * Uploads multiple files in parallel
   *
   * @param files - Array of files to upload
   * @returns Promise with the uploaded file attachments
   */
  async uploadFiles(
    files: File[]
  ): Promise<{attachments: FileAttachment[]; failedCount: number}> {
    const formData = new FormData();
    files.forEach(file => formData.append('files', file));

    const response = await fetch('/api/files/upload', {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`Upload failed: ${response.statusText}`);
    }

    const result = await response.json();

    // Format response as an array of FileAttachments
    const attachments = result.map((item: any) => ({
      file_id: item.id || item.file_id,
      name: item.name,
      size: item.size,
      type: item.type,
    }));

    const failedCount = files.length - attachments.length;

    return {attachments, failedCount};
  }
}

// Export a singleton instance of the service
export const fileService = new FileService();
