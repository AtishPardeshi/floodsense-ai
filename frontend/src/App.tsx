import { useEffect, useState } from "react";
import FloodMap from "./components/map/FloodMap";
import RiskOverview from "./components/dashboard/RiskOverview";
import Simulation from "./components/dashboard/Simulation";
import OperationalEvidenceView from "./components/dashboard/OperationalEvidenceView";
import CitizenReportView from "./components/citizen/CitizenReportView";
import ReportTrackingView from "./components/citizen/ReportTrackingView";
import OperatorDashboardView from "./components/operator/OperatorDashboardView";
import ResponderConsoleView from "./components/responder/ResponderConsoleView";
import NotificationCentreView from "./components/common/NotificationCentreView";
import ConnectionStatusBanner from "./components/common/ConnectionStatusBanner";
import { fetchRisk } from "./services/api";
import { fetchCitizenReports } from "./services/reportsApi";
import type { SpotRisk, ReplaySpotState, CitizenReport } from "./types";

type ViewMode = "live" | "replay" | "evidence" | "report" | "track" | "operator" | "responder" | "alerts";

export default function App() {
  const [viewMode, setViewMode] = useState<ViewMode>("live");
  const [rainNow, setRainNow] = useState(0); // mm/h falling now
  const [forecast, setForecast] = useState(0); // mm expected in the next 2 h
  const [liveSpots, setLiveSpots] = useState<SpotRisk[]>([]);
  const [replaySpots, setReplaySpots] = useState<SpotRisk[]>([]);
  const [, setReplayTimestamp] = useState<string>("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Citizen Reports & Evidence State
  const [citizenReports, setCitizenReports] = useState<CitizenReport[]>([]);
  const [customReportPin, setCustomReportPin] = useState<{ lat: number; lng: number } | null>(null);
  const [activeTrackingToken, setActiveTrackingToken] = useState<string | null>(null);

  // Poll or refresh reports for map markers
  const refreshReports = () => {
    fetchCitizenReports()
      .then((data) => setCitizenReports(data))
      .catch(() => {});
  };

  useEffect(() => {
    refreshReports();
    const interval = setInterval(refreshReports, 8000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (viewMode !== "live") return;
    const t = setTimeout(() => {
      fetchRisk({
        rain_1h_mm: rainNow,
        rain_3h_mm: rainNow * 2, // assumption until live 3 h totals are wired in
        forecast_2h_mm: forecast,
      })
        .then((data) => {
          setLiveSpots(data);
          setError(null);
        })
        .catch(() => setError("Can't reach the risk API. Start the backend with ./start.sh."));
    }, 150);
    return () => clearTimeout(t);
  }, [rainNow, forecast, viewMode]);

  const handleReplayUpdate = (spots: ReplaySpotState[], timestamp: string) => {
    // Map ReplaySpotState to SpotRisk for FloodMap compatibility
    const mapped: SpotRisk[] = spots.map((s) => ({
      spot_id: s.spot_id,
      name: s.name,
      lat: s.lat,
      lng: s.lng,
      risk: s.predicted_risk,
      level: s.predicted_level,
      lead_time_min: s.lead_time_min,
      drivers: s.drivers,
      rain_1h_mm: s.rain_1h_mm,
      rain_3h_mm: s.rain_3h_mm,
      rain_24h_mm: s.rain_24h_mm,
      data_quality_status: s.data_quality_status,
      retrospective_outcome: s.retrospective_outcome,
    }));
    setReplaySpots(mapped);
    setReplayTimestamp(timestamp);
  };

  const handleMapClick = (coords: { lat: number; lng: number }) => {
    if (viewMode === "report") {
      setCustomReportPin(coords);
    }
  };

  const handleNavigateToTrack = (reportId: string) => {
    setActiveTrackingToken(reportId);
    setViewMode("track");
    refreshReports();
  };

  const handleNavigateToReport = () => {
    setViewMode("report");
  };

  const handleSelectReportOnMap = (report: CitizenReport) => {
    // If report has spot_id, select it
    if (report.spot_id) {
      setSelectedId(report.spot_id);
    }
  };

  const activeSpots = viewMode === "replay" ? replaySpots : liveSpots;
  const redCount = activeSpots.filter((s) => s.level === "red").length;
  const activeFloodCount = activeSpots.filter((s) => s.retrospective_outcome?.actual_flood).length;

  return (
    <div className="layout">
      <aside className="panel">
        <header>
          <h1>FloodSense AI</h1>
          <p className="sub">Hyperlocal flood early warning for Bengaluru</p>
        </header>

        {/* Offline & PWA Sync Status Banner */}
        <ConnectionStatusBanner onQueueUpdated={refreshReports} />

        {/* View Mode Switcher */}
        <div className="view-mode-tabs" role="tablist">
          <button
            className={`tab-btn ${viewMode === "live" ? "active" : ""}`}
            onClick={() => setViewMode("live")}
            role="tab"
            aria-selected={viewMode === "live"}
          >
            ⚡ Live
          </button>
          <button
            className={`tab-btn ${viewMode === "replay" ? "active" : ""}`}
            onClick={() => setViewMode("replay")}
            role="tab"
            aria-selected={viewMode === "replay"}
          >
            ⏱️ Replay
          </button>
          <button
            className={`tab-btn ${viewMode === "evidence" ? "active" : ""}`}
            onClick={() => setViewMode("evidence")}
            role="tab"
            aria-selected={viewMode === "evidence"}
          >
            📊 Evidence
          </button>
          <button
            className={`tab-btn ${viewMode === "report" ? "active" : ""}`}
            onClick={() => setViewMode("report")}
            role="tab"
            aria-selected={viewMode === "report"}
          >
            📝 Report
          </button>
          <button
            className={`tab-btn ${viewMode === "track" ? "active" : ""}`}
            onClick={() => setViewMode("track")}
            role="tab"
            aria-selected={viewMode === "track"}
          >
            🔍 Track
          </button>
          <button
            className={`tab-btn ${viewMode === "operator" ? "active" : ""}`}
            onClick={() => setViewMode("operator")}
            role="tab"
            aria-selected={viewMode === "operator"}
          >
            🛡️ BBMP
          </button>
          <button
            className={`tab-btn ${viewMode === "responder" ? "active" : ""}`}
            onClick={() => setViewMode("responder")}
            role="tab"
            aria-selected={viewMode === "responder"}
          >
            🚜 Field
          </button>
          <button
            className={`tab-btn ${viewMode === "alerts" ? "active" : ""}`}
            onClick={() => setViewMode("alerts")}
            role="tab"
            aria-selected={viewMode === "alerts"}
          >
            🔔 Alerts
          </button>
        </div>

        {/* Mode-Specific Content */}
        {viewMode === "live" && (
          <>
            <section className="controls" aria-label="Rain scenario">
              <label>
                <span>Rain falling now: {rainNow} mm/h</span>
                <input
                  type="range"
                  min={0}
                  max={80}
                  value={rainNow}
                  onChange={(e) => setRainNow(+e.target.value)}
                />
              </label>
              <label>
                <span>Forecast for next 2 h: {forecast} mm</span>
                <input
                  type="range"
                  min={0}
                  max={150}
                  value={forecast}
                  onChange={(e) => setForecast(+e.target.value)}
                />
              </label>
            </section>

            <p className="summary" role="status">
              {error
                ? error
                : redCount > 0
                ? `${redCount} spot${redCount > 1 ? "s" : ""} likely to flood`
                : "No spots likely to flood"}
            </p>

            <RiskOverview spots={liveSpots} selectedId={selectedId} onSelect={setSelectedId} />
          </>
        )}

        {viewMode === "replay" && (
          <>
            <p className="summary" role="status">
              {activeFloodCount > 0 ? (
                <span style={{ color: "#003b6f", fontWeight: 600 }}>
                  🌊 {activeFloodCount} confirmed flood event{activeFloodCount > 1 ? "s" : ""} active
                </span>
              ) : redCount > 0 ? (
                `${redCount} location${redCount > 1 ? "s" : ""} flagged as likely to flood`
              ) : (
                "All locations below flood risk threshold"
              )}
            </p>

            <Simulation
              selectedId={selectedId}
              onSelect={setSelectedId}
              onReplayUpdate={handleReplayUpdate}
            />
          </>
        )}

        {viewMode === "evidence" && (
          <OperationalEvidenceView
            spots={activeSpots}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        )}

        {viewMode === "report" && (
          <CitizenReportView
            onNavigateToTrack={handleNavigateToTrack}
            selectedCoordinates={customReportPin}
          />
        )}

        {viewMode === "track" && (
          <ReportTrackingView
            initialToken={activeTrackingToken}
            onNavigateToReport={handleNavigateToReport}
          />
        )}

        {viewMode === "operator" && (
          <OperatorDashboardView
            onReportSelect={(rep) => handleSelectReportOnMap(rep)}
          />
        )}

        {viewMode === "responder" && (
          <ResponderConsoleView />
        )}

        {viewMode === "alerts" && (
          <NotificationCentreView />
        )}
      </aside>

      <FloodMap
        spots={activeSpots}
        selectedId={selectedId}
        onSelect={setSelectedId}
        customPin={viewMode === "report" ? customReportPin : null}
        onMapClick={handleMapClick}
        citizenReports={citizenReports}
        onReportSelect={handleSelectReportOnMap}
        isOperatorView={viewMode === "operator"}
      />
    </div>
  );
}
