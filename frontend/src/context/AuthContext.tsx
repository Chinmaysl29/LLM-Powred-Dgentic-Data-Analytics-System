/* eslint-disable react-refresh/only-export-components */
/**
 * AuthContext â€” Frontend authentication state boundary.
 *
 * Manages Supabase authentication state, user session, and token persistence
 * synchronized with backend API authorization headers.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { supabase, isSupabaseConfigured } from '../lib/supabase/client';
import { clearAuthToken, setAuthToken } from '../api/client';
import { authService } from '../services/authService';
import type { LoginRequest, SignupRequest, User } from '../types/auth';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AuthContextValue {
  /** True when the user has passed the authentication boundary. */
  isAuthenticated: boolean;

  /** Current authenticated user profile or null if not authenticated. */
  user: User | null;

  /** Authenticate with email & password. */
  login: (data: LoginRequest) => Promise<User>;

  /** Register a new user. */
  signup: (data: SignupRequest) => Promise<User>;

  /** Loading state while checking session validity on initial load. */
  isLoading: boolean;

  /** Error message if initial session retrieval failed. */
  sessionError: string | null;

  /** Retry session verification. */
  retrySession: () => void;

  /** Clear the authentication state and sign out. */
  signOut: () => void;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const AuthContext = createContext<AuthContextValue | null>(null);

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [sessionAttempt, setSessionAttempt] = useState(0);
  const [user, setUser] = useState<User | null>(null);

  const retrySession = useCallback(() => {
    setIsLoading(true);
    setSessionError(null);
    setSessionAttempt((n) => n + 1);
  }, []);

  useEffect(() => {
    let active = true;

    if (!isSupabaseConfigured()) {
      // Local fallback mode
      authService
        .getCurrentUser()
        .then((fetchedUser) => {
          if (!active) return;
          setUser(fetchedUser);
          setIsAuthenticated(true);
        })
        .catch(() => {
          if (!active) return;
          setUser(null);
          setIsAuthenticated(false);
        })
        .finally(() => {
          if (active) setIsLoading(false);
        });
      return () => {
        active = false;
      };
    }

    // An auth event supersedes a pending initial session read (including logout).
    let authEventVersion = 0;
    const sessionTimer = setTimeout(() => {
      if (!active || authEventVersion !== 0) return;
      clearAuthToken();
      setIsAuthenticated(false);
      setUser(null);
      setSessionError('Session verification timed out. Please retry.');
      setIsLoading(false);
    }, 15_000);

    // 1. Initial Session Check from Supabase
    supabase.auth
      .getSession()
      .then(({ data: { session }, error }) => {
        if (!active || authEventVersion !== 0) return;
        clearTimeout(sessionTimer);
        if (error) {
          setSessionError(error.message);
          setIsAuthenticated(false);
          setUser(null);
          clearAuthToken();
        } else if (session?.user) {
          setSessionError(null);
          setAuthToken(session.access_token);
          setUser({
            id: session.user.id,
            email: session.user.email || '',
            full_name:
              session.user.user_metadata?.full_name ||
              session.user.user_metadata?.name ||
              (session.user.email ? session.user.email.split('@')[0] : 'Analyst'),
            created_at: session.user.created_at || new Date().toISOString(),
          });
          setIsAuthenticated(true);
        } else {
          setIsAuthenticated(false);
          setUser(null);
          clearAuthToken();
        }
      })
      .catch((err: unknown) => {
        if (!active || authEventVersion !== 0) return;
        clearAuthToken();
        setSessionError(err instanceof Error ? err.message : 'Session service is unavailable.');
        setIsAuthenticated(false);
        setUser(null);
      })
      .finally(() => {
        clearTimeout(sessionTimer);
        if (active) setIsLoading(false);
      });

    // 2. Real-time Auth State Change Listener
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!active) return;
      authEventVersion++;
      clearTimeout(sessionTimer);
      setSessionError(null);
      if (session?.user) {
        setAuthToken(session.access_token);
        setUser({
          id: session.user.id,
          email: session.user.email || '',
          full_name:
            session.user.user_metadata?.full_name ||
            session.user.user_metadata?.name ||
            (session.user.email ? session.user.email.split('@')[0] : 'Analyst'),
          created_at: session.user.created_at || new Date().toISOString(),
        });
        setIsAuthenticated(true);
        setIsLoading(false);
      } else {
        clearAuthToken();
        setUser(null);
        setIsAuthenticated(false);
        setIsLoading(false);
      }
    });

    return () => {
      active = false;
      clearTimeout(sessionTimer);
      subscription.unsubscribe();
    };
  }, [sessionAttempt]);

  const login = useCallback(async (data: LoginRequest) => {
    const loggedInUser = await authService.login(data);
    setUser(loggedInUser);
    setIsAuthenticated(true);
    return loggedInUser;
  }, []);

  const signup = useCallback(async (data: SignupRequest) => {
    return await authService.signup(data);
  }, []);

  const signOut = useCallback(() => {
    void authService.logout();
    setUser(null);
    setIsAuthenticated(false);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      isAuthenticated,
      user,
      isLoading,
      sessionError,
      retrySession,
      signOut,
      login,
      signup,
    }),
    [isAuthenticated, user, isLoading, sessionError, retrySession, signOut, login, signup],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return ctx;
}
