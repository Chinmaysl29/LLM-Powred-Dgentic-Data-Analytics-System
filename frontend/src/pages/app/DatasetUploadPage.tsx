/**
 * DatasetUploadPage
 *
 * Provides the Dataset Upload UI for route: /datasets/upload
 *
 * Phase 2F scope — frontend interaction only:
 *   - Drag-and-drop file selection onto a dashed drop zone
 *   - Native file picker via Browse
 *   - Accepted types: .csv, .xlsx, .json
 *   - Client-side extension validation (not a security check)
 *   - Duplicate detection by (name + size + lastModified)
 *   - Selected file list with per-file remove
 *   - Formatted file sizes (reuses formatFileSize from datasetUtils)
 *
 * What is intentionally NOT in this phase:
 *   - No fetch() / API call of any kind
 *   - No file content parsing (no CSV/XLSX/JSON reading)
 *   - No upload progress or fake success messages
 *   - No browser-side file preview
 *
 * Future backend integration path:
 *   When POST /api/upload (or equivalent) is implemented:
 *   1. Build a FormData from the selectedFiles entries
 *   2. Call datasetService.upload(formData)
 *   3. On success navigate to /datasets and show the new dataset
 *   4. On error show the backend error message
 *   No presentation code changes will be required — add the submit
 *   handler alongside the existing "Upload files" button.
 *
 * BACKEND DEPENDENCY: POST /api/upload — not yet implemented.
 */

import { useState, useRef, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import type { UploadFileEntry, UploadValidationError } from '../../types/datasets';
import { formatFileSize } from '../../datasetUtils';
import { datasetService } from '../../services/datasetService';

// ---------------------------------------------------------------------------
// Accepted dataset file extensions
//
// The backend will perform authoritative validation. This list controls only
// the file-picker filter and the client-side extension check on drag-and-drop.
// ---------------------------------------------------------------------------

const ACCEPTED_EXTENSIONS = [
  '.csv',
  '.tsv',
  '.xlsx',
  '.xls',
  '.json',
  '.jsonl',
  '.ndjson',
  '.parquet',
  '.pdf',
  '.txt',
  '.md',
  '.markdown',
] as const;

const ACCEPT_ATTR = ACCEPTED_EXTENSIONS.join(',');

/**
 * Returns the lowercase dot-prefixed extension from a filename, or null.
 * e.g. "sales.CSV" -> ".csv"
 */
function getFileExtension(filename: string): string | null {
  const idx = filename.lastIndexOf('.');
  if (idx === -1 || idx === filename.length - 1) return null;
  return '.' + filename.slice(idx + 1).toLowerCase();
}

/**
 * Returns true if the file extension is in the accepted list.
 */
function isAcceptedExtension(filename: string): boolean {
  const ext = getFileExtension(filename);
  return ext !== null && (ACCEPTED_EXTENSIONS as readonly string[]).includes(ext);
}

/**
 * Builds a stable deduplication key from native File properties.
 * Uses name + size + lastModified — no file content is read.
 */
function fileKey(file: File): string {
  return `${file.name}::${file.size}::${file.lastModified}`;
}

// ---------------------------------------------------------------------------
// Inline SVG icons — no icon library dependency
// ---------------------------------------------------------------------------

function IconUploadCloud({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="40"
      height="40"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <polyline points="16 16 12 12 8 16" />
      <line x1="12" y1="12" x2="12" y2="21" />
      <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3" />
    </svg>
  );
}

function IconFile({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  );
}

function IconX({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

function IconAlertCircle({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// DatasetUploadPage
// ---------------------------------------------------------------------------

export default function DatasetUploadPage() {
  const navigate = useNavigate();
  const [isDragActive, setIsDragActive] = useState<boolean>(false);
  const [selectedFiles, setSelectedFiles] = useState<UploadFileEntry[]>([]);
  const [validationErrors, setValidationErrors] = useState<UploadValidationError[]>([]);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);

  async function handleUpload() {
    if (selectedFiles.length === 0 || isUploading) return;
    setIsUploading(true);
    setUploadError(null);
    try {
      for (const entry of selectedFiles) {
        await datasetService.upload(entry.file);
      }
      navigate('/datasets');
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Upload failed. Please try again.';
      setUploadError(message);
    } finally {
      setIsUploading(false);
    }
  }

  /**
   * Merges newly selected File objects into the selection list.
   * - Validates extension; rejects unsupported types with a clear error.
   * - Skips exact duplicates (name + size + lastModified).
   * - Valid files from a mixed drop are still added.
   */
  const addFiles = useCallback((incoming: File[]) => {
    const errors: UploadValidationError[] = [];
    const valid: UploadFileEntry[] = [];

    for (const file of incoming) {
      if (!isAcceptedExtension(file.name)) {
        const ext = getFileExtension(file.name) ?? 'unknown';
        const isDocx = ext === '.docx' || ext === '.doc';
        errors.push({
          filename: file.name,
          reason: isDocx
            ? 'Microsoft Word (.docx) files are explicitly unsupported. Please upload structured datasets (CSV, TSV, XLS, XLSX, JSON, JSONL, Parquet) or document files (PDF, TXT, Markdown).'
            : `"${ext}" is not supported. Accepted types: CSV, TSV, XLSX, JSON, JSONL, Parquet, PDF, TXT, Markdown.`,
        });

        continue;
      }
      valid.push({ key: fileKey(file), file });
    }

    if (errors.length > 0) {
      setValidationErrors(errors);
    } else {
      setValidationErrors([]);
    }

    if (valid.length > 0) {
      setSelectedFiles((prev) => {
        const existingKeys = new Set(prev.map((e) => e.key));
        const deduped = valid.filter((e) => !existingKeys.has(e.key));
        return [...prev, ...deduped];
      });
    }
  }, []);

  // --- Drag events -----------------------------------------------------------

  function handleDragEnter(e: React.DragEvent<HTMLElement>) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(true);
  }

  function handleDragOver(e: React.DragEvent<HTMLElement>) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(true);
  }

  function handleDragLeave(e: React.DragEvent<HTMLElement>) {
    e.preventDefault();
    e.stopPropagation();
    // Only clear drag-active when leaving the drop zone itself (not a child)
    if (e.currentTarget === e.target || !e.currentTarget.contains(e.relatedTarget as Node)) {
      setIsDragActive(false);
    }
  }

  function handleDrop(e: React.DragEvent<HTMLElement>) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      addFiles(Array.from(e.dataTransfer.files));
    }
  }

  // --- File input change -----------------------------------------------------

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files && e.target.files.length > 0) {
      addFiles(Array.from(e.target.files));
      // Reset the input value so the same file can be re-selected after removal
      e.target.value = '';
    }
  }

  // --- Browse trigger --------------------------------------------------------

  function openFilePicker() {
    inputRef.current?.click();
  }

  // Allow keyboard activation of the drop zone (Enter / Space)
  function handleDropZoneKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      openFilePicker();
    }
  }

  // --- Remove a selected file ------------------------------------------------

  function removeFile(key: string) {
    setSelectedFiles((prev) => prev.filter((e) => e.key !== key));
  }

  // --- Dismiss validation errors ---------------------------------------------

  function dismissErrors() {
    setValidationErrors([]);
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div>
      {/* Page Header */}
      <header className="page-header">
        <div className="upload-page-header-row">
          <div>
            <h1 className="page-title">Upload Dataset</h1>
            <p className="page-description">
              Add CSV, XLSX, JSON, or PDF files to your dataset library.
            </p>
          </div>
          <Link to="/datasets" className="upload-back-link" aria-label="Back to dataset list">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <line x1="19" y1="12" x2="5" y2="12" />
              <polyline points="12 19 5 12 12 5" />
            </svg>
            Back to Datasets
          </Link>
        </div>
      </header>

      {/* Upload Card */}
      <div className="upload-card">

        {/* Card Header */}
        <div className="upload-card-header">
          <h2 className="upload-card-title">Upload your files</h2>
          <p className="upload-card-subtitle">CSV, XLSX, JSON, PDF</p>
        </div>


        {/* Drop Zone */}
        {/*
          The hidden <input> is inside the <form> for native semantics.
          The visual drop zone div is keyboard-accessible via tabIndex + keyDown.
          Clicking anywhere on the zone (or Browse span) triggers openFilePicker().
        */}
        <form onSubmit={(e) => e.preventDefault()} className="upload-form">
          {/* Hidden file input */}
          <input
            ref={inputRef}
            id="dataset-file-input"
            type="file"
            multiple
            accept={ACCEPT_ATTR}
            onChange={handleInputChange}
            className="upload-input-hidden"
            aria-label="Select dataset files"
          />

          {/* Visible drop zone */}
          <div
            role="button"
            tabIndex={0}
            aria-label="Drop files here or press Enter to browse"
            className={`upload-dropzone${isDragActive ? ' upload-dropzone--active' : ''}`}
            onClick={openFilePicker}
            onKeyDown={handleDropZoneKeyDown}
            onDragEnter={handleDragEnter}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            <IconUploadCloud
              className={`upload-cloud-icon${isDragActive ? ' upload-cloud-icon--active' : ''}`}
            />
            <p className="upload-dropzone-text">
              Drag &amp; drop files or{' '}
              <span className="upload-browse-action" aria-hidden="true">
                Browse
              </span>
            </p>
          </div>
        </form>

        {/* Validation errors — shown when unsupported files are dropped */}
        {validationErrors.length > 0 && (
          <div
            className="upload-error-banner"
            role="alert"
            aria-live="assertive"
          >
            <div className="upload-error-banner-header">
              <IconAlertCircle className="upload-error-icon" />
              <span>
                {validationErrors.length === 1
                  ? '1 file was rejected'
                  : `${validationErrors.length} files were rejected`}
              </span>
              <button
                type="button"
                className="upload-error-dismiss"
                onClick={dismissErrors}
                aria-label="Dismiss validation errors"
              >
                <IconX />
              </button>
            </div>
            <ul className="upload-error-list" aria-label="Rejected files">
              {validationErrors.map((err) => (
                <li key={err.filename} className="upload-error-item">
                  <span className="upload-error-filename" title={err.filename}>
                    {err.filename}
                  </span>
                  <span className="upload-error-reason">{err.reason}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Selected files list — only shown when files have been selected */}
        {selectedFiles.length > 0 && (
          <div className="upload-file-list" aria-label="Selected files">
            <h3 className="upload-file-list-heading">
              Selected Files
              <span className="upload-file-count">({selectedFiles.length})</span>
            </h3>

            <div
              className="upload-file-list-scroll"
              role="list"
              aria-label={`${selectedFiles.length} file${selectedFiles.length === 1 ? '' : 's'} selected`}
            >
              {selectedFiles.map((entry) => (
                <div
                  key={entry.key}
                  className="upload-file-item"
                  role="listitem"
                >
                  {/* File icon */}
                  <div className="upload-file-icon" aria-hidden="true">
                    <IconFile />
                  </div>

                  {/* File info */}
                  <div className="upload-file-info">
                    <span
                      className="upload-file-name"
                      title={entry.file.name}
                    >
                      {entry.file.name}
                    </span>
                    <span className="upload-file-size">
                      {formatFileSize(entry.file.size)}
                    </span>
                  </div>

                  {/* Remove button */}
                  <button
                    type="button"
                    className="upload-file-remove"
                    onClick={() => removeFile(entry.key)}
                    aria-label={`Remove ${entry.file.name}`}
                  >
                    <IconX />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Upload Action */}
        {selectedFiles.length > 0 && (
          <div style={{ marginTop: '20px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {uploadError && (
              <div className="upload-error-banner" role="alert">
                <div className="upload-error-banner-header">
                  <IconAlertCircle className="upload-error-icon" />
                  <span>{uploadError}</span>
                </div>
              </div>
            )}
            <button
              type="button"
              className="datasets-upload-btn"
              disabled={isUploading}
              onClick={handleUpload}
              style={{ width: '100%', justifyContent: 'center' }}
            >
              {isUploading
                ? 'Uploading…'
                : `Upload ${selectedFiles.length} file${selectedFiles.length === 1 ? '' : 's'}`}
            </button>
          </div>
        )}

      </div>
    </div>
  );
}
