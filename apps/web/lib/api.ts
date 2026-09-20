/**
 * Client API centralisé pour ORBIT.
 * Base URL lue depuis NEXT_PUBLIC_API_URL (définie dans .env.local).
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Types ────────────────────────────────────────────────────────────────────

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface UserOut {
  id: string;
  email: string;
}

// ── Auth ─────────────────────────────────────────────────────────────────────

/**
 * Login via OAuth2PasswordRequestForm (form-encoded).
 * Retourne le JWT access_token.
 */
export async function loginUser(
  email: string,
  password: string
): Promise<TokenResponse> {
  const body = new URLSearchParams();
  body.append("username", email); // FastAPI OAuth2 attend "username"
  body.append("password", password);

  const res = await fetch(`${BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Erreur inconnue" }));
    throw new Error(err.detail ?? "Erreur de connexion");
  }

  return res.json();
}

/**
 * Inscription d'un nouvel utilisateur via /auth/register (JSON).
 * Retourne le UserOut.
 */
export async function registerUser(
  email: string,
  password: string
): Promise<UserOut> {
  const res = await fetch(`${BASE_URL}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Erreur inconnue" }));
    throw new Error(err.detail ?? "Erreur d'inscription");
  }

  return res.json();
}

/**
 * Wrapper fetch sécurisé avec token JWT automatique.
 * Redirige vers /login si le token est invalide ou expiré (401).
 */
export async function authFetch(
  endpoint: string,
  options: RequestInit = {}
): Promise<Response> {
  const token = getToken();
  const headers = new Headers(options.headers || {});

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(`${BASE_URL}${endpoint}`, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    removeToken();
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
  }

  return res;
}

// ── Token helpers ────────────────────────────────────────────────────────────

export const TOKEN_KEY = "orbit_token";

export function saveToken(token: string) {
  if (typeof window !== "undefined") localStorage.setItem(TOKEN_KEY, token);
}

export function getToken(): string | null {
  if (typeof window !== "undefined") return localStorage.getItem(TOKEN_KEY);
  return null;
}

export function removeToken() {
  if (typeof window !== "undefined") localStorage.removeItem(TOKEN_KEY);
}

/**
 * Récupère l'utilisateur courant via GET /auth/me.
 * Retourne null en cas d'erreur (token invalide, réseau, etc.)
 */
export async function getMe(): Promise<UserOut | null> {
  try {
    const res = await authFetch("/auth/me");
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}
