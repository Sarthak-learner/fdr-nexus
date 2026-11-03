import { useState, useEffect, useCallback } from "react";

let currentUser = null;

export const getUser = () => currentUser;
export const getRole = () => currentUser?.role || "";

function setUser(user) {
  currentUser = user || null;
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("fdr_auth_changed", { detail: currentUser }));
  }
}

function csrfToken() {
  if (typeof document === "undefined") return "";
  const entry = document.cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith("fdr_csrf="));
  return entry ? decodeURIComponent(entry.slice("fdr_csrf=".length)) : "";
}

function errorMessage(res, detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((e) => `${(e.loc || []).slice(1).join(".")}: ${e.msg}`).join("; ");
  return res.statusText || "Request failed";
}

export async function login(username, password) {
  const res = await fetch("/api/auth/login", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  let data = {};
  try { data = await res.json(); } catch {}
  if (!res.ok) throw new Error(errorMessage(res, data.detail));
  setUser(data.user);
  return data.user;
}

export async function logout() {
  await api("/auth/logout", { method: "POST" });
  setUser(null);
}

export async function api(path, { method = "GET", body, headers = {} } = {}) {
  const isForm = body instanceof FormData;
  const upperMethod = method.toUpperCase();
  const requestHeaders = { ...headers };
  if (body && !isForm) requestHeaders["Content-Type"] = "application/json";
  if (!["GET", "HEAD", "OPTIONS"].includes(upperMethod)) {
    const token = csrfToken();
    if (token) requestHeaders["X-CSRF-Token"] = token;
  }
  const res = await fetch("/api" + path, {
    method,
    credentials: "include",
    headers: requestHeaders,
    body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
  });
  if (res.status === 401 && !path.startsWith("/auth/login")) {
    setUser(null);
    if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent("fdr_auth_expired"));
  }
  if (!res.ok) {
    let detail;
    try { detail = (await res.json()).detail; } catch {}
    throw new Error(errorMessage(res, detail));
  }
  if (res.status === 204) return null;
  return res.json();
}

export function useFetch(path) {
  const [state, set] = useState({ data: null, error: null, loading: true });
  const load = useCallback(() => {
    set((s) => ({ ...s, loading: true }));
    api(path).then((data) => set({ data, error: null, loading: false }))
      .catch((error) => set({ data: null, error: error.message, loading: false }));
  }, [path]);

  useEffect(load, [load]);
  useEffect(() => {
    const handleAuth = () => load();
    window.addEventListener("fdr_auth_changed", handleAuth);
    return () => window.removeEventListener("fdr_auth_changed", handleAuth);
  }, [load]);

  return { ...state, reload: load };
}

export function useAuth() {
  const [state, setState] = useState({ user: currentUser, loading: !currentUser });
  useEffect(() => {
    let active = true;
    const onChange = (event) => setState({ user: event.detail || null, loading: false });
    const onExpired = () => setState({ user: null, loading: false });
    window.addEventListener("fdr_auth_changed", onChange);
    window.addEventListener("fdr_auth_expired", onExpired);
    if (!currentUser) {
      api("/auth/me")
        .then((data) => { if (active) setUser(data.user); })
        .catch(() => { if (active) setState({ user: null, loading: false }); });
    }
    return () => {
      active = false;
      window.removeEventListener("fdr_auth_changed", onChange);
      window.removeEventListener("fdr_auth_expired", onExpired);
    };
  }, []);
  return state;
}
