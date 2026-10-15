/**
 * Authentication service powered by Supabase Authentication.
 *
 * Implements:
 * - login: supabase.auth.signInWithPassword -> stores session token -> syncs backend
 * - signup: supabase.auth.signUp with full_name metadata
 * - logout: supabase.auth.signOut -> clears local auth state
 * - getCurrentUser: supabase.auth.getUser -> returns mapped User profile
 * - forgotPassword: supabase.auth.resetPasswordForEmail
 * - resetPassword: supabase.auth.updateUser({ password })
 * - updateProfile: supabase.auth.updateUser + profiles table update
 */

import { supabase, isSupabaseConfigured } from '../lib/supabase/client';
import { apiClient, clearAuthToken, setAuthToken } from '../api/client';
import type {
  ForgotPasswordRequest,
  LoginRequest,
  ResetPasswordRequest,
  SignupRequest,
  UpdateProfileRequest,
  User,
} from '../types/auth';

interface BackendUserResponse {
  id: string;
  email: string;
  full_name: string;
  role?: string;
  is_active?: boolean;
}

function mapUserResponse(user: BackendUserResponse): User {
  return {
    id: user.id,
    email: user.email,
    full_name: user.full_name,
    created_at: new Date().toISOString(),
  };
}

export const authService = {
  /**
   * Log in user using email and password via Supabase Auth.
   */
  async login(data: LoginRequest): Promise<User> {
    if (isSupabaseConfigured()) {
      const { data: authData, error } = await supabase.auth.signInWithPassword({
        email: data.email,
        password: data.password,
      });

      if (error) {
        if (error.message.includes('Email not confirmed')) {
          throw new Error('Please confirm your email address. Check your inbox for the confirmation link.');
        }
        if (error.message.includes('Invalid login credentials')) {
          throw new Error('Invalid email or password. Please verify and try again.');
        }
        throw new Error(error.message);
      }

      if (!authData.user || !authData.session) {
        throw new Error('Authentication succeeded but no active session was returned.');
      }

      // Persist the Supabase JWT token for backend API authorization headers
      setAuthToken(authData.session.access_token);

      const user: User = {
        id: authData.user.id,
        email: authData.user.email || data.email,
        full_name:
          authData.user.user_metadata?.full_name ||
          authData.user.user_metadata?.name ||
          data.email.split('@')[0],
        created_at: authData.user.created_at || new Date().toISOString(),
      };

      return user;
    }

    // Fallback to local FastAPI auth if Supabase is disabled
    const res = await apiClient.post<{ access_token: string }>('/api/v1/auth/login', {
      email: data.email,
      password: data.password,
    });
    setAuthToken(res.access_token);
    const userRes = await apiClient.get<BackendUserResponse>('/api/v1/auth/me');
    return mapUserResponse(userRes);
  },

  /**
   * Register a new user with Supabase Auth.
   */
  async signup(data: SignupRequest): Promise<User> {
    if (isSupabaseConfigured()) {
      const { data: authData, error } = await supabase.auth.signUp({
        email: data.email,
        password: data.password,
        options: {
          data: {
            full_name: data.full_name,
          },
        },
      });

      if (error) {
        if (error.message.includes('User already registered')) {
          throw new Error('An account with this email address already exists. Please log in.');
        }
        throw new Error(error.message);
      }

      if (!authData.user) {
        throw new Error('Registration failed. Please try again.');
      }

      if (authData.session) {
        setAuthToken(authData.session.access_token);
      }

      const user: User = {
        id: authData.user.id,
        email: authData.user.email || data.email,
        full_name: data.full_name,
        created_at: authData.user.created_at || new Date().toISOString(),
      };

      return user;
    }

    const userRes = await apiClient.post<BackendUserResponse>('/api/v1/auth/register', {
      email: data.email,
      password: data.password,
      full_name: data.full_name,
    });
    return mapUserResponse(userRes);
  },

  /**
   * Log out the current user and revoke session tokens.
   */
  async logout(): Promise<void> {
    try {
      if (isSupabaseConfigured()) {
        await supabase.auth.signOut();
      } else {
        await apiClient.post('/api/v1/auth/logout', {});
      }
    } catch {
      // Always proceed with local token removal even if remote logout fails
    } finally {
      clearAuthToken();
    }
  },

  /**
   * Retrieve the currently authenticated user from Supabase or the backend session.
   */
  async getCurrentUser(): Promise<User> {
    if (isSupabaseConfigured()) {
      const { data: { user }, error } = await supabase.auth.getUser();

      if (error || !user) {
        throw new Error('No active authenticated session.');
      }

      return {
        id: user.id,
        email: user.email || '',
        full_name:
          user.user_metadata?.full_name ||
          user.user_metadata?.name ||
          (user.email ? user.email.split('@')[0] : 'Analyst'),
        created_at: user.created_at || new Date().toISOString(),
      };
    }

    const userRes = await apiClient.get<BackendUserResponse>('/api/v1/auth/me');
    return mapUserResponse(userRes);
  },

  /**
   * Request password reset instructions via Supabase Auth.
   */
  async forgotPassword(data: ForgotPasswordRequest): Promise<void> {
    if (isSupabaseConfigured()) {
      const redirectTo = typeof window !== 'undefined'
        ? `${window.location.origin}/login`
        : undefined;

      const { error } = await supabase.auth.resetPasswordForEmail(data.email, {
        redirectTo,
      });

      if (error) {
        throw new Error(error.message);
      }
      return;
    }

    throw new Error('Password reset is not configured for this environment.');
  },

  /**
   * Reset the current user's password using Supabase Auth.
   */
  async resetPassword(data: ResetPasswordRequest): Promise<void> {
    if (isSupabaseConfigured()) {
      const { error } = await supabase.auth.updateUser({
        password: data.new_password,
      });

      if (error) {
        throw new Error(error.message);
      }
      return;
    }

    throw new Error('Password update is not configured for this environment.');
  },

  /**
   * Fetch user profile.
   */
  getProfile(): Promise<User> {
    return this.getCurrentUser();
  },

  /**
   * Update user profile information.
   */
  async updateProfile(data: UpdateProfileRequest): Promise<User> {
    if (isSupabaseConfigured()) {
      const { data: updated, error } = await supabase.auth.updateUser({
        data: {
          full_name: data.full_name,
        },
      });

      if (error) {
        throw new Error(error.message);
      }

      if (!updated.user) {
        throw new Error('Profile update returned no user data.');
      }

      // Also attempt updating the public.profiles record if table exists
      try {
        await supabase
          .from('profiles')
          .update({
            full_name: data.full_name,
            updated_at: new Date().toISOString(),
          } as Record<string, unknown>)
          .eq('id', updated.user.id);
      } catch {
        // Ignored if profiles table is not yet migrated
      }

      return {
        id: updated.user.id,
        email: updated.user.email || '',
        full_name: data.full_name || updated.user.user_metadata?.full_name || '',
        created_at: updated.user.created_at || new Date().toISOString(),
      };
    }

    throw new Error('Profile update is not supported in this environment.');
  },
};
