import { useEffect, useState, type FormEvent } from "react";
import { exportLetter, fetchProviders, generateLetter, type ProviderInfo } from "./api";

// Keys are stored only in this browser (opt-in) and sent to our backend per request;
// the backend never persists them.
const keyStorageId = (provider: string) => `clg.apiKey.${provider}`;
const PROVIDER_STORAGE_ID = "clg.provider";

function readStorage(id: string): string {
  try {
    return localStorage.getItem(id) ?? "";
  } catch {
    return "";
  }
}

function writeStorage(id: string, value: string | null) {
  try {
    if (value) localStorage.setItem(id, value);
    else localStorage.removeItem(id);
  } catch {
    /* storage unavailable (private mode etc.) */
  }
}

const KEY_HELP: Record<string, string> = {
  anthropic: "https://console.anthropic.com/settings/keys",
  openai: "https://platform.openai.com/api-keys",
  gemini: "https://aistudio.google.com/apikey",
};

export default function App() {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [providerId, setProviderId] = useState(readStorage(PROVIDER_STORAGE_ID) || "anthropic");
  const [apiKey, setApiKey] = useState("");
  const [rememberKey, setRememberKey] = useState(false);
  const [model, setModel] = useState("");

  const [resume, setResume] = useState<File | null>(null);
  const [jdMode, setJdMode] = useState<"text" | "file">("text");
  const [jdText, setJdText] = useState("");
  const [jdFile, setJdFile] = useState<File | null>(null);
  const [instructions, setInstructions] = useState("");

  const [letter, setLetter] = useState("");
  const [usedModel, setUsedModel] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchProviders()
      .then(setProviders)
      .catch((e) => setError(`Could not reach the backend: ${e.message}`));
  }, []);

  // Load the saved key (if any) whenever the provider changes.
  useEffect(() => {
    const saved = readStorage(keyStorageId(providerId));
    setApiKey(saved);
    setRememberKey(Boolean(saved));
    setModel("");
    writeStorage(PROVIDER_STORAGE_ID, providerId);
  }, [providerId]);

  const provider = providers.find((p) => p.id === providerId);
  const keyOptional = provider?.server_key_available ?? false;
  const canSubmit =
    !loading &&
    resume !== null &&
    (jdMode === "text" ? jdText.trim() !== "" : jdFile !== null) &&
    (apiKey.trim() !== "" || keyOptional);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!resume) return;
    setError("");
    setLoading(true);
    writeStorage(keyStorageId(providerId), rememberKey ? apiKey.trim() : null);

    const form = new FormData();
    form.append("resume", resume);
    if (jdMode === "file" && jdFile) form.append("jd_file", jdFile);
    else form.append("jd_text", jdText);
    if (instructions.trim()) form.append("instructions", instructions);
    form.append("provider", providerId);
    if (apiKey.trim()) form.append("api_key", apiKey.trim());
    if (model.trim()) form.append("model", model.trim());

    try {
      const result = await generateLetter(form);
      setLetter(result.cover_letter);
      setUsedModel(`${provider?.name ?? result.provider} · ${result.model}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function onExport(format: "pdf" | "docx") {
    setError("");
    try {
      await exportLetter(letter, format);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <main className="container">
      <header>
        <h1>Cover Letter Generator</h1>
        <p className="muted">Upload your resume and a job description to get a tailored cover letter.</p>
      </header>

      <form onSubmit={onSubmit} className="card">
        <fieldset>
          <legend>AI provider</legend>
          <div className="row">
            <label>
              Provider
              <select value={providerId} onChange={(e) => setProviderId(e.target.value)}>
                {providers.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Model <span className="muted">(optional)</span>
              <input
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder={provider?.default_model ?? ""}
              />
            </label>
          </div>
          <label>
            API key{" "}
            {keyOptional && <span className="muted">(optional — the server has a default key)</span>}
            <input
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={`Your ${provider?.name ?? ""} API key`}
            />
          </label>
          <div className="row between">
            <label className="inline">
              <input
                type="checkbox"
                checked={rememberKey}
                onChange={(e) => setRememberKey(e.target.checked)}
              />
              Remember key in this browser
            </label>
            {KEY_HELP[providerId] && (
              <a href={KEY_HELP[providerId]} target="_blank" rel="noreferrer">
                Get a key
              </a>
            )}
          </div>
        </fieldset>

        <fieldset>
          <legend>Resume</legend>
          <input
            type="file"
            accept=".pdf,.docx,.txt,.md"
            onChange={(e) => setResume(e.target.files?.[0] ?? null)}
          />
          <p className="muted small">PDF, DOCX, or TXT, up to 10 MB.</p>
        </fieldset>

        <fieldset>
          <legend>Job description</legend>
          <div className="tabs">
            <button type="button" className={jdMode === "text" ? "active" : ""} onClick={() => setJdMode("text")}>
              Paste text
            </button>
            <button type="button" className={jdMode === "file" ? "active" : ""} onClick={() => setJdMode("file")}>
              Upload file
            </button>
          </div>
          {jdMode === "text" ? (
            <textarea
              rows={8}
              value={jdText}
              onChange={(e) => setJdText(e.target.value)}
              placeholder="Paste the job description here"
            />
          ) : (
            <input
              type="file"
              accept=".pdf,.docx,.txt,.md"
              onChange={(e) => setJdFile(e.target.files?.[0] ?? null)}
            />
          )}
        </fieldset>

        <fieldset>
          <legend>
            Extra instructions <span className="muted">(optional)</span>
          </legend>
          <textarea
            rows={2}
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            placeholder="e.g. Keep it under 300 words, emphasise leadership experience"
          />
        </fieldset>

        <button type="submit" className="primary" disabled={!canSubmit}>
          {loading ? "Writing your cover letter…" : "Generate cover letter"}
        </button>
      </form>

      {error && <div className="error" role="alert">{error}</div>}

      {letter && (
        <section className="card">
          <div className="row between">
            <h2>Your cover letter</h2>
            <span className="muted small">{usedModel}</span>
          </div>
          <p className="muted small">Edit the text below before downloading.</p>
          <textarea className="letter" rows={20} value={letter} onChange={(e) => setLetter(e.target.value)} />
          <div className="row">
            <button type="button" onClick={() => onExport("pdf")} disabled={!letter.trim()}>
              Download PDF
            </button>
            <button type="button" onClick={() => onExport("docx")} disabled={!letter.trim()}>
              Download Word
            </button>
            <button type="button" onClick={() => navigator.clipboard.writeText(letter)}>
              Copy
            </button>
          </div>
        </section>
      )}
    </main>
  );
}
