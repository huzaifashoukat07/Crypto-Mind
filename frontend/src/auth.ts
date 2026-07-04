const STORAGE_KEY = "cryptomind_api_token";

export function getApiToken(): string {
  return localStorage.getItem(STORAGE_KEY) ?? "";
}

export function setApiToken(token: string): void {
  if (token) {
    localStorage.setItem(STORAGE_KEY, token);
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }
}

export function authHeaders(): Record<string, string> {
  const token = getApiToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
