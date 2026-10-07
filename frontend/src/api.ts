export interface ProviderInfo {
  id: string;
  name: string;
  default_model: string;
  server_key_available: boolean;
}

export interface GenerateResult {
  cover_letter: string;
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

export async function generateLetter(form: FormData): Promise<GenerateResult> {
  const res = await fetch("/api/generate", { method: "POST", body: form });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

export async function exportLetter(text: string, format: "pdf" | "docx"): Promise<void> {
  const res = await fetch("/api/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, format }),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = `cover_letter.${format}`;
  a.click();
  URL.revokeObjectURL(url);
}
