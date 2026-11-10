import { CircleMarker, Popup } from "react-leaflet";
import type { Level, SpotRisk } from "../../types";

export const LEVEL_COLOR: Record<Level, string> = {
  green: "#2e7d5b",
  amber: "#d9962b",
  red: "#c23b2e",
};

export const LEVEL_LABEL: Record<Level, string> = {
  green: "Low risk",
  amber: "Watch",
  red: "Likely to flood",
};

interface Props {
  spot: SpotRisk;
  selected: boolean;
  onSelect: (id: string) => void;
}

export default function RiskMarker({ spot, selected, onSelect }: Props) {
  const color = LEVEL_COLOR[spot.level];
  const actualFlood = spot.retrospective_outcome?.actual_flood;

  return (
    <CircleMarker
      center={[spot.lat, spot.lng]}
      radius={actualFlood ? 12 + spot.risk * 14 : 9 + spot.risk * 14}
      pathOptions={{
        color: actualFlood ? "#003b6f" : selected ? "#14263a" : color,
        weight: actualFlood ? 4 : selected ? 3 : 2,
        fillColor: color,
        fillOpacity: actualFlood ? 0.8 : 0.55,
      }}
      eventHandlers={{ click: () => onSelect(spot.spot_id) }}
    >
      <Popup>
        <div style={{ minWidth: 200 }}>
          <strong>{spot.name}</strong>
          <div style={{ margin: "4px 0" }}>
            <span style={{ color, fontWeight: 600 }}>{LEVEL_LABEL[spot.level]}</span> ·{" "}
            <strong>{Math.round(spot.risk * 100)}%</strong> physical risk
          </div>
          {spot.lead_time_min ? (
            <div style={{ fontSize: "0.85rem", color: "#1f6f8b" }}>
              ⏱️ Warning lead: about {spot.lead_time_min} min ahead
            </div>
          ) : null}

          {/* Retrospective Outcome Overlay */}
          {actualFlood && (
            <div
              style={{
                marginTop: 8,
                padding: "6px 8px",
                background: "#e8f4fd",
                borderLeft: "3px solid #005a9c",
                borderRadius: 4,
                fontSize: "0.85rem",
              }}
            >
              <div style={{ fontWeight: 600, color: "#003b6f" }}>🌊 Documented Flood Outcome</div>
              <div>Severity: Level {spot.retrospective_outcome?.severity} / 3</div>
              {spot.retrospective_outcome?.source_name && (
                <div style={{ marginTop: 2 }}>
                  Source:{" "}
                  {spot.retrospective_outcome?.source_url ? (
                    <a
                      href={spot.retrospective_outcome.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: "#005a9c", textDecoration: "underline" }}
                    >
                      {spot.retrospective_outcome.source_name}
                    </a>
                  ) : (
                    spot.retrospective_outcome.source_name
                  )}
                </div>
              )}
            </div>
          )}

          {/* Contributing Drivers */}
          {spot.drivers && spot.drivers.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <span style={{ fontSize: "0.8rem", color: "#5b6b7b", fontWeight: 500 }}>
                Contributing Physical Factors:
              </span>
              <ul className="popup-drivers" style={{ margin: "4px 0 0", paddingLeft: 16, fontSize: "0.85rem" }}>
                {spot.drivers.map((d) => (
                  <li key={d}>{d}</li>
                ))}
              </ul>
            </div>
          )}

          {spot.data_quality_status && (
            <div style={{ marginTop: 6, fontSize: "0.75rem", color: "#8a9ba8" }}>
              DEM Data: {spot.data_quality_status.toUpperCase()}
            </div>
          )}
        </div>
      </Popup>
    </CircleMarker>
  );
}
