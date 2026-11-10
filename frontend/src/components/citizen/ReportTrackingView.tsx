import { useEffect, useState } from "react";
import { fetchReportById, getRecentSubmittedIds } from "../../services/reportsApi";
import type { CitizenReport, VerificationStatus } from "../../types";

interface Props {
  initialToken?: string | null;
  onNavigateToReport: () => void;
}

export default function ReportTrackingView({ initialToken, onNavigateToReport }: Props) {
  const [searchToken, setSearchToken] = useState<string>(initialToken || "");
  const [report, setReport] = useState<CitizenReport | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [recentTokens, setRecentTokens] = useState<string[]>([]);

  useEffect(() => {
    const recents = getRecentSubmittedIds();
    setRecentTokens(recents);

    if (initialToken) {
      setSearchToken(initialToken);
      handleTrack(initialToken);
    } else if (recents.length > 0) {
      // Auto-populate with most recent token if available
      setSearchToken(recents[0]);
      handleTrack(recents[0]);
    }
  }, [initialToken]);

  const handleTrack = async (tokenId: string) => {
    const clean = tokenId.trim();
    if (!clean) {
      setError("Please enter a valid report tracking token (e.g. rep_...)");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const data = await fetchReportById(clean);
      setReport(data);
    } catch (err: any) {
      setError(err?.message || "Report could not be found.");
      setReport(null);
    } finally {
      setLoading(false);
    }
  };

  const getStatusBadge = (status: VerificationStatus) => {
    switch (status) {
      case "approved":
      case "verified":
        return {
          label: "Approved & Verified",
          className: "status-pill status-approved",
          desc: "Confirmed flood ground-truth incident. Registered in BBMP municipal response ledger.",
          color: "#2b8a3e",
        };
      case "under_review":
        return {
          label: "Under Active Review",
          className: "status-pill status-review",
          desc: "BBMP Control Room operator is cross-checking rainfall rates and road sensors.",
          color: "#e67700",
        };
      case "rejected":
        return {
          label: "Rejected / Unsubstantiated",
          className: "status-pill status-rejected",
          desc: "Report could not be corroborated with sensor data or was outside monitored zones.",
          color: "#c92a2a",
        };
      case "needs_info":
        return {
          label: "Needs More Information",
          className: "status-pill status-needs-info",
          desc: "Operator requested clearer photo evidence or water depth estimation.",
          color: "#d9480f",
        };
      case "submitted":
      case "pending":
      default:
        return {
          label: "Submitted (Pending Review)",
          className: "status-pill status-submitted",
          desc: "Report has been safely logged in the system. Awaiting municipal triage.",
          color: "#1f6f8b",
        };
    }
  };

  return (
    <div className="citizen-card tracking-card">
      <div className="form-intro">
        <h2>Citizen Incident Tracking</h2>
        <p className="sub">Track live municipal verification and ground-truth updates</p>
      </div>

      {/* Search Bar */}
      <form
        className="tracking-search-form"
        onSubmit={(e) => {
          e.preventDefault();
          handleTrack(searchToken);
        }}
      >
        <div className="search-input-wrap">
          <input
            type="text"
            className="form-input tracking-input"
            placeholder="Enter Tracking Token (e.g. rep_8a3f9e...)"
            value={searchToken}
            onChange={(e) => setSearchToken(e.target.value)}
          />
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? "Searching..." : "Track"}
          </button>
        </div>
      </form>

      {/* Recent submissions chips */}
      {recentTokens.length > 0 && (
        <div className="recent-tokens-row">
          <span className="recent-label">Your Recent Reports:</span>
          <div className="recent-chips">
            {recentTokens.slice(0, 4).map((t) => (
              <button
                key={t}
                type="button"
                className={`token-chip ${searchToken === t ? "active" : ""}`}
                onClick={() => {
                  setSearchToken(t);
                  handleTrack(t);
                }}
              >
                {t}
              </button>
            ))}
          </div>
        </div>
      )}

      {error && <div className="error-alert" role="alert">{error}</div>}

      {/* Report Result Display */}
      {report && (
        <div className="tracking-result-panel">
          {/* Status Banner */}
          {(() => {
            const badge = getStatusBadge(report.verification_status);
            return (
              <div className="tracking-status-banner" style={{ borderLeftColor: badge.color }}>
                <div className="tracking-status-header">
                  <span className={badge.className}>{badge.label}</span>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => handleTrack(report.report_id)}
                    title="Refresh status"
                  >
                    🔄 Refresh
                  </button>
                </div>
                <p className="tracking-status-desc">{badge.desc}</p>
              </div>
            );
          })()}

          {/* Stepper Timeline */}
          <div className="stepper-timeline">
            <div
              className={`timeline-step ${
                ["submitted", "under_review", "approved", "rejected", "needs_info"].includes(
                  report.verification_status
                )
                  ? "completed"
                  : ""
              }`}
            >
              <div className="step-circle">1</div>
              <div className="step-label">Submitted</div>
            </div>
            <div className="timeline-line"></div>
            <div
              className={`timeline-step ${
                ["under_review", "approved", "rejected", "needs_info"].includes(
                  report.verification_status
                )
                  ? "completed"
                  : ""
              }`}
            >
              <div className="step-circle">2</div>
              <div className="step-label">Under Review</div>
            </div>
            <div className="timeline-line"></div>
            <div
              className={`timeline-step ${
                report.verification_status === "approved" || report.verification_status === "verified"
                  ? "completed is-approved"
                  : report.verification_status === "rejected"
                  ? "completed is-rejected"
                  : report.verification_status === "needs_info"
                  ? "completed is-needs-info"
                  : "pending"
              }`}
            >
              <div className="step-circle">
                {report.verification_status === "approved"
                  ? "✓"
                  : report.verification_status === "rejected"
                  ? "✕"
                  : report.verification_status === "needs_info"
                  ? "!"
                  : "3"}
              </div>
              <div className="step-label">
                {report.verification_status === "approved"
                  ? "Approved"
                  : report.verification_status === "rejected"
                  ? "Rejected"
                  : report.verification_status === "needs_info"
                  ? "Needs Info"
                  : "Verified"}
              </div>
            </div>
          </div>

          {/* Report Data Details */}
          <div className="report-detail-grid">
            <div className="detail-item">
              <span className="item-label">Tracking ID</span>
              <span className="item-value font-mono">{report.report_id}</span>
            </div>
            <div className="detail-item">
              <span className="item-label">Report Type</span>
              <span className="item-value">
                {report.report_type === "flood" ? "🌊 Waterlogging / Flood" : "✅ Clear & Passable Corridor"}
              </span>
            </div>
            <div className="detail-item">
              <span className="item-label">Monitored Spot</span>
              <span className="item-value">{report.spot_name || report.spot_id}</span>
            </div>
            <div className="detail-item">
              <span className="item-label">Coordinates</span>
              <span className="item-value font-mono">
                {report.latitude.toFixed(4)} N, {report.longitude.toFixed(4)} E
              </span>
            </div>
            {report.severity_level && (
              <div className="detail-item">
                <span className="item-label">Severity Assessment</span>
                <span className="item-value capitalize">{report.severity_level}</span>
              </div>
            )}
            {report.water_depth_cm !== null && report.water_depth_cm !== undefined && (
              <div className="detail-item">
                <span className="item-label">Observed Depth</span>
                <span className="item-value">{report.water_depth_cm} cm</span>
              </div>
            )}
            <div className="detail-item">
              <span className="item-label">Reported By</span>
              <span className="item-value">{report.reporter_alias || "Anonymous Citizen"}</span>
            </div>
            <div className="detail-item">
              <span className="item-label">Logged Timestamp</span>
              <span className="item-value">
                {new Date(report.created_at).toLocaleString([], { dateStyle: "short", timeStyle: "short" })}
              </span>
            </div>
          </div>

          {/* Description & Notes */}
          {report.notes && (
            <div className="report-notes-box">
              <span className="item-label">Observation Notes</span>
              <p className="notes-text">{report.notes}</p>
            </div>
          )}

          {/* Photo Preview if available */}
          {report.image_url && (
            <div className="report-photo-box">
              <span className="item-label">Photo Evidence</span>
              <div className="photo-container">
                <img
                  src={`http://localhost:8000${report.image_url}`}
                  alt="Citizen flood evidence"
                  className="tracking-photo-img"
                  onError={(e) => {
                    // Fallback if image fails to load
                    (e.target as HTMLElement).style.display = "none";
                  }}
                />
              </div>
            </div>
          )}

          {/* Verification Operator Notes */}
          {report.verified_by && (
            <div className="operator-verified-box">
              <span className="item-label">Municipal Action Log</span>
              <p className="operator-text">
                Reviewed by <strong>{report.verified_by}</strong>
                {report.verified_at && ` on ${new Date(report.verified_at).toLocaleTimeString()}`}.
              </p>
            </div>
          )}
        </div>
      )}

      <div className="tracking-footer">
        <button type="button" className="btn btn-secondary btn-block" onClick={onNavigateToReport}>
          📝 Submit a New Flood or Clear Corridor Report
        </button>
      </div>
    </div>
  );
}

