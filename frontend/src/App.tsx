import { useEffect, useRef, useState, type FormEvent } from "react";
import { exportFilename, exportLetter, fetchProviders, generateLetter, type ProviderInfo } from "./api";

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

// Slightly above the backend's worst case (2 attempts x 120s) so the server's own timeout error wins.
const CLIENT_TIMEOUT_MS = 260_000;

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
  const [company, setCompany] = useState("");
  const [role, setRole] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [pendingLabel, setPendingLabel] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  // Tick an elapsed-seconds counter while a generation is in flight.
  useEffect(() => {
    if (!loading) return;
    const started = Date.now();
    setElapsed(0);
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(id);
  }, [loading]);

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

    const controller = new AbortController();
    abortRef.current = controller;
    const timer = setTimeout(() => controller.abort("timeout"), CLIENT_TIMEOUT_MS);
    setPendingLabel(`${provider?.name ?? providerId} · ${model.trim() || provider?.default_model || ""}`);

    try {
      const result = await generateLetter(form, controller.signal);
      setLetter(result.cover_letter);
      setCompany(result.company);
      setRole(result.role);
      setUsedModel(`${provider?.name ?? result.provider} · ${result.model}`);
    } catch (err) {
      if (controller.signal.aborted) {
        setError(
          controller.signal.reason === "timeout"
            ? "The request timed out. The provider may be overloaded; try again or pick a faster model."
            : "Cancelled.",
        );
      } else {
        setError((err as Error).message);
      }
    } finally {
      clearTimeout(timer);
      abortRef.current = null;
      setLoading(false);
    }
  }

  function onCancel() {
    abortRef.current?.abort("cancelled");
  }

  async function onExport(format: "pdf" | "docx") {
    setError("");
    try {
      await exportLetter(letter, format, exportFilename(company, role, format));
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

        {loading ? (
          <div className="progress" role="status" aria-live="polite">
            <div className="progress-main">
              <span className="spinner" aria-hidden="true" />
              <div>
                <div>
                  <strong>Writing your cover letter</strong> <span className="muted">· {elapsed}s</span>
                </div>
                <div className="muted small">
                  {elapsed < 2 ? "Uploading files…" : `Waiting for ${pendingLabel}`}
                </div>
                {elapsed >= 30 && (
                  <div className="muted small">
                    Still working. Larger models can take a minute or more; it will time out after about 4 minutes.
                  </div>
                )}
              </div>
            </div>
            <button type="button" onClick={onCancel}>
              Cancel
            </button>
          </div>
        ) : (
          <button type="submit" className="primary" disabled={!canSubmit}>
            Generate cover letter
          </button>
        )}
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
            <label>
              Company
              <input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Company name" />
            </label>
            <label>
              Role
              <input value={role} onChange={(e) => setRole(e.target.value)} placeholder="Job title" />
            </label>
          </div>
          <p className="muted small">Saves as: {exportFilename(company, role, "pdf").slice(0, -".pdf".length)}.pdf / .docx</p>
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
