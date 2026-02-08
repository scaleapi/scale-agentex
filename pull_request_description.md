
# Feature: User File Uploads

## Summary
Added support for users to attach files to their messages. The files are uploaded to the backend and their text content is injected into the prompt sent to the agent.

## Implementation Details

### Backend
- Added `POST /files/upload` endpoint.
- Introduced `StorageProvider` abstract base class to handle file storage.
  - Implemented `LocalStorageProvider` for saving files to the local disk (`uploads/` directory).
  - Used `run_in_threadpool` for file I/O to avoid blocking the async event loop.
- Updated `MessagesUseCase` to retrieve file content and append it to the message text.

### Frontend
- Added file selection button to the chat input component.
- Implemented `useUploadFile` hook to handle the upload request.
- Displays uploaded files as chips in the UI.

## Notes
- The storage implementation is modular. For production, we can swap `LocalStorageProvider` with an S3 implementation without changing the core logic.
- Validation is currently set to a 10MB limit and restricts file types to common text/image formats.

## Verification
- Added unit tests for the upload endpoint (`scripts/test_upload_isolated.py` was used for verification).
- Verified the UI components build and render correctly via `npm run dev`.
