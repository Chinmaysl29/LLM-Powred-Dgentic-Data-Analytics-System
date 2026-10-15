import { useState, useRef, type DragEvent, type ChangeEvent } from 'react';
import {
  UploadCloud,
  FileSpreadsheet,
  FileText,
  FileCode,
  FileCheck,
  X,
  AlertCircle,
  Database,
  ArrowRight,
  Loader2,
  CheckCircle2,
} from 'lucide-react';
import { datasetService } from '../../services/datasetService';
import type { Dataset } from '../../types/datasets';

interface UploadDatasetModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (newDataset: Dataset) => void;
}

const ALLOWED_EXTENSIONS = [
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
];

export function UploadDatasetModal({ isOpen, onClose, onSuccess }: UploadDatasetModalProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [datasetName, setDatasetName] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  if (!isOpen) return null;

  function validateAndSelectFile(file: File) {
    setError(null);
    const ext = '.' + (file.name.split('.').pop()?.toLowerCase() ?? '');
    if (ext === '.docx' || ext === '.doc') {
      setError(
        'Microsoft Word (.docx) files are explicitly unsupported. Please upload structured datasets (CSV, TSV, XLS, XLSX, JSON, JSONL, Parquet) or document files (PDF, TXT, Markdown).'
      );
      return;
    }
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      setError(
        `Unsupported file type '${ext}'. Accepted types: CSV, TSV, XLS, XLSX, JSON, JSONL, Parquet, PDF, TXT, Markdown.`
      );
      return;
    }

    if (file.size > 100 * 1024 * 1024) {
      setError('File exceeds maximum upload size limit (100 MB).');
      return;
    }

    setSelectedFile(file);
    if (!datasetName) {
      setDatasetName(file.name.replace(/\.[^/.]+$/, ''));
    }
  }

  function handleDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }

  function handleDragLeave(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      validateAndSelectFile(e.dataTransfer.files[0]);
    }
  }

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    if (e.target.files && e.target.files.length > 0) {
      validateAndSelectFile(e.target.files[0]);
    }
  }

  async function handleUpload() {
    if (!selectedFile) {
      setError('Please select a file to upload.');
      return;
    }

    setIsUploading(true);
    setUploadProgress(15);
    setError(null);

    // Simulated progress steps for great UX
    const interval = setInterval(() => {
      setUploadProgress((prev) => {
        if (prev >= 85) {
          clearInterval(interval);
          return 85;
        }
        return prev + 15;
      });
    }, 250);

    try {
      const created = await datasetService.upload(selectedFile, datasetName.trim() || undefined);
      clearInterval(interval);
      setUploadProgress(100);
      setSuccessMessage(`Dataset '${created.filename}' successfully uploaded and indexed!`);
      setTimeout(() => {
        onSuccess(created);
        handleClose();
      }, 1000);
    } catch (err: unknown) {
      clearInterval(interval);
      setIsUploading(false);
      setError(err instanceof Error ? err.message : 'Upload failed. Please verify the file and try again.');
    }
  }

  function handleClose() {
    if (isUploading) return;
    setSelectedFile(null);
    setDatasetName('');
    setError(null);
    setSuccessMessage(null);
    setUploadProgress(0);
    onClose();
  }

  function getFileIcon(name: string) {
    const ext = name.split('.').pop()?.toLowerCase();
    if (ext === 'xlsx' || ext === 'xls') return <FileSpreadsheet className="w-8 h-8 text-emerald-400" />;
    if (ext === 'pdf') return <FileText className="w-8 h-8 text-rose-400" />;
    if (ext === 'json') return <FileCode className="w-8 h-8 text-amber-400" />;
    return <FileCheck className="w-8 h-8 text-sky-400" />;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-2xl bg-zinc-900 border border-zinc-700/60 rounded-2xl shadow-2xl shadow-black/80 overflow-hidden flex flex-col">
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 bg-zinc-950/60">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400">
              <UploadCloud className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-zinc-100">Upload Dataset</h3>
              <p className="text-xs text-zinc-400">Add files to Enterprise Dataset Management Center</p>
            </div>
          </div>
          <button
            onClick={handleClose}
            disabled={isUploading}
            className="p-1.5 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded-lg transition-colors disabled:opacity-50"
            aria-label="Close modal"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Content */}
        <div className="p-6 space-y-5">
          {error && (
            <div className="flex items-center gap-3 p-3 text-sm text-rose-300 bg-rose-950/50 border border-rose-800/60 rounded-xl">
              <AlertCircle className="w-5 h-5 shrink-0 text-rose-400" />
              <span>{error}</span>
            </div>
          )}

          {successMessage && (
            <div className="flex items-center gap-3 p-3 text-sm text-emerald-300 bg-emerald-950/50 border border-emerald-800/60 rounded-xl">
              <CheckCircle2 className="w-5 h-5 shrink-0 text-emerald-400" />
              <span>{successMessage}</span>
            </div>
          )}

          {/* Drag & Drop Area */}
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`group relative flex flex-col items-center justify-center p-8 border-2 border-dashed rounded-2xl cursor-pointer transition-all duration-200 ${
              isDragging
                ? 'border-sky-500 bg-sky-500/10 scale-[1.01]'
                : selectedFile
                ? 'border-emerald-500/50 bg-emerald-500/5'
                : 'border-zinc-700/80 hover:border-zinc-500 bg-zinc-950/40 hover:bg-zinc-950/70'
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.xlsx,.xls,.json,.pdf,.parquet"
              onChange={handleFileChange}
              className="hidden"
            />

            {selectedFile ? (
              <div className="flex flex-col items-center text-center space-y-3">
                <div className="p-3 bg-zinc-800/80 rounded-xl border border-zinc-700 shadow-md">
                  {getFileIcon(selectedFile.name)}
                </div>
                <div>
                  <p className="text-sm font-medium text-zinc-100">{selectedFile.name}</p>
                  <p className="text-xs text-zinc-400 mt-0.5">
                    {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB • Ready for ingestion
                  </p>
                </div>
                <span className="text-xs text-sky-400 hover:underline">Click or drop to replace file</span>
              </div>
            ) : (
              <div className="flex flex-col items-center text-center space-y-3">
                <div className="p-3.5 bg-zinc-800/60 rounded-2xl border border-zinc-700/60 group-hover:border-sky-500/40 group-hover:scale-110 transition-all text-sky-400">
                  <UploadCloud className="w-8 h-8" />
                </div>
                <div>
                  <p className="text-base font-medium text-zinc-200">Drop Files Here</p>
                  <p className="text-xs text-zinc-400 mt-1">or browse files from your computer</p>
                </div>
                <div className="flex flex-wrap justify-center gap-1.5 pt-2">
                  {['CSV', 'Excel', 'JSON', 'PDF', 'Parquet'].map((format) => (
                    <span
                      key={format}
                      className="px-2 py-0.5 text-[11px] font-medium rounded-md bg-zinc-800/80 text-zinc-300 border border-zinc-700/50"
                    >
                      {format}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Dataset Name Input */}
          <div>
            <label className="block text-xs font-medium text-zinc-300 mb-1.5">
              Dataset Name (Optional)
            </label>
            <input
              type="text"
              value={datasetName}
              onChange={(e) => setDatasetName(e.target.value)}
              placeholder="e.g. Sales_Data_2025"
              className="w-full px-3.5 py-2 text-sm bg-zinc-950/80 border border-zinc-800 focus:border-sky-500 focus:ring-1 focus:ring-sky-500 rounded-xl text-zinc-100 placeholder:text-zinc-600 outline-none transition-all"
            />
          </div>

          {/* Storage Architecture Overview Banner */}
          <div className="p-3.5 rounded-xl bg-zinc-950/60 border border-zinc-800/80 text-xs text-zinc-300 space-y-2">
            <div className="flex items-center gap-2 font-medium text-zinc-200">
              <Database className="w-3.5 h-3.5 text-sky-400" />
              <span>Automatic Enterprise Storage Pipeline:</span>
            </div>
            <div className="flex items-center gap-2 text-zinc-400 font-mono text-[11px]">
              <span className="text-emerald-400">storage/raw/</span>
              <ArrowRight className="w-3 h-3 text-zinc-600" />
              <span className="text-sky-400">storage/processed/ (.parquet)</span>
              <ArrowRight className="w-3 h-3 text-zinc-600" />
              <span className="text-purple-400">datasets/ (metadata, profile, quality)</span>
            </div>
          </div>

          {/* Progress Bar (Visible during upload) */}
          {isUploading && (
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs text-zinc-400">
                <span>Ingesting, profiling and converting to Parquet...</span>
                <span className="font-mono text-sky-400">{uploadProgress}%</span>
              </div>
              <div className="w-full h-2 bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-sky-500 to-indigo-500 transition-all duration-300"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-zinc-800 bg-zinc-950/60">
          <button
            type="button"
            onClick={handleClose}
            disabled={isUploading}
            className="px-4 py-2 text-sm font-medium text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded-xl transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleUpload}
            disabled={!selectedFile || isUploading}
            className="flex items-center gap-2 px-5 py-2 text-sm font-medium text-white bg-sky-600 hover:bg-sky-500 active:bg-sky-700 disabled:bg-zinc-800 disabled:text-zinc-500 rounded-xl transition-colors shadow-lg shadow-sky-600/20"
          >
            {isUploading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Ingesting...</span>
              </>
            ) : (
              <>
                <UploadCloud className="w-4 h-4" />
                <span>Upload Dataset</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
