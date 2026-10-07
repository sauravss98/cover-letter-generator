export interface ProviderInfo {
  id: string;
  name: string;
  default_model: string;
  server_key_available: boolean;
}

export interface GenerateResult {
  cover_letter: string;
  company: string;
  role: string;
  provider: string;
  model: string;
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return body.detail.map((d: { msg: string }) => d.msg).join("; ");
  } catch {
    /* non-JSON error body */
  }
  return `Request failed (${res.status})`;
}

export async function fetchProviders(): Promise<ProviderInfo[]> {
  const res = await fetch("/api/providers");
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

export async function generateLetter(form: FormData, signal?: AbortSignal): Promise<GenerateResult> {
  const res = await fetch("/api/generate", { method: "POST", body: form, signal });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

// Characters not allowed in Windows/macOS file names, plus control characters.
const UNSAFE_FILENAME_CHARS = /[<>:"/\\|?*\u0000-\u001f]/g;

// Builds e.g. "Cover Letter - Acme Corp - Senior Engineer.pdf".
export function exportFilename(company: string, role: string, format: "pdf" | "docx"): string {
  const clean = (s: string) => s.replace(UNSAFE_FILENAME_CHARS, " ").replace(/\s+/g, " ").trim().slice(0, 80);
  const parts = ["Cover Letter", clean(company), clean(role)].filter(Boolean);
  // Windows rejects names ending in a dot or space.
  return `${parts.join(" - ").replace(/[. ]+$/, "")}.${format}`;
}

export async function exportLetter(text: string, format: "pdf" | "docx", filename: string): Promise<void> {
  const res = await fetch("/api/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, format }),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
