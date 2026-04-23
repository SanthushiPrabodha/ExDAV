import React, { useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import "./App.css";

// Production default when REACT_APP_BACKEND_URL was not set at build time
// (Vercel env misconfiguration). Override via Vercel env, public/config.js, or
// window.__EXDAV_BACKEND_URL__.
const VERCEL_HOST_DEFAULT_BACKEND = "https://p01--exdav--2rlz8sczq2qc.code.run";

/**
 * API origin (no trailing slash). Resolution order:
 *   1. REACT_APP_BACKEND_URL (build-time)
 *   2. window.__EXDAV_BACKEND_URL__ (runtime, set in public/config.js)
 *   3. When served from ex-dav.vercel.app and no env — Northflank default above
 *   4. Local dev fallback
 */
function resolveBackendBaseUrl() {
  const fromEnv = (process.env.REACT_APP_BACKEND_URL || "").trim().replace(/\/$/, "");
  if (fromEnv) return fromEnv;

  if (typeof window !== "undefined") {
    const w = (window.__EXDAV_BACKEND_URL__ || "").toString().trim().replace(/\/$/, "");
    if (w) return w;
    if (window.location && window.location.hostname === "ex-dav.vercel.app") {
      return VERCEL_HOST_DEFAULT_BACKEND.replace(/\/$/, "");
    }
  }
  return "http://127.0.0.1:8000";
}

// Silent warm-up + cold-start handling for Render free tier.
// The backend can take 30–90+ seconds to wake up, then run heavy OCR/reasoning.
// We warm the service on mount; the analyze call retries with a progressive
// delay so the user never sees infrastructure details.
const WARMUP_TIMEOUT_MS = 90000;    // health-check timeout
const ANALYZE_TIMEOUT_MS = 300000;  // single analyze attempt timeout (5 min)
const MAX_RETRIES = 2;              // up to 2 retries = 3 total attempts

const VERDICT_META = {
  authentic:    { cls: "verdict-authentic",    icon: "✔", label: "Authentic" },
  suspicious:   { cls: "verdict-suspicious",   icon: "⚠", label: "Suspicious" },
  counterfeit:  { cls: "verdict-counterfeit",  icon: "✕", label: "Counterfeit" },
  inconclusive: { cls: "verdict-inconclusive", icon: "?", label: "Inconclusive" },
};

function getVerdictMeta(verdict) {
  return VERDICT_META[(verdict || "").toLowerCase()] || VERDICT_META.inconclusive;
}

const REQUIRED_METADATA = ["drug_name", "batch_number", "expiry_date", "manufacturer"];
const METADATA_LABELS = {
  drug_name:         "Drug Name",
  dosage:            "Dosage / Strength",
  manufacturer:      "Manufacturer",
  batch_number:      "Batch Number",
  manufactured_date: "Manufactured Date",
  expiry_date:       "Expiry Date",
  detected_logos:    "Detected Brand Logos",
};

const NMRA_RECORD_LABELS = {
  generic_name: "Generic Name",
  brand: "Brand",
  dosage: "Dosage",
  pack_size: "Pack Size",
  pack_type: "Pack Type",
  manufacturer: "Manufacturer (NMRA registered)",
  country: "Country",
  agent: "Agent (Distributor)",
  reg_date: "Registration Date",
  reg_no: "Registration Number",
  schedule: "Schedule",
  validation_status: "Validation Status",
  dossier_no: "Dossier Number",
};

function MetaField({ fieldKey, value }) {
  const isMissing = REQUIRED_METADATA.includes(fieldKey) && !value;
  const display =
    fieldKey === "detected_logos"
      ? Array.isArray(value) && value.length > 0
        ? value.join(", ")
        : null
      : value || null;

  return (
    <p className={isMissing ? "meta-row meta-missing" : "meta-row"}>
      <span className="meta-label">{METADATA_LABELS[fieldKey] || fieldKey}:</span>{" "}
      {display ?? <em className="missing-tag">Not detected</em>}
    </p>
  );
}

function GuidelineBadge({ guideline, status }) {
  const cls = status === "passed" ? "badge badge-pass" : "badge badge-fail";
  return <span className={cls}>{guideline}</span>;
}

function OcrToggle({ text }) {
  const [open, setOpen] = useState(false);
  if (!text) return null;
  return (
    <div className="ocr-block">
      <button className="toggle-btn" onClick={() => setOpen((o) => !o)}>
        {open ? "▲ Hide raw OCR text" : "▼ Show raw OCR text"}
      </button>
      {open && <pre className="ocr-pre">{text}</pre>}
    </div>
  );
}

function NMRABadge({ status }) {
  const cls =
    status === "Registered"
      ? "badge badge-pass"
      : status === "Not Found"
      ? "badge badge-fail"
      : "badge badge-warn";
  return <span className={cls}>{status === "Registered" ? "✔ NMRA Registered" : status === "Not Found" ? "✕ Not in NMRA" : "? NMRA Unavailable"}</span>;
}

function MatchBadge({ match }) {
  return match
    ? <span className="badge badge-pass">✔ Manufacturer Verified</span>
    : <span className="badge badge-fail">✕ Manufacturer Mismatch</span>;
}

function ValidationComparison({ nmra }) {
  if (!nmra || !nmra.validation) return null;
  const v = nmra.validation;
  const row = (label, val) => (
    <p className="meta-row">
      <span className="meta-label">{label}:</span>{" "}
      {val === true && <span className="badge badge-pass">✔ Match</span>}
      {val === false && <span className="badge badge-fail">✕ Mismatch</span>}
      {(val === null || val === undefined) && (
        <em className="missing-tag">Not compared</em>
      )}
    </p>
  );
  return (
    <section className="card nmra-validation-card">
      <h3>Validation Comparison</h3>
      <p className="section-hint">
        Packaging OCR vs the NMRA line selected for this analysis (manufacturer is a strong
        signal for picking the correct registration when several products share the same
        ingredient).
      </p>
      <p className="meta-row">
        <span className="meta-label">Manufacturer (packaging):</span>{" "}
        {nmra.extracted_manufacturer ? (
          <span>{nmra.extracted_manufacturer}</span>
        ) : (
          <em className="missing-tag">Not detected</em>
        )}
      </p>
      <p className="meta-row">
        <span className="meta-label">Manufacturer (NMRA registration):</span>{" "}
        {nmra.nmra_manufacturer ? (
          <span>{nmra.nmra_manufacturer}</span>
        ) : (
          <em className="missing-tag">—</em>
        )}
      </p>
      {row("Manufacturer consistency", v.manufacturer_match)}
      {row("Brand", v.brand_match)}
      {row("Dosage", v.dosage_match)}
    </section>
  );
}

function NmraVerifiedSection({ nmra }) {
  if (!nmra) return null;
  const ds = nmra.display_status || "";
  const rec = nmra.record || {};
  const approved = ds === "APPROVED";
  const notFound = ds === "NOT FOUND";

  return (
    <section className="card nmra-card">
      <h3>NMRA Verified Data</h3>
      <div
        className={
          "nmra-banner " +
          (approved ? "nmra-banner-ok" : notFound ? "nmra-banner-bad" : "nmra-banner-warn")
        }
      >
        {approved && (
          <>
            <span className="nmra-status-icon">✅</span> Status: <strong>APPROVED</strong>
            <span className="nmra-sub"> — product found in NMRA registry</span>
          </>
        )}
        {notFound && (
          <>
            <span className="nmra-status-icon">❌</span> Status: <strong>NOT FOUND</strong>
            <span className="nmra-sub"> — not listed in NMRA database</span>
          </>
        )}
        {!approved && !notFound && (
          <>
            <span className="nmra-status-icon">⚠</span> Status:{" "}
            <strong>{ds || nmra.status || "UNAVAILABLE"}</strong>
          </>
        )}
      </div>

      {notFound && (
        <p className="nmra-alert">
          This drug is not found in the NMRA registered database. Treat as suspicious until
          verified with NMRA.
        </p>
      )}

      {approved && nmra.record && (
        <div className="nmra-record-grid">
          {Object.entries(NMRA_RECORD_LABELS).map(([key, label]) => (
            <p key={key} className="meta-row">
              <span className="meta-label">{label}:</span>{" "}
              {rec[key] ? (
                <span>{rec[key]}</span>
              ) : (
                <em className="missing-tag">—</em>
              )}
            </p>
          ))}
        </div>
      )}

      {nmra.match_type && (
        <p className="nmra-meta-line">
          <span className="meta-label">Match method:</span> {nmra.match_type}{" "}
          {typeof nmra.match_score === "number" && (
            <span className="nmra-score"> (score {(nmra.match_score * 100).toFixed(0)}%)</span>
          )}
        </p>
      )}
      {approved && nmra.match_note && (
        <p className="nmra-match-note">{nmra.match_note}</p>
      )}
    </section>
  );
}

function isColdStartError(err) {
  if (!err) return false;
  if (err.code === "ECONNABORTED") return true;
  if (!err.response) return true;
  const s = err.response.status;
  return s === 502 || s === 503 || s === 504;
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function App() {
  const [files, setFiles] = useState([]);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [apiCheck, setApiCheck] = useState("checking");
  const didWarmupRef = useRef(false);

  const backendBase = useMemo(() => resolveBackendBaseUrl(), []);
  const analyzeUrl = `${backendBase}/analyze`;
  const healthUrl = `${backendBase}/`;

  useEffect(() => {
    if (didWarmupRef.current) return;
    didWarmupRef.current = true;
    // Fire-and-forget warm-up; also record reachability for on-page debugging.
    axios
      .get(healthUrl, { timeout: WARMUP_TIMEOUT_MS })
      .then(() => setApiCheck("ok"))
      .catch((err) => {
        console.warn("Backend warm-up ping failed:", err?.code || err?.message);
        setApiCheck(err?.code || err?.message || "failed");
      });
  }, [healthUrl]);

  const handleFileChange = (e) => {
    const selected = Array.from(e.target.files || []);
    if (selected.length > 5) {
      setError("Maximum 5 images allowed. Please select up to 5 images.");
      return;
    }
    setFiles(selected);
    setError("");
  };

  // Do NOT set Content-Type for FormData — the browser must add the
  // multipart boundary. A bare "multipart/form-data" header breaks uploads
  // and often surfaces as "Network Error" with no err.response.
  const postAnalyze = (formData, currentTimeout = ANALYZE_TIMEOUT_MS) =>
    axios.post(analyzeUrl, formData, { timeout: currentTimeout });

  const handleUpload = async () => {
    if (!files.length) {
      setError("Please select at least one image.");
      return;
    }

    const formData = new FormData();
    files.forEach((f) => formData.append("images", f));

    setLoading(true);
    setError("");
    setResult(null);

    let attempt = 0;
    const maxAttempts = MAX_RETRIES + 1;

    while (attempt < maxAttempts) {
      try {
        const response = await postAnalyze(formData);
        setResult(response.data);
        setLoading(false);
        return;                    // Success → exit loop
      } catch (err) {
        attempt++;
        console.warn(`Attempt ${attempt}/${maxAttempts} failed:`, err?.code || err?.message);

        if (attempt < maxAttempts && isColdStartError(err)) {
          // Progressive delay on cold start (6s → 12s)
          const delay = attempt * 6000;
          console.warn(`Cold start detected — retrying in ${delay}ms...`);
          await sleep(delay);
          continue;
        }

        // Final failure after all retries
        console.error("FULL ERROR after retries:", err);
        setError(friendlyErrorMessage(err, backendBase));
        break;
      }
    }

    setLoading(false);
  };

  const friendlyErrorMessage = (err, baseUrl) => {
    if (err?.response?.data) {
      const exp = err.response.data.explanation;
      if (exp) return Array.isArray(exp) ? exp.join(" ") : exp;
      return "We couldn't complete the analysis. Please try again.";
    }
    const hint = [err?.code, err?.message].filter(Boolean).join(" — ");
    const corsHint =
      (err?.message || "").toLowerCase().includes("network") ||
      err?.code === "ERR_NETWORK"
        ? " On the server, set EXDAV_ALLOWED_ORIGINS to https://ex-dav.vercel.app (or *)."
        : "";
    return (
      "We couldn't reach the analysis service. " +
      (hint ? `(${hint}) ` : "") +
      `Trying API: ${baseUrl}. If this is wrong, set REACT_APP_BACKEND_URL on Vercel or edit public/config.js and redeploy.` +
      (corsHint ? ` ${corsHint}` : "")
    );
  };

  const vm = result ? getVerdictMeta(result.verdict) : null;

  return (
    <div className="page">
      <div className="container">

        <header className="hero card">
          <h1>Ex-DAV</h1>
          <p>Explainable Drug Authenticity Verification</p>
        </header>

        {/* ── Upload ── */}
        <section className="card">
          <h2>Upload Drug Package Image(s)</h2>
          <p className="upload-hint">
            Upload 1–5 images of the same package (front, back, sides) for the most complete analysis.
          </p>
          <p className="upload-hint api-status-line">
            API: {backendBase}
            {" — "}
            {apiCheck === "checking"
              ? "checking reachability…"
              : apiCheck === "ok"
              ? "reachable"
              : `unreachable (${apiCheck})`}
          </p>
          <div className="upload-row">
            <input
              type="file"
              accept="image/*"
              multiple
              onChange={handleFileChange}
            />
            <button onClick={handleUpload} disabled={loading}>
              {loading ? "Analyzing..." : "Analyze"}
            </button>
          </div>
          {files.length > 0 && (
            <p className="upload-count">
              {files.length} image{files.length > 1 ? "s" : ""} selected:{" "}
              {files.map((f) => f.name).join(", ")}
            </p>
          )}
          {error && <p className="error">{error}</p>}
        </section>

        {/* ── Processing ── */}
        {loading && (
          <section className="card processing">
            <div className="spinner" />
            <p>Running OCR · metadata extraction · ontology mapping · reasoning…</p>
          </section>
        )}

        {result && (
          <>
            {/* ── Summary metrics ── */}
            <section className="card">
              <h2>Result Dashboard</h2>
              <div className="result-grid">
                <div className={`metric-card verdict-card ${vm.cls}`}>
                  <p className="label">Verdict</p>
                  <p className={`verdict ${vm.cls}`}>
                    <span className="verdict-icon">{vm.icon}</span> {vm.label}
                  </p>
                </div>
                <div className="metric-card">
                  <p className="label">Confidence</p>
                  <p className="metric">{Math.round((result.confidence || 0) * 100)}%</p>
                </div>
                <div className="metric-card">
                  <p className="label">Trust Score</p>
                  <p className="metric">{result.trustScore} / 100</p>
                </div>
                <div className="metric-card">
                  <p className="label">Conflicting Clues</p>
                  <p className={`metric ${result.conflictingClues ? "text-warn" : "text-ok"}`}>
                    {result.conflictingClues ? "Yes" : "No"}
                  </p>
                </div>
              </div>

              {/* ── NMRA & Manufacturer row ── */}
              <div className="nmra-row">
                <div className="nmra-cell">
                  <p className="label">NMRA Registration</p>
                  <NMRABadge status={result.nmra_status} />
                </div>
                <div className="nmra-cell">
                  <p className="label">Manufacturer</p>
                  <MatchBadge match={result.manufacturer_match} />
                </div>
                <div className="nmra-cell">
                  <p className="label">Images Processed</p>
                  <p className="metric-sm">{result.number_of_images_processed ?? 1}</p>
                </div>
              </div>
            </section>

            {/* ── Extracted metadata ── */}
            <section className="card">
              <h3>Extracted Metadata</h3>
              <div className="metadata-grid">
                {Object.keys(METADATA_LABELS).map((k) => (
                  <MetaField key={k} fieldKey={k} value={result.metadata?.[k]} />
                ))}
              </div>
            </section>

            <NmraVerifiedSection nmra={result.nmra} />
            <ValidationComparison nmra={result.nmra} />

            {/* ── Guideline justification ── */}
            <section className="card">
              <h3>Guideline Justification</h3>
              <ul className="guideline-list">
                {(result.validationResults || []).map((item, i) => (
                  <li key={`gl-${i}`} className={`guideline-item ${item.status === "passed" ? "gl-pass" : "gl-fail"}`}>
                    <div className="guideline-header">
                      <GuidelineBadge guideline={item.guideline} status={item.status} />
                      <span className="guideline-rule">{item.rule}</span>
                    </div>
                    <p className="guideline-detail">{item.detail}</p>
                  </li>
                ))}
              </ul>
            </section>

            {/* ── Explanation ── */}
            <section className="card">
              <h3>Explanation</h3>
              <div className="explanation-block">
                {(result.explanation || []).map((line, i) => (
                  <p key={`ex-${i}`}>{line}</p>
                ))}
              </div>
            </section>

            {/* ── Raw OCR (collapsed) – only render when text is available ── */}
            {result.ocr_raw_text && (
              <section className="card">
                <OcrToggle text={result.ocr_raw_text} />
              </section>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default App;