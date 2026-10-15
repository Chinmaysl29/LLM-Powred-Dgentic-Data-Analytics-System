/**
 * DatasetsPage
 *
 * Displays the list of datasets available in the platform.
 *
 * Phase 2B: Uses isolated development data (DEV_DATASETS).
 * Phase 2C: Adds local search, status filter, and sort controls.
 *   The derived dataset pipeline is:
 *     DEV_DATASETS -> search -> status filter -> sort -> visible list
 *   DEV_DATASETS is never mutated.
 * Phase 2D: Adds "View" link per row navigating to /datasets/:datasetId.
 *   Shared utilities (DEV_DATASETS, StatusBadge, formatFileSize, formatDate,
 *   getExtension) are imported from datasetUtils.tsx to avoid duplication
 *   and to satisfy the ESLint react-refresh/only-export-components rule.
 *
 * The component architecture is designed so that only the state
 * initializer changes when the real backend is connected - the entire
 * presentation layer (DatasetTable, DatasetRow, StatusBadge) is
 * data-source agnostic.
 *
 * Future integration path:
 *   1. Import { datasetService } from '../../services/datasetService'
 *   2. Import { ApiError } from '../../api/client'
 *   3. Replace the useState initializer block with a useEffect that
 *      calls datasetService.list(), sets isLoading, and catches ApiError.
 *   4. Remove DEV_DATASETS import.
 *   No presentation code changes are required.
 *
 * BACKEND DEPENDENCY: GET /api/datasets -- not yet implemented.
 */

import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import type { Dataset, DatasetStatus } from '../../types/datasets';
import {
  formatFileSize,
  formatDate,
  getExtension,
} from '../../datasetUtils';
import { StatusBadge } from '../../components/StatusBadge';
import { datasetService } from '../../services/datasetService';

// ---------------------------------------------------------------------------
// Sort options
// ---------------------------------------------------------------------------

type SortOption =
  | 'recently-uploaded'
  | 'oldest-uploaded'
  | 'name-asc'
  | 'name-desc'
  | 'size-desc'
  | 'size-asc';

const SORT_OPTIONS: { value: SortOption; label: string }[] = [
  { value: 'recently-uploaded', label: 'Recently uploaded' },
  { value: 'oldest-uploaded',   label: 'Oldest uploaded' },
  { value: 'name-asc',          label: 'Name A-Z' },
  { value: 'name-desc',         label: 'Name Z-A' },
  { value: 'size-desc',         label: 'Largest size' },
  { value: 'size-asc',          label: 'Smallest size' },
];

// ---------------------------------------------------------------------------
// Status filter options
// ---------------------------------------------------------------------------

type StatusFilterValue = 'all' | DatasetStatus;

const STATUS_FILTER_OPTIONS: { value: StatusFilterValue; label: string }[] = [
  { value: 'all',        label: 'All statuses' },
  { value: 'ready',      label: 'Ready' },
  { value: 'uploaded',   label: 'Uploaded' },
  { value: 'validating', label: 'Validating' },
  { value: 'validated',  label: 'Validated' },
  { value: 'processing', label: 'Processing' },
  { value: 'processed',  label: 'Processed' },
  { value: 'failed',     label: 'Failed' },
];

// ---------------------------------------------------------------------------
// Derived dataset pipeline - pure, no side effects, never mutates source
//
// source -> search -> status filter -> sort -> visible list
// ---------------------------------------------------------------------------

function deriveVisibleDatasets(
  source: Dataset[],
  searchQuery: string,
  statusFilter: StatusFilterValue,
  sortOption: SortOption,
): Dataset[] {
  // 1. Search - case-insensitive, trims surrounding whitespace
  const trimmed = searchQuery.trim().toLowerCase();
  const searched =
    trimmed === ''
      ? source
      : source.filter((ds) => ds.filename.toLowerCase().includes(trimmed));

  // 2. Status filter
  const filtered =
    statusFilter === 'all'
      ? searched
      : searched.filter((ds) => ds.status.toLowerCase() === statusFilter.toLowerCase());

  // 3. Sort - spread to avoid mutating the filtered array reference
  const sorted = [...filtered].sort((a, b) => {
    switch (sortOption) {
      case 'recently-uploaded':
        return new Date(b.uploaded_at).getTime() - new Date(a.uploaded_at).getTime();
      case 'oldest-uploaded':
        return new Date(a.uploaded_at).getTime() - new Date(b.uploaded_at).getTime();
      case 'name-asc':
        return a.filename.localeCompare(b.filename);
      case 'name-desc':
        return b.filename.localeCompare(a.filename);
      case 'size-desc':
        return b.size_bytes - a.size_bytes;
      case 'size-asc':
        return a.size_bytes - b.size_bytes;
      default:
        return 0;
    }
  });

  return sorted;
}

// ---------------------------------------------------------------------------
// DatasetRow - a single row in the dataset table
// Phase 2D: Action cell contains a "View" link -> /datasets/:datasetId
// ---------------------------------------------------------------------------

function DatasetRow({ dataset }: { dataset: Dataset }) {
  return (
    <tr>
      {/* Dataset name + file type */}
      <td>
        <span className="dataset-filename">{dataset.filename}</span>
        <span className="dataset-filetype">{getExtension(dataset.filename)}</span>
      </td>

      {/* File size */}
      <td className="dataset-meta">
        {formatFileSize(dataset.size_bytes)}
      </td>

      {/* Upload date */}
      <td className="dataset-meta">
        <time dateTime={dataset.uploaded_at}>
          {formatDate(dataset.uploaded_at)}
        </time>
      </td>

      {/* Processing status */}
      <td>
        <StatusBadge status={dataset.status} />
      </td>

      {/* Action area - Phase 2D: View details link */}
      <td>
        <div className="dataset-actions">
          <Link
            to={`/datasets/${dataset.dataset_id}`}
            className="dataset-action-link"
            aria-label={`View details for ${dataset.filename}`}
          >
            View
          </Link>
        </div>
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// DatasetTable
//
// Renders the dataset list table, or a contextual empty state.
//
// Accepts:
//   datasets       - the derived (filtered + sorted) list to display
//   hasSourceData  - true if the original data source is non-empty
//   onClearFilters - callback to reset search + status filter
//
// Presentation is data-source agnostic.
// ---------------------------------------------------------------------------

interface DatasetTableProps {
  datasets: Dataset[];
  hasSourceData: boolean;
  onClearFilters: () => void;
}

function DatasetTable({ datasets, hasSourceData, onClearFilters }: DatasetTableProps) {
  if (datasets.length === 0) {
    // Case 1: No datasets exist at all
    if (!hasSourceData) {
      return (
        <div className="dataset-table-wrapper">
          <div className="dataset-empty">
            {/* Inline SVG - no icon library required */}
            <svg
              className="dataset-empty-icon"
              width="52"
              height="52"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.4"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <ellipse cx="12" cy="5" rx="9" ry="3" />
              <path d="M3 5v14c0 1.657 4.03 3 9 3s9-1.343 9-3V5" />
              <path d="M3 12c0 1.657 4.03 3 9 3s9-1.343 9-3" />
            </svg>
            <p className="dataset-empty-title">No datasets yet</p>
            <p className="dataset-empty-body">
              Datasets will appear here once they have been uploaded and are
              available for analysis.
            </p>
            <Link
              to="/datasets/upload"
              className="datasets-upload-btn"
              style={{ marginTop: '16px', display: 'inline-flex' }}
            >
              <svg
                width="15"
                height="15"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              Upload Dataset
            </Link>
          </div>
        </div>
      );
    }

    // Case 2: Datasets exist, but search/filter yields no results
    return (
      <div className="dataset-table-wrapper">
        <div className="dataset-empty">
          <svg
            className="dataset-empty-icon"
            width="52"
            height="52"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
            <line x1="8" y1="11" x2="14" y2="11" />
          </svg>
          <p className="dataset-empty-title">No matching datasets</p>
          <p className="dataset-empty-body">
            No datasets match your current search or filters.
          </p>
          <button
            className="dataset-clear-btn"
            type="button"
            onClick={onClearFilters}
          >
            Clear search and filters
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="dataset-table-wrapper">
      <table className="dataset-table" aria-label="Dataset list">
        <thead>
          <tr>
            <th scope="col">Dataset</th>
            <th scope="col">Size</th>
            <th scope="col">Uploaded</th>
            <th scope="col">Status</th>
            <th scope="col">
              {/* Actions column - no label, context is per-row */}
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {datasets.map((ds) => (
            <DatasetRow key={ds.dataset_id} dataset={ds} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// DatasetLoadingSkeleton
//
// Shown while datasetService.list() is in flight (Phase 2B: never shown
// because data loads synchronously from DEV_DATASETS, but the structure
// is ready for when the real API is connected).
// ---------------------------------------------------------------------------

function DatasetLoadingSkeleton() {
  return (
    <div
      className="dataset-table-wrapper"
      aria-label="Loading datasets"
      aria-busy="true"
    >
      <div className="dataset-skeleton" role="status">
        {Array.from({ length: 5 }, (_, i) => (
          <div key={i} className="dataset-skeleton-row">
            <div className="skeleton-block" style={{ width: '36%' }} />
            <div className="skeleton-block" style={{ width: '8%', marginLeft: 'auto' }} />
            <div className="skeleton-block" style={{ width: '12%' }} />
            <div className="skeleton-block" style={{ width: '11%' }} />
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// DatasetErrorBanner
//
// Shown when datasetService.list() rejects with an ApiError.
// (Phase 2B: never shown because no live API call is made, but the
// structure is ready for when the real API is connected.)
// ---------------------------------------------------------------------------

function DatasetErrorBanner({ message }: { message: string }) {
  return (
    <div className="dataset-error" role="alert">
      <strong>Failed to load datasets.</strong>{' '}
      {message}
    </div>
  );
}

// ---------------------------------------------------------------------------
// DatasetControls - search input, status filter select, sort select
//
// All state lives in the parent (DatasetsPage); callbacks update it.
// ---------------------------------------------------------------------------

interface DatasetControlsProps {
  searchQuery: string;
  onSearchChange: (value: string) => void;
  statusFilter: StatusFilterValue;
  onStatusFilterChange: (value: StatusFilterValue) => void;
  sortOption: SortOption;
  onSortChange: (value: SortOption) => void;
  isFiltered: boolean;
  onClearFilters: () => void;
}

function DatasetControls({
  searchQuery,
  onSearchChange,
  statusFilter,
  onStatusFilterChange,
  sortOption,
  onSortChange,
  isFiltered,
  onClearFilters,
}: DatasetControlsProps) {
  return (
    <div className="dataset-controls" role="search" aria-label="Dataset search and filter controls">
      {/* Search */}
      <div className="dataset-control-field">
        <label htmlFor="dataset-search" className="dataset-control-label">
          Search
        </label>
        <div className="dataset-search-wrapper">
          {/* Search icon */}
          <svg
            className="dataset-search-icon"
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            id="dataset-search"
            type="search"
            className="dataset-search-input"
            placeholder="Search by filename..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            aria-label="Search datasets by filename"
            autoComplete="off"
            spellCheck={false}
          />
        </div>
      </div>

      {/* Status filter */}
      <div className="dataset-control-field">
        <label htmlFor="dataset-status-filter" className="dataset-control-label">
          Status
        </label>
        <select
          id="dataset-status-filter"
          className="dataset-control-select"
          value={statusFilter}
          onChange={(e) => onStatusFilterChange(e.target.value as StatusFilterValue)}
          aria-label="Filter datasets by status"
        >
          {STATUS_FILTER_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Sort */}
      <div className="dataset-control-field">
        <label htmlFor="dataset-sort" className="dataset-control-label">
          Sort
        </label>
        <select
          id="dataset-sort"
          className="dataset-control-select"
          value={sortOption}
          onChange={(e) => onSortChange(e.target.value as SortOption)}
          aria-label="Sort datasets"
        >
          {SORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Clear filters - only shown when search or status filter is active */}
      {isFiltered && (
        <div className="dataset-control-field dataset-control-field--clear">
          <button
            type="button"
            className="dataset-clear-btn"
            onClick={onClearFilters}
            aria-label="Clear active search and status filters"
          >
            Clear filters
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// DatasetsPage - page component for route /datasets
//
// State:
//   datasets     - source list (Phase 2B: DEV_DATASETS)
//   isLoading    - true while datasetService.list() is in flight
//   error        - error message if datasetService.list() rejected
//   searchQuery  - Phase 2C: current filename search string
//   statusFilter - Phase 2C: selected status filter value
//   sortOption   - Phase 2C: selected sort option
//
// Phase 2B: datasets is initialised synchronously from DEV_DATASETS.
//   isLoading is always false.
//   error is always null.
//   The loading and error UIs are structurally present but not triggered.
//
// Future integration (no presentation changes needed):
//   const [datasets, setDatasets] = useState<Dataset[]>([]);
//   const [isLoading, setIsLoading] = useState(true);
//   const [error, setError] = useState<string | null>(null);
//   useEffect(() => {
//     datasetService.list()
//       .then(res => setDatasets(res.items))
//       .catch((err: ApiError) => setError(err.message))
//       .finally(() => setIsLoading(false));
//   }, []);
// ---------------------------------------------------------------------------

export default function DatasetsPage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    datasetService
      .list()
      .then((data) => {
        if (isMounted) setDatasets(data);
      })
      .catch((err: unknown) => {
        if (isMounted) {
          const message = err instanceof Error ? err.message : 'Failed to load datasets';
          setError(message);
        }
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  // Phase 2C: search, filter, sort - all local state, no global state.
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<StatusFilterValue>('all');
  const [sortOption, setSortOption] = useState<SortOption>('recently-uploaded');

  // Derived dataset pipeline: source -> search -> filter -> sort
  // DEV_DATASETS is never mutated - spread happens inside deriveVisibleDatasets.
  const visibleDatasets = deriveVisibleDatasets(
    datasets,
    searchQuery,
    statusFilter,
    sortOption,
  );

  // isFiltered = true when search or status filter is active (NOT sort).
  // Sort is an independent control and is NOT reset by Clear Filters.
  const isFiltered = searchQuery.trim() !== '' || statusFilter !== 'all';

  function handleClearFilters() {
    setSearchQuery('');
    setStatusFilter('all');
    // sortOption is intentionally NOT reset - sort is independent.
  }

  // Count labels: total from source, visible from derived pipeline.
  const totalCount = datasets.length;
  const visibleCount = visibleDatasets.length;

  return (
    <div className="ws-page dataset-workspace">
      {/* Page Header */}
      <header className="page-header">
        <div className="datasets-header-row">
          <div>
            <p className="eyebrow">DATA MANAGEMENT / DATASETS</p>
            <h1 className="page-title">Your data, organized.</h1>
            <p className="page-description">
              Manage and inspect datasets available for analysis.
            </p>
          </div>
          {/* Phase 2F: Upload entry point */}
          <Link to="/datasets/upload" className="datasets-upload-btn">
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            Upload Dataset
          </Link>
        </div>
      </header>

      {/* Dataset Summary */}
      {!isLoading && !error && (
        <div className="dataset-summary" aria-label="Dataset summary">
          <div className="dataset-stat">
            <span className="dataset-stat-value">{totalCount}</span>
            <span className="dataset-stat-label">
              {totalCount === 1 ? 'Dataset' : 'Datasets'}
            </span>
          </div>

          {/* Visible result count - only shown when filtering is active */}
          {isFiltered && (
            <div className="dataset-stat">
              <span className="dataset-stat-value">{visibleCount}</span>
              <span className="dataset-stat-label">
                {visibleCount === 1 ? 'Result' : 'Results'}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Search / Filter / Sort controls - only shown when data is available */}
      {!isLoading && !error && totalCount > 0 && (
        <DatasetControls
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          statusFilter={statusFilter}
          onStatusFilterChange={setStatusFilter}
          sortOption={sortOption}
          onSortChange={setSortOption}
          isFiltered={isFiltered}
          onClearFilters={handleClearFilters}
        />
      )}

      {/* Dataset List - conditional on state */}
      {isLoading && <DatasetLoadingSkeleton />}
      {!isLoading && error !== null && <DatasetErrorBanner message={error} />}
      {!isLoading && error === null && (
        <DatasetTable
          datasets={visibleDatasets}
          hasSourceData={totalCount > 0}
          onClearFilters={handleClearFilters}
        />
      )}
    </div>
  );
}
