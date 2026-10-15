import { fetchWithRecovery } from '../../api/recovery';
/**
 * Supabase Client Initialization & Configuration Module
 *
 * Configures the official Supabase JavaScript SDK for AI Data Analyst OS.
 * Manages singleton client instance with environment validation, persistent
 * browser sessions, automatic token refresh, and safe error normalization.
 */

import { createClient, type SupabaseClient } from '@supabase/supabase-js';

/**
 * Resolve Supabase connection configuration strictly from environment variables.
 * Prefer VITE_ prefix for Vite apps, with backward compatibility for NEXT_PUBLIC_.
 */
function getSupabaseConfig(): { url: string; anonKey: string } {
  const envUrl = (
    import.meta.env.VITE_SUPABASE_URL ||
    import.meta.env.NEXT_PUBLIC_SUPABASE_URL ||
    ''
  ).trim();

  const envKey = (
    import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ||
    import.meta.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ||
    ''
  ).trim();

  return { url: envUrl, anonKey: envKey };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let supabaseInstance: SupabaseClient<any> | null = null;

/**
 * Returns true if the required Supabase URL and key are available.
 */
export function isSupabaseConfigured(): boolean {
  const { url, anonKey } = getSupabaseConfig();
  return Boolean(url && anonKey && url.startsWith('http'));
}

/**
 * Get or initialize the singleton Supabase client.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function getSupabaseClient(): SupabaseClient<any> {
  if (supabaseInstance) {
    return supabaseInstance;
  }

  const { url, anonKey } = getSupabaseConfig();

  if (!url || !anonKey) {
    throw new Error(
      'Supabase configuration error: Missing VITE_SUPABASE_URL or VITE_SUPABASE_PUBLISHABLE_KEY.',
    );
  }

  try {
    supabaseInstance = createClient(url, anonKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
        storageKey: 'ai_data_analyst_os_auth_token',
      },
      db: {
        schema: 'public',
        // The transport owns the attempt budget; SDK retries would multiply it.
        retry: false,
      },
      global: {
        fetch: (input, init) => fetchWithRecovery(input, init, { bufferResponse: true }),
        headers: {
          'x-application-name': 'ai-data-analyst-os',
        },
      },
    });
  } catch (error) {
    console.error('Failed to initialize Supabase client:', error);
    throw error;
  }

  return supabaseInstance;
}

/**
 * Default Supabase client instance for application services.
 */
export const supabase = getSupabaseClient();
