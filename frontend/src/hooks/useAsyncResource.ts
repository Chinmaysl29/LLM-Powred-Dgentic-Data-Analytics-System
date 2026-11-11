import { useEffect, useMemo, useState } from 'react';

type Loader<T> = (signal: AbortSignal) => Promise<T>;

/** Keep results tied to their request, and ignore completions after cancellation.
 * Pass a stable (useCallback) loader, or null to disable the request.
 */
export function useAsyncResource<T>(load: Loader<T> | null, revision = 0) {
  const request = useMemo(() => ({ load, revision }), [load, revision]);
  const [result, setResult] = useState<{
    request: typeof request;
    data?: T;
    error?: string;
  }>();

  useEffect(() => {
    const { load } = request;
    if (!load) return;
    const controller = new AbortController();
    void (async () => {
      try {
        const data = await load(controller.signal);
        if (!controller.signal.aborted) setResult({ request, data });
      } catch (error) {
        if (!controller.signal.aborted) {
          setResult({
            request,
            error: error instanceof Error ? error.message : 'Unable to load data.',
          });
        }
      }
    })();
    return () => controller.abort();
  }, [request]);

  const current = load && result?.request === request ? result : undefined;
  return { data: current?.data, error: current?.error ?? '', loading: Boolean(load && !current) };
}
