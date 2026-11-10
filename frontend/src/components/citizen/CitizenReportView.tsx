import React, { useEffect, useState } from "react";
import {
  clearDraft,
  enqueueOfflineReport,
  getDraft,
  saveDraft,
  submitCitizenReport,
} from "../../services/reportsApi";
import type { CitizenReport, OfflineQueuedReport, ReportType, SeverityLevel } from "../../types";

interface Props {
  onNavigateToTrack: (reportId: string) => void;
  selectedCoordinates?: { lat: number; lng: number } | null;
}

const MONITORED_SPOTS = [
  { id: "silk_board", name: "Silk Board Junction", lat: 12.9177, lng: 77.6233 },
  { id: "bellandur", name: "Bellandur Lake Edge", lat: 12.9352, lng: 77.6745 },
  { id: "hsr_layout", name: "HSR Layout Sector 2", lat: 12.9116, lng: 77.6389 },
  { id: "agara", name: "Agara Underpass", lat: 12.9250, lng: 77.6480 },
  { id: "kr_circle", name: "KR Circle Underpass", lat: 12.9763, lng: 77.5929 },
  { id: "hebbal", name: "Hebbal Flyover Approach", lat: 13.0358, lng: 77.5970 },
  { id: "mahadevapura", name: "Mahadevapura Main Road", lat: 12.9910, lng: 77.6980 },
  { id: "indiranagar", name: "Indiranagar 100ft Road", lat: 12.9719, lng: 77.6412 },
];

export default function CitizenReportView({ onNavigateToTrack, selectedCoordinates }: Props) {
  // Form state
  const [reportType, setReportType] = useState<ReportType>("flood");
  const [selectedSpotId, setSelectedSpotId] = useState<string>("silk_board");
  const [latitude, setLatitude] = useState<string>("12.9177");
  const [longitude, setLongitude] = useState<string>("77.6233");
  const [waterDepthCm, setWaterDepthCm] = useState<number>(30);
  const [severityLevel, setSeverityLevel] = useState<SeverityLevel>("medium");
  const [notes, setNotes] = useState<string>("");
  const [reporterAlias, setReporterAlias] = useState<string>("");

  // Photo state
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);
  const [photoError, setPhotoError] = useState<string | null>(null);

  // GPS state
  const [gpsLoading, setGpsLoading] = useState<boolean>(false);
  const [gpsStatus, setGpsStatus] = useState<string | null>(null);

  // UI state
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [submittedReport, setSubmittedReport] = useState<CitizenReport | null>(null);
  const [queuedOffline, setQueuedOffline] = useState<OfflineQueuedReport | null>(null);
  const [copiedToken, setCopiedToken] = useState<boolean>(false);

  // Auto-restore draft from localStorage
  useEffect(() => {
    const draft = getDraft();
    if (draft) {
      if (draft.report_type) setReportType(draft.report_type);
      if (draft.spot_id) setSelectedSpotId(draft.spot_id);
      if (draft.latitude) setLatitude(String(draft.latitude));
      if (draft.longitude) setLongitude(String(draft.longitude));
      if (draft.water_depth_cm !== undefined && draft.water_depth_cm !== null) {
        setWaterDepthCm(draft.water_depth_cm);
      }
      if (draft.severity_level) setSeverityLevel(draft.severity_level);
      if (draft.notes) setNotes(draft.notes);
      if (draft.reporter_alias) setReporterAlias(draft.reporter_alias);
    }
  }, []);

  // Update coordinates if selected from map pin click
  useEffect(() => {
    if (selectedCoordinates) {
      setLatitude(selectedCoordinates.lat.toFixed(4));
      setLongitude(selectedCoordinates.lng.toFixed(4));
      setSelectedSpotId("custom");
    }
  }, [selectedCoordinates]);

  // Auto-save draft changes to localStorage
  useEffect(() => {
    if (!submittedReport && !queuedOffline) {
      saveDraft({
        spot_id: selectedSpotId,
        report_type: reportType,
        latitude: parseFloat(latitude) || 12.9177,
        longitude: parseFloat(longitude) || 77.6233,
        water_depth_cm: reportType === "flood" ? waterDepthCm : null,
        severity_level: severityLevel,
        notes,
        reporter_alias: reporterAlias,
      });
    }
  }, [selectedSpotId, reportType, latitude, longitude, waterDepthCm, severityLevel, notes, reporterAlias, submittedReport, queuedOffline]);

  // Handle spot dropdown change
  const handleSpotChange = (spotId: string) => {
    setSelectedSpotId(spotId);
    if (spotId === "custom") return;
    const found = MONITORED_SPOTS.find((s) => s.id === spotId);
    if (found) {
      setLatitude(found.lat.toFixed(4));
      setLongitude(found.lng.toFixed(4));
    }
  };

  // Explicit user action to request GPS permission
  const handleRequestGps = () => {
    if (!navigator.geolocation) {
      setGpsStatus("Geolocation is not supported by your browser.");
      return;
    }

    setGpsLoading(true);
    setGpsStatus("Requesting device location...");

    navigator.geolocation.getCurrentPosition(
      (position) => {
        const lat = position.coords.latitude;
        const lng = position.coords.longitude;
        setLatitude(lat.toFixed(4));
        setLongitude(lng.toFixed(4));
        setSelectedSpotId("custom");
        setGpsLoading(false);
        setGpsStatus(`GPS coordinates acquired (accuracy: ~${Math.round(position.coords.accuracy)}m)`);
      },
      (error) => {
        setGpsLoading(false);
        let msg = "Could not retrieve GPS location.";
        if (error.code === error.PERMISSION_DENIED) {
          msg = "GPS permission was denied. You can manually enter coordinates or pick a spot.";
        } else if (error.code === error.POSITION_UNAVAILABLE) {
          msg = "Location unavailable. Please enter coordinates manually.";
        } else if (error.code === error.TIMEOUT) {
          msg = "Location request timed out. Please retry or enter manually.";
        }
        setGpsStatus(msg);
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 }
    );
  };

  // Photo handling
  const handlePhotoSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    setPhotoError(null);
    const file = e.target.files?.[0];
    if (!file) return;

    // Validate size (< 5MB)
    if (file.size > 5 * 1024 * 1024) {
      setPhotoError("File size exceeds 5 MB. Please choose a smaller photo.");
      return;
    }

    // Validate type
    const validTypes = ["image/jpeg", "image/png", "image/webp"];
    if (!validTypes.includes(file.type)) {
      setPhotoError("Unsupported file type. Please upload a JPEG, PNG, or WebP photo.");
      return;
    }

    setPhotoFile(file);
    const reader = new FileReader();
    reader.onload = (event) => {
      setPhotoPreview(event.target?.result as string);
    };
    reader.readAsDataURL(file);
  };

  const handleRemovePhoto = () => {
    setPhotoFile(null);
    setPhotoPreview(null);
    setPhotoError(null);
  };

  // Form submission
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    const latNum = parseFloat(latitude);
    const lngNum = parseFloat(longitude);

    if (isNaN(latNum) || isNaN(lngNum)) {
      setFormError("Please provide valid latitude and longitude coordinates.");
      return;
    }

    // Sanity check coordinates for Bengaluru region (~12.7 to ~13.3 N, ~77.3 to ~77.9 E)
    if (latNum < 12.0 || latNum > 14.0 || lngNum < 76.5 || lngNum > 78.5) {
      setFormError("Coordinates appear outside Greater Bengaluru area (expected approx lat 12.9, lng 77.6).");
      return;
    }

    if (!notes.trim() && reportType === "flood") {
      setFormError("Please provide a brief description of the flood or waterlogging condition.");
      return;
    }

    setSubmitting(true);

    const payload = {
      spot_id: selectedSpotId === "custom" ? undefined : selectedSpotId,
      report_type: reportType,
      water_depth_cm: reportType === "flood" ? waterDepthCm : null,
      severity_level: severityLevel,
      latitude: latNum,
      longitude: lngNum,
      reporter_alias: reporterAlias.trim() || "Anonymous Citizen",
      notes: notes.trim(),
    };

    // Check online status
    if (!navigator.onLine) {
      // Offline queueing
      const queued = enqueueOfflineReport(payload, photoPreview || undefined, photoFile?.name);
      clearDraft();
      setSubmitting(false);
      setQueuedOffline(queued);
      return;
    }

    try {
      const formData = new FormData();
      if (payload.spot_id) formData.append("spot_id", payload.spot_id);
      formData.append("report_type", payload.report_type);
      if (payload.water_depth_cm !== null && payload.water_depth_cm !== undefined) {
        formData.append("water_depth_cm", String(payload.water_depth_cm));
      }
      formData.append("severity_level", payload.severity_level);
      formData.append("latitude", String(payload.latitude));
      formData.append("longitude", String(payload.longitude));
      formData.append("reporter_alias", payload.reporter_alias);
      formData.append("notes", payload.notes);

      if (photoFile) {
        formData.append("image", photoFile);
      }

      const response = await submitCitizenReport(formData);
      clearDraft();
      setSubmittedReport(response);
    } catch (err: any) {
      console.warn("Online submission failed, falling back to offline queue:", err);
      // Fallback: save to offline queue if server is unreachable
      const queued = enqueueOfflineReport(payload, photoPreview || undefined, photoFile?.name);
      clearDraft();
      setQueuedOffline(queued);
    } finally {
      setSubmitting(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedToken(true);
    setTimeout(() => setCopiedToken(false), 2500);
  };

  const resetForm = () => {
    setSubmittedReport(null);
    setQueuedOffline(null);
    setNotes("");
    setPhotoFile(null);
    setPhotoPreview(null);
    setFormError(null);
    setGpsStatus(null);
    clearDraft();
  };

  /* -------------------------------------------------------------------------- */
  /*                         CONFIRMATION SCREEN (SUCCESS)                      */
  /* -------------------------------------------------------------------------- */

  if (submittedReport) {
    return (
      <div className="citizen-card confirmation-card" role="region" aria-label="Submission Confirmation">
        <div className="confirmation-header">
          <div className="success-badge-icon">✓</div>
          <h2>Report Submitted Successfully</h2>
          <p className="sub">Transmitted to Bengaluru Municipal Early Warning Cell</p>
        </div>

        <div className="token-box">
          <span className="token-label">Report Tracking Token</span>
          <div className="token-value-row">
            <code className="token-code">{submittedReport.report_id}</code>
            <button
              type="button"
              className="btn btn-secondary btn-copy"
              onClick={() => copyToClipboard(submittedReport.report_id)}
            >
              {copiedToken ? "Copied!" : "📋 Copy"}
            </button>
          </div>
        </div>

        <div className="status-summary-box">
          <div className="status-row">
            <span className="status-lbl">Current Status:</span>
            <span className="status-pill status-submitted">
              ● Submitted (Pending Field Review)
            </span>
          </div>
          <div className="status-row">
            <span className="status-lbl">Location:</span>
            <span>{submittedReport.spot_name || `${submittedReport.latitude}, ${submittedReport.longitude}`}</span>
          </div>
          {submittedReport.water_depth_cm && (
            <div className="status-row">
              <span className="status-lbl">Water Depth:</span>
              <span>{submittedReport.water_depth_cm} cm</span>
            </div>
          )}
          <div className="status-row">
            <span className="status-lbl">Logged At:</span>
            <span>{new Date(submittedReport.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
          </div>
        </div>

        {/* Civic Integrity Notice */}
        <div className="civic-notice">
          <strong>Civic Verification Notice:</strong> This report is logged as crowd evidence.
          It will be cross-referenced with radar rain rates and traffic sensors before being
          formally verified by BBMP operators.
        </div>

        <div className="confirmation-actions">
          <button
            type="button"
            className="btn btn-primary btn-block"
            onClick={() => onNavigateToTrack(submittedReport.report_id)}
          >
            🔍 Track Verification Progress
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-block"
            onClick={resetForm}
          >
            ➕ Submit Another Report
          </button>
        </div>
      </div>
    );
  }

  /* -------------------------------------------------------------------------- */
  /*                      OFFLINE QUEUE CONFIRMATION SCREEN                     */
  /* -------------------------------------------------------------------------- */

  if (queuedOffline) {
    return (
      <div className="citizen-card confirmation-card offline-card" role="region" aria-label="Offline Submission Queued">
        <div className="confirmation-header">
          <div className="offline-badge-icon">⏳</div>
          <h2>Saved to Local Offline Queue</h2>
          <p className="sub">No internet connection detected</p>
        </div>

        <div className="token-box">
          <span className="token-label">Local Reference ID</span>
          <div className="token-value-row">
            <code className="token-code">{queuedOffline.temp_id}</code>
          </div>
        </div>

        <div className="civic-notice offline-notice">
          <strong>Offline Queue Indicator:</strong> This report is stored safely on your device.
          As soon as your network reconnects, FloodSense AI will automatically synchronize it with
          the BBMP Disaster Monitoring Cell. <em>It is NOT yet submitted to the server.</em>
        </div>

        <div className="confirmation-actions">
          <button
            type="button"
            className="btn btn-primary btn-block"
            onClick={resetForm}
          >
            📝 Return to Reporting Form
          </button>
        </div>
      </div>
    );
  }

  /* -------------------------------------------------------------------------- */
  /*                             REPORTING FORM                                 */
  /* -------------------------------------------------------------------------- */

  return (
    <form className="citizen-form" onSubmit={handleSubmit} noValidate>
      <div className="form-intro">
        <h2>Report Flood or Clear Road</h2>
        <p className="sub">Hyperlocal crowdsourced intelligence for Bengaluru</p>
      </div>

      {formError && <div className="error-alert" role="alert">{formError}</div>}

      {/* 1. Report Type Switcher */}
      <div className="field-group">
        <label className="field-label">Report Type</label>
        <div className="report-type-toggle" role="radiogroup">
          <button
            type="button"
            className={`btn-type ${reportType === "flood" ? "active is-flood" : ""}`}
            onClick={() => setReportType("flood")}
          >
            🌊 Waterlogging / Flood
          </button>
          <button
            type="button"
            className={`btn-type ${reportType === "control_clear" ? "active is-clear" : ""}`}
            onClick={() => setReportType("control_clear")}
          >
            ✅ Road is Clear & Passable
          </button>
        </div>
        <p className="field-hint">
          {reportType === "flood"
            ? "Report standing water, underpass flooding, or drainage choke points."
            : "Helpful negative control: Confirm that this carriageway is dry and traffic is flowing."}
        </p>
      </div>

      {/* 2. Location Selection */}
      <div className="field-group">
        <div className="field-label-row">
          <label className="field-label" htmlFor="spotSelect">Location Selection</label>
          <button
            type="button"
            className="btn btn-ghost btn-gps"
            onClick={handleRequestGps}
            disabled={gpsLoading}
          >
            {gpsLoading ? "📍 Locating..." : "📍 Use My GPS"}
          </button>
        </div>

        <select
          id="spotSelect"
          className="form-select"
          value={selectedSpotId}
          onChange={(e) => handleSpotChange(e.target.value)}
        >
          {MONITORED_SPOTS.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
          <option value="custom">📍 Custom Pin / Other Bengaluru Location</option>
        </select>

        {gpsStatus && <p className="gps-status-text">{gpsStatus}</p>}

        <div className="coords-row">
          <label className="coord-input-wrap">
            <span>Latitude</span>
            <input
              type="text"
              className="form-input"
              value={latitude}
              onChange={(e) => {
                setLatitude(e.target.value);
                setSelectedSpotId("custom");
              }}
              placeholder="e.g. 12.9177"
            />
          </label>
          <label className="coord-input-wrap">
            <span>Longitude</span>
            <input
              type="text"
              className="form-input"
              value={longitude}
              onChange={(e) => {
                setLongitude(e.target.value);
                setSelectedSpotId("custom");
              }}
              placeholder="e.g. 77.6233"
            />
          </label>
        </div>
        <p className="field-hint">
          Click any spot on the map, select a known hotspot, or tap &quot;Use My GPS&quot;.
        </p>
      </div>

      {/* 3. Flood Details (if flood type) */}
      {reportType === "flood" && (
        <>
          <div className="field-group">
            <label className="field-label">Severity Level</label>
            <div className="severity-grid" role="radiogroup">
              {[
                { level: "low", label: "Low", desc: "Curb pooling (<15cm)", color: "#2b8a3e" },
                { level: "medium", label: "Medium", desc: "Ankle deep (15-45cm)", color: "#e67700" },
                { level: "high", label: "High", desc: "Knee / Axle (45-80cm)", color: "#d9480f" },
                { level: "critical", label: "Critical", desc: "Underpass submerged (>80cm)", color: "#c92a2a" },
              ].map((item) => (
                <button
                  type="button"
                  key={item.level}
                  className={`severity-btn ${severityLevel === item.level ? "active" : ""}`}
                  style={{ borderColor: severityLevel === item.level ? item.color : undefined }}
                  onClick={() => setSeverityLevel(item.level as SeverityLevel)}
                >
                  <span className="sev-title" style={{ color: item.color }}>{item.label}</span>
                  <span className="sev-desc">{item.desc}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="field-group">
            <div className="field-label-row">
              <label className="field-label" htmlFor="waterDepth">Water Depth Estimate</label>
              <span className="depth-badge">{waterDepthCm} cm (~{(waterDepthCm / 30.48).toFixed(1)} ft)</span>
            </div>
            <input
              id="waterDepth"
              type="range"
              min={5}
              max={150}
              step={5}
              value={waterDepthCm}
              onChange={(e) => setWaterDepthCm(Number(e.target.value))}
              className="depth-slider"
            />
            <div className="slider-ticks">
              <span>5cm</span>
              <span>30cm (Knee)</span>
              <span>60cm (Car)</span>
              <span>100cm+ (Bus/Submerged)</span>
            </div>
          </div>
        </>
      )}

      {/* 4. Photograph Upload */}
      <div className="field-group">
        <label className="field-label">Evidence Photograph</label>
        <div className="photo-upload-box">
          {!photoPreview ? (
            <label className="photo-dropzone">
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                capture="environment"
                onChange={handlePhotoSelect}
                className="hidden-file-input"
              />
              <span className="upload-icon">📷</span>
              <span className="upload-prompt">Take photo with camera or choose file</span>
              <span className="upload-limits">JPEG, PNG, WebP up to 5 MB</span>
            </label>
          ) : (
            <div className="photo-preview-wrap">
              <img src={photoPreview} alt="Flood evidence preview" className="photo-preview" />
              <div className="photo-actions">
                <span className="photo-name">{photoFile?.name}</span>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={handleRemovePhoto}
                >
                  ✕ Remove
                </button>
              </div>
            </div>
          )}
        </div>
        {photoError && <p className="error-text">{photoError}</p>}
      </div>

      {/* 5. Report Information */}
      <div className="field-group">
        <label className="field-label" htmlFor="notesText">Description & Ground Observation</label>
        <textarea
          id="notesText"
          className="form-textarea"
          rows={3}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder={
            reportType === "flood"
              ? "e.g., Silk Board service road waterlogged, two two-wheelers stalled, drain inlet blocked by debris."
              : "e.g., Flyover and surface roads completely dry, rain ceased 20 mins ago."
          }
        />
      </div>

      <div className="field-group">
        <label className="field-label" htmlFor="aliasText">Your Name or Identifier (Optional)</label>
        <input
          id="aliasText"
          type="text"
          className="form-input"
          value={reporterAlias}
          onChange={(e) => setReporterAlias(e.target.value)}
          placeholder="e.g. Resident / Traffic Warden (Defaults to Anonymous Citizen)"
        />
      </div>

      {/* Submit Button */}
      <button
        type="submit"
        className="btn btn-primary btn-submit-report"
        disabled={submitting}
      >
        {submitting ? "Transmitting Report..." : "Submit Report to Early Warning Cell"}
      </button>

      <p className="privacy-note">
        🔒 FloodSense AI does not collect personal contact numbers or track continuous GPS.
        Reports are preserved in a local public safety log.
      </p>
    </form>
  );
}

