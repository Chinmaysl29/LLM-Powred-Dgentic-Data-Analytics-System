/**
 * Frontend authentication domain types.
 *
 * These define the contract between the UI layer and the auth service
 * boundary. Exact field names will be reconciled with the backend once
 * auth endpoints are implemented.
 *
 * BACKEND DEPENDENCY: No backend auth endpoints exist yet.
 * All types here represent the anticipated frontend domain model.
 */

// ---------------------------------------------------------------------------
// Request types — what the UI sends to the auth service
// ---------------------------------------------------------------------------

export interface LoginRequest {
  email: string;
  password: string;
}

export interface SignupRequest {
  email: string;
  password: string;
  full_name: string;
}

export interface ForgotPasswordRequest {
  email: string;
}

export interface ResetPasswordRequest {
  token: string;
  new_password: string;
}

export interface UpdateProfileRequest {
  full_name?: string;
  email?: string;
}

// ---------------------------------------------------------------------------
// Domain types — frontend representation of backend entities
// ---------------------------------------------------------------------------

export interface User {
  id: string;
  email: string;
  full_name: string;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Response types
// ---------------------------------------------------------------------------
// The authentication transport/session response (e.g. token-based,
// cookie-based) depends on the backend implementation which is not
// yet finalized. Response types will be added once the backend auth
// contract is established. Do not prematurely define AuthResponse,
// token structures, or session shapes here.
