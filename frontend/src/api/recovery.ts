/** Shared transport policy. Only GET/HEAD may be replayed automatically. */
export interface RecoveryPolicy {
  timeoutMs?: number;
  retries?: number;
  baseDelayMs?: number;
  /** SDKs that consume whole response bodies can include that read in the budget. */
  bufferResponse?: boolean;
}

const transientStatuses = new Set([429, 502, 503, 504]);

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const abort = () => { clearTimeout(timer); reject(new DOMException('Request aborted', 'AbortError')); };
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, ms);
    if (signal.aborted) abort();
    else signal.addEventListener('abort', abort, { once: true });
  });
}

function retryDelay(response: Response | undefined, attempt: number, base: number): number {
  const header = response?.headers.get('Retry-After');
  if (header) {
    const seconds = Number(header);
    const delay = Number.isFinite(seconds) ? seconds * 1000 : Date.parse(header) - Date.now();
    if (Number.isFinite(delay) && delay >= 0) return delay;
  }
  return base * 2 ** attempt * (0.5 + Math.random());
}

export async function fetchWithRecovery(
  input: RequestInfo | URL,
  init: RequestInit = {},
  policy: RecoveryPolicy = {},
): Promise<Response> {
  const request = typeof Request !== 'undefined' && input instanceof Request ? input : undefined;
  const method = (init.method ?? request?.method ?? 'GET').toUpperCase();
  const safe = method === 'GET' || method === 'HEAD';
  const retries = safe ? Math.min(3, Math.max(0, policy.retries ?? 2)) : 0;
  const timeout = Math.max(1, policy.timeoutMs ?? 30_000);
  const deadline = Date.now() + timeout;
  const controller = new AbortController();
  const outerSignal = init.signal ?? request?.signal;
  const abort = () => controller.abort();
  if (outerSignal?.aborted) controller.abort();
  else outerSignal?.addEventListener('abort', abort, { once: true });
  const timer = setTimeout(abort, timeout);
  const finish = async (response: Response): Promise<Response> => {
    if (!policy.bufferResponse || !response.body) return response;
    const reader = response.body.getReader();
    const chunks: Uint8Array[] = [];
    let rejectAbort: (() => void) | undefined;
    const cancelled = new Promise<never>((_resolve, reject) => {
      rejectAbort = () => {
        reject(new DOMException('Response body timed out or was cancelled', 'AbortError'));
        void reader.cancel().catch(() => undefined);
      };
      controller.signal.addEventListener('abort', rejectAbort, { once: true });
      if (controller.signal.aborted) rejectAbort();
    });
    try {
      while (true) {
        const { done, value } = await Promise.race([reader.read(), cancelled]);
        if (controller.signal.aborted) throw new DOMException('Response body cancelled', 'AbortError');
        if (done) break;
        chunks.push(value);
      }
      const headers = new Headers(response.headers);
      headers.delete('content-encoding');
      headers.delete('content-length');
      return new Response(new Blob(chunks as BlobPart[]), {
        status: response.status, statusText: response.statusText, headers,
      });
    } finally {
      if (rejectAbort) controller.signal.removeEventListener('abort', rejectAbort);
      reader.releaseLock();
    }
  };
  try {
    for (let attempt = 0; ; attempt++) {
      if (controller.signal.aborted) throw new DOMException('Request aborted', 'AbortError');
      let response: Response | undefined;
      let failure: unknown;
      try {
        response = await fetch(input, { ...init, signal: controller.signal });
      } catch (error) {
        if (controller.signal.aborted || !(error instanceof TypeError)) throw error;
        failure = error;
      }
      if (response && (!transientStatuses.has(response.status) || attempt >= retries)) return await finish(response);
      if (!response && attempt >= retries) throw failure;
      const delay = retryDelay(response, attempt, policy.baseDelayMs ?? 300);
      if (Date.now() + delay >= deadline) {
        if (response) return await finish(response);
        throw failure;
      }
      await response?.body?.cancel();
      await wait(delay, controller.signal);
    }
  } finally {
    clearTimeout(timer);
    outerSignal?.removeEventListener('abort', abort);
  }
}
