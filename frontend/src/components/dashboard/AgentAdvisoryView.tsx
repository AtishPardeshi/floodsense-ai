import { useEffect, useState } from "react";
import type { EmergencyAdvisory, SpotRisk } from "../../types";
import { fetchAgentAdvisory, fetchLiveAgentAdvisory } from "../../services/api";

interface Props {
  activeSpots: SpotRisk[];
}

export default function AgentAdvisoryView({ activeSpots }: Props) {
  const [advisory, setAdvisory] = useState<EmergencyAdvisory | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedLang, setSelectedLang] = useState<"en" | "kn">("en");
  const [advisorySource, setAdvisorySource] = useState<"simulation" | "live_feed">("simulation");

  const loadAdvisory = async (source: "simulation" | "live_feed") => {
    setLoading(true);
    setError(null);
    try {
      if (source === "live_feed") {
        const liveAdv = await fetchLiveAgentAdvisory();
        setAdvisory(liveAdv);
      } else {
        const simAdv = await fetchAgentAdvisory(activeSpots, "Current Simulation State");
        setAdvisory(simAdv);
      }
    } catch (err: any) {
      setError(err?.message || "Failed to generate emergency advisory");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAdvisory(advisorySource);
  }, [advisorySource, activeSpots]);

  const levelColor =
    advisory?.overall_alert_level === "red"
      ? "#d9381e"
      : advisory?.overall_alert_level === "amber"
      ? "#e68a00"
      : "#1b8a5a";

  const levelBg =
    advisory?.overall_alert_level === "red"
      ? "#fde8e8"
      : advisory?.overall_alert_level === "amber"
      ? "#fff8e6"
      : "#e8f7ee";

  return (
    <div className="advisory-container">
      {/* Source selector */}
      <div className="advisory-source-bar">
        <label className="control-label">Advisory Context:</label>
        <div className="source-toggle">
          <button
            className={`btn-source ${advisorySource === "simulation" ? "active" : ""}`}
            onClick={() => setAdvisorySource("simulation")}
          >
            Active Simulation Spots
          </button>
          <button
            className={`btn-source ${advisorySource === "live_feed" ? "active" : ""}`}
            onClick={() => setAdvisorySource("live_feed")}
          >
            📡 Live Bengaluru Feed
          </button>
        </div>
      </div>

      {loading && (
        <div className="advisory-loading">
          <span className="spinner" /> Synthesizing Early-Warning Directives...
        </div>
      )}

      {error && <div className="error-alert">{error}</div>}

      {advisory && !loading && (
        <>
          {/* Header Banner */}
          <div
            className="alert-banner"
            style={{
              borderColor: levelColor,
              backgroundColor: levelBg,
            }}
          >
            <div className="alert-badge" style={{ backgroundColor: levelColor }}>
              {advisory.overall_alert_level.toUpperCase()} ALERT
            </div>
            <div className="alert-meta">
              <span className="alert-time">
                {new Date(advisory.timestamp).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}{" "}
                IST
              </span>
              <span className="alert-counts">
                {advisory.high_risk_spots_count} Critical · {advisory.watch_spots_count} Watch
              </span>
            </div>
          </div>

          {/* Citizen Advisory Section with Bilingual Toggle */}
          <section className="advisory-card">
            <div className="card-header">
              <h3>📢 Citizen Warning & Travel Advisory</h3>
              <div className="lang-tabs" role="tablist">
                <button
                  className={`btn-lang ${selectedLang === "en" ? "active" : ""}`}
                  onClick={() => setSelectedLang("en")}
                >
                  English
                </button>
                <button
                  className={`btn-lang ${selectedLang === "kn" ? "active" : ""}`}
                  onClick={() => setSelectedLang("kn")}
                >
                  ಕನ್ನಡ (Kannada)
                </button>
              </div>
            </div>

            <p className="advisory-text">
              {selectedLang === "en"
                ? advisory.citizen_advisory.english
                : advisory.citizen_advisory.kannada}
            </p>

            {advisory.citizen_advisory.avoid_underpasses.length > 0 && (
              <div className="avoid-list">
                <span className="section-label">⚠️ Underpasses to Avoid:</span>
                <div className="tags-row">
                  {advisory.citizen_advisory.avoid_underpasses.map((loc, idx) => (
                    <span key={idx} className="tag-warning">
                      {loc}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {advisory.citizen_advisory.suggested_routes.length > 0 && (
              <div className="routes-list">
                <span className="section-label">🚗 Recommended Routing:</span>
                <ul>
                  {advisory.citizen_advisory.suggested_routes.map((rt, idx) => (
                    <li key={idx}>{rt}</li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          {/* Municipal Action Plan (BBMP / Police Directives) */}
          <section className="advisory-card">
            <div className="card-header">
              <h3>🚜 Municipal & BBMP Action Directives</h3>
              <span className="priority-pill">{advisory.municipal_action_plan.priority_level}</span>
            </div>

            {/* Dewatering Pump Deployments */}
            <div className="action-subsection">
              <h4>Dewatering Pump Mobilization</h4>
              {advisory.municipal_action_plan.pump_deployments.length === 0 ? (
                <p className="action-empty">No emergency dewatering pump mobilization required.</p>
              ) : (
                <ul className="action-list">
                  {advisory.municipal_action_plan.pump_deployments.map((p, idx) => (
                    <li key={idx} className="action-item pump-item">
                      <div className="item-header">
                        <strong>{p.location}</strong>
                        <span className="capacity-badge">{p.capacity_gpm}</span>
                      </div>
                      <div className="item-action">{p.action}</div>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Barricade & Closure Orders */}
            {advisory.municipal_action_plan.barricade_orders.length > 0 && (
              <div className="action-subsection">
                <h4>Traffic Police Barricading Orders</h4>
                <ul className="action-list">
                  {advisory.municipal_action_plan.barricade_orders.map((b, idx) => (
                    <li key={idx} className="action-item barricade-item">
                      <strong>{b.location}</strong>: {b.action}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Traffic Diversions */}
            {advisory.municipal_action_plan.traffic_diversions.length > 0 && (
              <div className="action-subsection">
                <h4>Corridor Diversions</h4>
                <ul className="action-list">
                  {advisory.municipal_action_plan.traffic_diversions.map((d, idx) => (
                    <li key={idx} className="action-item diversion-item">
                      <strong>{d.route}</strong>: {d.alternate}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          {/* Provenance & Notes */}
          <footer className="advisory-footer">
            <span>Provider: {advisory.model_provider}</span>
            <span title={advisory.generation_notes}>ℹ️ Verified Rule Baseline</span>
          </footer>
        </>
      )}
    </div>
  );
}

