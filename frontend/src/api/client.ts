import { fetchWithRecovery } from './recovery';
/**
 * Shared API client using the native fetch API.
 *
 * Provides a central place for:
 * - Base URL configuration (via VITE_API_BASE_URL)
 * - HTTP request handling with typed methods
 * - Consistent error normalization
 * - Timeout handling
 *
 * Authenticated requests use the token maintained by AuthContext.
 */

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

function getApiBaseUrl(): string {
  const envUrl = (import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || '').trim();

  if (import.meta.env.PROD) {
    // In production, if envUrl is missing or points to localhost/127.0.0.1, use same-origin
    if (!envUrl || envUrl.includes('localhost') || envUrl.includes('127.0.0.1')) {
      if (typeof window !== 'undefined' && window.location?.origin) {
        return window.location.origin;
      }
      return '';
    }
    return envUrl.replace(/\/api\/v1\/?$/, '');
  }

  // In development, target the local backend port 8000
  if (envUrl) {
    return envUrl.replace(/\/api\/v1\/?$/, '');
  }
  return 'http://localhost:8000';
}

const API_BASE_URL: string = getApiBaseUrl();

const DEFAULT_TIMEOUT_MS = 30_000;

// ---------------------------------------------------------------------------
// Error Model
// ---------------------------------------------------------------------------

/**
 * Normalized API error thrown by all client methods.
 *
 * - `status`  â€” HTTP status code, or 0 for network/timeout errors.
 * - `code`    â€” Machine-readable error code for programmatic handling.
 * - `message` â€” Human-readable description safe to display in UI.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

/** Maps HTTP status codes to machine-readable error codes. */
function errorCodeFromStatus(status: number): string {
  switch (status) {
    case 400:
      return 'VALIDATION_ERROR';
    case 401:
      return 'UNAUTHORIZED';
    case 403:
      return 'FORBIDDEN';
    case 404:
      return 'NOT_FOUND';
    case 409:
      return 'CONFLICT';
    case 422:
      return 'VALIDATION_ERROR';
    case 429:
      return 'RATE_LIMITED';
    default:
      return status >= 500 ? 'SERVER_ERROR' : 'UNKNOWN_ERROR';
  }
}

// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// Authentication Token Storage
// ---------------------------------------------------------------------------

const AUTH_TOKEN_KEY = 'auth_token';

export function getAuthToken(): string | null {
  try {
    return localStorage.getItem(AUTH_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setAuthToken(token: string): void {
  try {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
  } catch {
    // Ignore storage quota or access errors
  }
}

export function clearAuthToken(): void {
  try {
    localStorage.removeItem(AUTH_TOKEN_KEY);
  } catch {
    // Ignore storage access errors
  }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

interface RequestOptions {
  responseType?: 'json' | 'blob';
  /** Query parameters appended to the URL. */
  params?: Record<string, string>;
  /** Additional headers merged with defaults. */
  headers?: Record<string, string>;
  /** Request timeout in milliseconds. Defaults to 30 000. */
  timeout?: number;
  /** AbortSignal for external cancellation. */
  signal?: AbortSignal;
}

/**
 * Core request function. All public methods delegate here.
 *
 * Throws {@link ApiError} for HTTP errors, network failures, and timeouts.
 */
async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  options: RequestOptions = {},
): Promise<T> {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const base = API_BASE_URL || (typeof window !== 'undefined' ? window.location.origin : '');
  const url = new URL(normalizedPath, base);

  if (options.params) {
    for (const [key, value] of Object.entries(options.params)) {
      url.searchParams.set(key, value);
    }
  }

  const isFormData = typeof FormData !== 'undefined' && body instanceof FormData;

  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...options.headers,
  };

  if (!isFormData) {
    headers['Content-Type'] = 'application/json';
  }

  const token = getAuthToken();
  if (token && !headers['Authorization']) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // Timeout handling via AbortController
  const timeoutMs = options.timeout ?? DEFAULT_TIMEOUT_MS;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  // If the caller provided an external signal, abort when it fires.
  const abortFromCaller = () => controller.abort();
  if (options.signal) {
    if (options.signal.aborted) controller.abort();
    options.signal.addEventListener('abort', abortFromCaller, {
      once: true,
    });
  }

  try {
    const response = await fetchWithRecovery(url.toString(), {
      method,
      headers,
      body: isFormData ? (body as FormData) : (body !== undefined ? JSON.stringify(body) : undefined),
      signal: controller.signal,
    }, { timeoutMs });

    // --- Success path ---
    if (response.ok) {
      // Handle 204 No Content
      if (response.status === 204) {
        return undefined as T;
      }
      if (options.responseType === 'blob') return await response.blob() as T;
      return (await response.json()) as T;
    }

    // --- Error path: attempt to parse backend error body ---
    let message = response.statusText || 'Request failed';
    let errorCode = errorCodeFromStatus(response.status);
    try {
      const errorBody: unknown = await response.json();
      if (typeof errorBody === 'object' && errorBody !== null && 'message' in errorBody && typeof errorBody.message === 'string') message = errorBody.message;
      if (typeof errorBody === 'object' && errorBody !== null && 'error_code' in errorBody && typeof errorBody.error_code === 'string') errorCode = errorBody.error_code;
      if (
        typeof errorBody === 'object' &&
        errorBody !== null &&
        'detail' in errorBody
      ) {
        const detail = (errorBody as { detail: unknown }).detail;
        message = typeof detail === 'string' ? detail : JSON.stringify(detail);
      }
    } catch {
      // Body is not JSON â€” use statusText as the message.
    }

    throw new ApiError(
      response.status,
      errorCode,
      message,
    );
  } catch (error: unknown) {
    // Re-throw ApiError instances as-is.
    if (error instanceof ApiError) {
      throw error;
    }

    // Network failure or abort
    if (error instanceof DOMException && error.name === 'AbortError') {
      if (options.signal?.aborted) throw new ApiError(0, 'CANCELLED', 'Request cancelled');
      throw new ApiError(0, 'TIMEOUT', 'Request timed out');
    }

    if (error instanceof TypeError) {
      throw new ApiError(0, 'NETWORK_ERROR', 'Network request failed');
    }

    throw new ApiError(0, 'UNKNOWN_ERROR', 'An unexpected error occurred');
  } finally {
    clearTimeout(timeoutId);
    options.signal?.removeEventListener('abort', abortFromCaller);
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export const apiClient = {
  getBlob(path: string, options?: RequestOptions): Promise<Blob> {
    return request<Blob>('GET', path, undefined, { ...options, responseType: 'blob' });
  },
  get<T>(path: string, options?: RequestOptions): Promise<T> {
    return request<T>('GET', path, undefined, options);
  },

  post<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return request<T>('POST', path, body, options);
  },

  put<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return request<T>('PUT', path, body, options);
  },

  patch<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return request<T>('PATCH', path, body, options);
  },

  delete<T>(path: string, options?: RequestOptions): Promise<T> {
    return request<T>('DELETE', path, undefined, options);
  },
};
