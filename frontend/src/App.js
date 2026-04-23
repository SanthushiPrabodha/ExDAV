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

function IconSelectImages() {
  return (
    <svg
      className="btn-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
      <circle cx="8.5" cy="8.5" r="1.5" />
      <polyline points="21 15 16 10 5 21" />
    </svg>
  );
}

function IconCamera() {
  return (
    <svg
      className="btn-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
      <circle cx="12" cy="13" r="4" />
    </svg>
  );
}

// Silent warm-up + cold-start handling for Render free tier.
// The backend can take 30–90+ seconds to wake up, then run heavy OCR/reasoning.
// We warm the service on mount; the analyze call retries with a progressive
// delay so the user never sees infrastructure details.
const WARMUP_TIMEOUT_MS = 90000; // health-check timeout

// Single POST /analyze can run a long time on a small VPS (OCR + OpenCV + reasoning).
// Default 20 min; override at build time with REACT_APP_ANALYZE_TIMEOUT_MS (milliseconds).
const _rawAnalyzeTimeout = (process.env.REACT_APP_ANALYZE_TIMEOUT_MS || "1200000").trim();
const _parsedTimeout = parseInt(_rawAnalyzeTimeout, 10);
const ANALYZE_TIMEOUT_MS =
  Number.isFinite(_parsedTimeout) && _parsedTimeout >= 120000 ? _parsedTimeout : 1200000;

const MAX_RETRIES = 2; // up to 2 retries = 3 total attempts

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
  const didWarmupRef = useRef(false);
  const cameraInputRef = useRef(null);

  const _MAX_IMAGES = 5;

  const backendBase = useMemo(() => resolveBackendBaseUrl(), []);
  const analyzeUrl = `${backendBase}/analyze`;
  const healthUrl = `${backendBase}/`;

  useEffect(() => {
    if (didWarmupRef.current) return;
    didWarmupRef.current = true;
    axios.get(healthUrl, { timeout: WARMUP_TIMEOUT_MS }).catch((err) => {
      console.warn("Backend warm-up ping failed:", err?.code || err?.message);
    });
  }, [healthUrl]);

  /** Replace selection — multi-select from gallery / files. */
  const handleGalleryChange = (e) => {
    const selected = Array.from(e.target.files || []);
    e.target.value = "";
    if (!selected.length) return;
    if (selected.length > _MAX_IMAGES) {
      setError(`Maximum ${_MAX_IMAGES} images allowed. Only the first ${_MAX_IMAGES} were kept.`);
      setFiles(selected.slice(0, _MAX_IMAGES));
    } else {
      setFiles(selected);
      setError("");
    }
  };

  /** Append one (or more) photos — used after camera capture on phones. */
  const handleCameraAdd = (e) => {
    const added = Array.from(e.target.files || []);
    e.target.value = "";
    if (!added.length) return;
    setFiles((prev) => {
      const combined = [...prev, ...added];
      if (combined.length > _MAX_IMAGES) {
        setError(
          `Maximum ${_MAX_IMAGES} images. ${combined.length - _MAX_IMAGES} photo(s) not added.`
        );
        return combined.slice(0, _MAX_IMAGES);
      }
      setError("");
      return combined;
    });
  };

  const openCamera = () => {
    cameraInputRef.current?.click();
  };

  const clearImages = () => {
    setFiles([]);
    setError("");
  };

  // Do NOT set Content-Type for FormData — the browser must add the
  // multipart boundary. A bare "multipart/form-data" header breaks uploads
  // and often surfaces as "Network Error" with no err.response.
  const postAnalyze = (formData, currentTimeout = ANALYZE_TIMEOUT_MS) =>
    axios.post(analyzeUrl, formData, { timeout: currentTimeout });

  const handleUpload = async () => {
    if (!files.length) {
      setError("Please add at least one image (gallery or camera).");
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
        setError(friendlyErrorMessage(err));
        break;
      }
    }

    setLoading(false);
  };

  const friendlyErrorMessage = (err) => {
    if (err?.response?.data) {
      const exp = err.response.data.explanation;
      if (exp) return Array.isArray(exp) ? exp.join(" ") : exp;
      return "We couldn't complete the analysis. Please try again.";
    }
    // Details for support only — not shown in the UI
    console.error("Analysis request failed (no HTTP response):", err?.code, err?.message);
    if (err?.code === "ECONNABORTED") {
      return "The analysis took too long. Try one smaller image or fewer images, then try again.";
    }
    if (
      (err?.message || "").toLowerCase().includes("network") ||
      err?.code === "ERR_NETWORK"
    ) {
      return "We couldn't connect. Check your internet connection and try again.";
    }
    return "We couldn't reach the analysis service. Please try again in a moment.";
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
            Add 1–5 images of the same package (front, back, sides) using{" "}
            <strong>Select images</strong> or <strong>Take photo</strong>.
          </p>
          <div className="upload-row upload-row-actions">
            <input
              id="exdav-gallery-input"
              className="file-input-hidden"
              type="file"
              accept="image/*"
              multiple
              onChange={handleGalleryChange}
            />
            <input
              ref={cameraInputRef}
              id="exdav-camera-input"
              className="file-input-hidden"
              type="file"
              accept="image/*"
              capture="environment"
              onChange={handleCameraAdd}
            />
            <label htmlFor="exdav-gallery-input" className="btn btn-secondary">
              <span className="btn-label-inner">
                <IconSelectImages />
                <span>Select images</span>
              </span>
            </label>
            <button
              type="button"
              className="btn btn-camera"
              onClick={openCamera}
              disabled={loading || files.length >= _MAX_IMAGES}
              aria-label="Open camera to take a photo"
            >
              <span className="btn-label-inner">
                <IconCamera />
                <span>Take photo</span>
              </span>
            </button>
            {files.length > 0 && (
              <button type="button" className="btn btn-ghost" onClick={clearImages} disabled={loading}>
                Clear all
              </button>
            )}
            <button className="btn btn-primary" onClick={handleUpload} disabled={loading}>
              {loading ? "Analyzing..." : "Analyze"}
            </button>
          </div>
          {files.length > 0 && (
            <p className="upload-count">
              {files.length} / {_MAX_IMAGES} image{files.length > 1 ? "s" : ""}:{" "}
              {files.map((f) => f.name).join(", ")}
            </p>
          )}
          {error && <p className="error">{error}</p>}
        </section>

        {/* ── Processing ── */}
        {loading && (
          <section className="card processing">
            <div className="spinner" />
            <p>
              Running OCR · metadata extraction · ontology mapping · reasoning…
              <br />
              <span className="processing-note">This may take a few minutes — please keep this tab open.</span>
            </p>
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