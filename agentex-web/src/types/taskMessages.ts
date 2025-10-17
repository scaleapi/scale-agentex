/**
 * File attachment interface. This is not used by Agentex or ACP.
 */
export interface FileAttachment {
  /**
   * The unique ID of the attached file
   */
  file_id: string;

  /**
   * The name of the file
   */
  name: string;

  /**
   * The size of the file in bytes
   */
  size: number;

  /**
   * The MIME type or content type of the file
   */
  type: string;

  /**
   * The status of the file upload
   */
  status?: 'success' | 'error' | 'uploading';

  /**
   * The error message for failed uploads
   */
  error?: string;

  /**
   * The progress of the file upload
   */
  progress?: number;
}
