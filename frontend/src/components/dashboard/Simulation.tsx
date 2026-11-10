import { useEffect, useState, useRef } from "react";
import type { ReplayEvent, ReplayState, ReplaySpotState } from "../../types";
import {
  fetchReplayEvents,
  startReplay,
  nextReplayStep,
  pauseReplay,
  resumeReplay,
  resetReplay,
} from "../../services/api";
import { LEVEL_COLOR, LEVEL_LABEL } from "../map/RiskMarker";

interface Props {
  selectedId: string | null;
  onSelect: (id: string) => void;
  onReplayUpdate: (spots: ReplaySpotState[], timestamp: string) => void;
}

export default function Simulation({ selectedId, onSelect, onReplayUpdate }: Props) {
  const [events, setEvents] = useState<ReplayEvent[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<string>("ev_20220905_deluge");
  const [replayState, setReplayState] = useState<ReplayState | null>(null);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1000); // ms per step
  const [error, setError] = useState<string | null>(null);

  const timerRef = useRef<number | null>(null);

  // Load available historical storm events on mount
  useEffect(() => {
    fetchReplayEvents()
      .then((data) => {
        setEvents(data);
        if (data.length > 0 && !selectedEventId) {
          setSelectedEventId(data[0].event_id);
        }
      })
      .catch((err) => setError(`Failed to fetch events: ${err.message}`));
  }, []);

  // Initialize selected scenario replay session
  useEffect(() => {
    if (!selectedEventId) return;
    setIsPlaying(false);
    if (timerRef.current) clearInterval(timerRef.current);

    startReplay(selectedEventId)
      .then((state) => {
        setReplayState(state);
        onReplayUpdate(state.spots, state.timestamp);
        setError(null);
      })
      .catch((err) => setError(`Failed to start replay: ${err.message}`));
  }, [selectedEventId]);

  // Handle automatic ticker when playing
  useEffect(() => {
    if (isPlaying && replayState && !replayState.is_completed) {
      timerRef.current = window.setInterval(() => {
        nextReplayStep(replayState.run_id)
          .then((newState) => {
            setReplayState(newState);
            onReplayUpdate(newState.spots, newState.timestamp);
            if (newState.is_completed) {
              setIsPlaying(false);
            }
          })
          .catch((err) => {
            setIsPlaying(false);
            setError(`Step error: ${err.message}`);
          });
      }, playbackSpeed);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isPlaying, playbackSpeed, replayState?.run_id]);

  const handleTogglePlay = () => {
    if (!replayState) return;
    if (replayState.is_completed) {
      // Loop or reset
      handleReset();
      setIsPlaying(true);
      return;
    }
    if (isPlaying) {
      pauseReplay(replayState.run_id).catch(() => {});
      setIsPlaying(false);
    } else {
      resumeReplay(replayState.run_id).catch(() => {});
      setIsPlaying(true);
    }
  };

  const handleStep = () => {
    if (!replayState || replayState.is_completed) return;
    setIsPlaying(false);
    nextReplayStep(replayState.run_id)
      .then((newState) => {
        setReplayState(newState);
        onReplayUpdate(newState.spots, newState.timestamp);
      })
      .catch((err) => setError(err.message));
  };

  const handleReset = () => {
    if (!replayState) return;
    setIsPlaying(false);
    resetReplay(replayState.run_id)
      .then((newState) => {
        setReplayState(newState);
        onReplayUpdate(newState.spots, newState.timestamp);
      })
      .catch((err) => setError(err.message));
  };

  const selectedSpot = replayState?.spots.find((s) => s.spot_id === selectedId);

  return (
    <div className="simulation-container">
      {/* Prominent Historical Simulation Disclaimer */}
      <div className="disclaimer-banner" role="alert">
        <span className="disclaimer-icon">⚠️</span>
        <div className="disclaimer-text">
          <strong>Historical Storm Replay:</strong> Retrospective reconstruction using archived Open-Meteo
          reanalysis rainfall. Model predictions are generated strictly from antecedent data.{" "}
          <em>This is a research simulation, not a live warning.</em>
        </div>
      </div>

      {/* Scenario Selector */}
      <div className="scenario-selector">
        <label htmlFor="scenario-select" className="control-label">
          Documented Historical Storm:
        </label>
        <select
          id="scenario-select"
          className="scenario-dropdown"
          value={selectedEventId}
          onChange={(e) => setSelectedEventId(e.target.value)}
        >
          {events.map((ev) => (
            <option key={ev.event_id} value={ev.event_id}>
              {ev.name} ({ev.date_str})
            </option>
          ))}
        </select>
      </div>

      {error && <div className="error-alert">{error}</div>}

      {/* Playback Controls & Status */}
      {replayState && (
        <section className="playback-panel" aria-label="Replay Controls">
          <div className="timestamp-badge">
            <span className="label">REPLAY TIMESTEP (IST):</span>
            <span className="value">
              {new Date(replayState.timestamp).toLocaleString("en-IN", {
                timeZone: "Asia/Kolkata",
                month: "short",
                day: "numeric",
                year: "numeric",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          </div>

          <div className="progress-bar-container">
            <div
              className="progress-fill"
              style={{
                width: `${((replayState.current_step + 1) / replayState.total_steps) * 100}%`,
              }}
            />
          </div>
          <div className="progress-text">
            <span>
              Hour {replayState.current_step + 1} of {replayState.total_steps}
            </span>
            <span>Peak Hourly Rain: {replayState.max_rainfall_rate_mm_h} mm/h</span>
          </div>

          <div className="button-toolbar">
            <button
              className="btn btn-primary"
              onClick={handleTogglePlay}
              title={isPlaying ? "Pause simulation" : "Play simulation"}
            >
              {isPlaying ? "⏸️ Pause" : replayState.is_completed ? "🔄 Replay" : "▶️ Play"}
            </button>
            <button
              className="btn btn-secondary"
              onClick={handleStep}
              disabled={replayState.is_completed || isPlaying}
              title="Advance one hour"
            >
              ⏭️ Step (+1h)
            </button>
            <button className="btn btn-ghost" onClick={handleReset} title="Reset to start">
              ⏮️ Reset
            </button>
            <div className="speed-toggle">
              <button
                className={`btn-speed ${playbackSpeed === 1500 ? "active" : ""}`}
                onClick={() => setPlaybackSpeed(1500)}
              >
                1x
              </button>
              <button
                className={`btn-speed ${playbackSpeed === 800 ? "active" : ""}`}
                onClick={() => setPlaybackSpeed(800)}
              >
                2x
              </button>
              <button
                className={`btn-speed ${playbackSpeed === 350 ? "active" : ""}`}
                onClick={() => setPlaybackSpeed(350)}
              >
                5x
              </button>
            </div>
          </div>
        </section>
      )}

      {/* Selected Spot Details & Physical Explainability Panel */}
      {selectedSpot && (
        <section className="detail-panel">
          <div className="detail-header">
            <h3>{selectedSpot.name}</h3>
            <span
              className="badge"
              style={{
                background: LEVEL_COLOR[selectedSpot.predicted_level],
                color: "#fff",
              }}
            >
              {LEVEL_LABEL[selectedSpot.predicted_level]} ({Math.round(selectedSpot.predicted_risk * 100)}%)
            </span>
          </div>

          {/* Actual Historical Outcome Overlay */}
          {selectedSpot.retrospective_outcome?.actual_flood ? (
            <div className="outcome-alert confirmed">
              <span className="outcome-icon">🌊</span>
              <div>
                <strong>Documented Flood Event:</strong> Severity Level{" "}
                {selectedSpot.retrospective_outcome.severity}/3.
                {selectedSpot.retrospective_outcome.source_name && (
                  <div style={{ marginTop: 2, fontSize: "0.85rem" }}>
                    Source:{" "}
                    {selectedSpot.retrospective_outcome.source_url ? (
                      <a
                        href={selectedSpot.retrospective_outcome.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="source-link"
                      >
                        {selectedSpot.retrospective_outcome.source_name} ↗
                      </a>
                    ) : (
                      selectedSpot.retrospective_outcome.source_name
                    )}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="outcome-alert unverified">
              <span>ℹ️</span>
              <div>
                <strong>Retrospective Status:</strong> No flood incident documented at this specific hour.
              </div>
            </div>
          )}

          <div className="metrics-grid">
            <div className="metric-box">
              <span className="metric-label">Rain 1h:</span>
              <span className="metric-val">{selectedSpot.rain_1h_mm.toFixed(1)} mm</span>
            </div>
            <div className="metric-box">
              <span className="metric-label">Rain 3h:</span>
              <span className="metric-val">{selectedSpot.rain_3h_mm.toFixed(1)} mm</span>
            </div>
            <div className="metric-box">
              <span className="metric-label">Rain 24h:</span>
              <span className="metric-val">{selectedSpot.rain_24h_mm.toFixed(1)} mm</span>
            </div>
          </div>

          {selectedSpot.drivers && selectedSpot.drivers.length > 0 && (
            <div className="drivers-box">
              <span className="drivers-title">Contributing Physical Drivers:</span>
              <ul>
                {selectedSpot.drivers.map((d) => (
                  <li key={d}>{d}</li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      {/* Spot List */}
      {replayState && (
        <ol className="spot-list">
          {replayState.spots.map((s) => {
            const hasActual = s.retrospective_outcome?.actual_flood;
            return (
              <li key={s.spot_id}>
                <button
                  className={`spot-row${s.spot_id === selectedId ? " is-selected" : ""}${
                    hasActual ? " has-actual-flood" : ""
                  }`}
                  onClick={() => onSelect(s.spot_id)}
                >
                  <span className="dot" style={{ background: LEVEL_COLOR[s.predicted_level] }} aria-hidden />
                  <span className="spot-main">
                    <span className="spot-name">
                      {s.name}
                      {hasActual && <span className="actual-tag">🌊 FLOOD</span>}
                    </span>
                    <span className="spot-meta">
                      {LEVEL_LABEL[s.predicted_level]}
                      {s.lead_time_min ? ` · warn ${s.lead_time_min}m ahead` : ""}
                      {` · Rain: ${s.rain_1h_mm} mm/h`}
                    </span>
                  </span>
                  <span className="spot-score">{Math.round(s.predicted_risk * 100)}%</span>
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

