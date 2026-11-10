import { useEffect, useState } from "react";
import { fetchOperationalEvidence } from "../../services/reportsApi";
import type { OperationalEvidence, SpotRisk } from "../../types";

interface Props {
  spots: SpotRisk[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export default function OperationalEvidenceView({ spots, selectedId, onSelect }: Props) {
  const [evidenceList, setEvidenceList] = useState<OperationalEvidence[]>([]);
  const [radiusMeters, setRadiusMeters] = useState<number>(1500);
  const [windowHours, setWindowHours] = useState<number>(6);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const loadEvidence = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchOperationalEvidence(radiusMeters, windowHours);
      setEvidenceList(data);
    } catch (err: any) {
      setError(err?.message || "Failed to load operational evidence overlay.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadEvidence();
  }, [radiusMeters, windowHours]);

  const evidenceBySpot = new Map(evidenceList.map((e) => [e.spot_id, e]));

  return (
    <div className="operational-evidence-view">
      <div className="evidence-header">
        <div>
          <h2>Operational Evidence Overlay</h2>
          <p className="sub">Independent Human-Verified Ground Truth Signal</p>
        </div>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={loadEvidence}
          disabled={loading}
        >
          {loading ? "Refreshing..." : "🔄 Refresh"}
        </button>
      </div>

      {/* Model Isolation & Integrity Notice */}
      <div className="civic-notice isolation-notice">
        <strong>Risk Engine Isolation Notice:</strong> Physical risk scores and crowd evidence
        signals are computed independently. PhysicalRiskModel weights and thresholds are unchanged.
        Descriptive operational assessments are not calibrated probabilities.
      </div>

      {/* Configurable Proximity & Time Controls */}
      <div className="evidence-controls-grid">
        <label className="param-slider-wrap">
          <div className="slider-label-row">
            <span>Proximity Radius:</span>
            <span className="slider-val">{radiusMeters}m ({(radiusMeters / 1000).toFixed(1)} km)</span>
          </div>
          <input
            type="range"
            min={500}
            max={5000}
            step={250}
            value={radiusMeters}
            onChange={(e) => setRadiusMeters(Number(e.target.value))}
            className="slider-input"
          />
        </label>
        <label className="param-slider-wrap">
          <div className="slider-label-row">
            <span>Time Window:</span>
            <span className="slider-val">{windowHours}h</span>
          </div>
          <input
            type="range"
            min={1}
            max={24}
            step={1}
            value={windowHours}
            onChange={(e) => setWindowHours(Number(e.target.value))}
            className="slider-input"
          />
        </label>
      </div>

      {error && <div className="error-alert" role="alert">{error}</div>}

      {/* Spots Comparison Grid */}
      <div className="spots-evidence-list">
        {spots.map((spot) => {
          const ev = evidenceBySpot.get(spot.spot_id);
          const isSelected = spot.spot_id === selectedId;

          // Compute descriptive operational assessment
          let assessment = "Routine Monitoring";
          let assessmentColor = "#2b8a3e";

          if (ev && ev.evidence_status === "critical") {
            assessment = "Emergency Priority (Physical + Verified Flood Evidence)";
            assessmentColor = "#c92a2a";
          } else if (spot.level === "red" && ev && ev.approved_reports_nearby > 0) {
            assessment = "High Alert (Extreme Rain + Ground Corroboration)";
            assessmentColor = "#d9480f";
          } else if (spot.level === "red") {
            assessment = "High Physical Hazard (Model Alert - Pending Ground Check)";
            assessmentColor = "#d9480f";
          } else if (ev && ev.evidence_status === "elevated") {
            assessment = "Field Alert (Multiple Verified Reports)";
            assessmentColor = "#e67700";
          } else if (spot.level === "amber") {
            assessment = "Moderate Watch (Physical Amber)";
            assessmentColor = "#b25e00";
          }

          return (
            <div
              key={spot.spot_id}
              className={`spot-evidence-card ${isSelected ? "is-selected" : ""}`}
              onClick={() => onSelect(spot.spot_id)}
            >
              <div className="card-top">
                <span className="spot-title">{spot.name}</span>
                <span className={`badge badge-${spot.level}`}>
                  Physical: {spot.risk.toFixed(2)} ({spot.level.toUpperCase()})
                </span>
              </div>

              {/* Signals Comparison Grid */}
              <div className="signals-grid">
                <div className="signal-cell">
                  <span className="sig-label">Approved Reports</span>
                  <span className="sig-value text-blue">
                    {ev ? ev.approved_reports_nearby : 0} verified
                  </span>
                </div>
                <div className="signal-cell">
                  <span className="sig-label">Pending Reviews</span>
                  <span className="sig-value text-amber">
                    {ev ? ev.pending_reports_nearby : 0} unverified
                  </span>
                </div>
                <div className="signal-cell">
                  <span className="sig-label">Evidence Status</span>
                  <span className={`status-pill status-${ev?.evidence_status || "none"}`}>
                    {ev?.evidence_status || "none"}
                  </span>
                </div>
                <div className="signal-cell">
                  <span className="sig-label">Freshness</span>
                  <span className="sig-value">{ev?.freshness || "none"}</span>
                </div>
              </div>

              {/* Descriptive Operational Assessment */}
              <div className="operational-assessment-box" style={{ borderLeftColor: assessmentColor }}>
                <span className="assessment-label">Descriptive Operational Assessment:</span>
                <p className="assessment-text" style={{ color: assessmentColor }}>
                  {assessment}
                </p>
              </div>

              {/* Explanation */}
              {ev?.explanation && <p className="evidence-explanation">{ev.explanation}</p>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

