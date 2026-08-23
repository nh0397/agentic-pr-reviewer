"use client";

import { useCallback, useEffect, useState } from "react";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// Every call needs this so the session cookie set at login actually gets
// sent, the frontend and backend are different origins as far as the
// browser's cookie rules are concerned.
export const fetchOpts: RequestInit = { credentials: "include" };

export type User = {
  id: number;
  username: string;
  avatar_url: string | null;
};

/**
 * Single source of truth for "who is logged in," shared by the login page
 * (redirects away if already logged in) and the dashboard (redirects away
 * if not), so both routes agree on the same fetch and the same edge cases
 * instead of each guessing independently.
 */
export function useSession() {
  const [user, setUser] = useState<User | null>(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [backendUnreachable, setBackendUnreachable] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/auth/me`, fetchOpts);
      setUser(res.ok ? await res.json() : null);
      setBackendUnreachable(false);
    } catch {
      setBackendUnreachable(true);
    } finally {
      setCheckingSession(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function logout() {
    await fetch(`${API_BASE_URL}/api/auth/logout`, { ...fetchOpts, method: "POST" });
    setUser(null);
  }

  return { user, checkingSession, backendUnreachable, refresh, logout };
}
