import { useEffect, useState } from "react";
import { MapContainer, TileLayer, Marker, Popup, useMap, useMapEvents } from "react-leaflet";
import L from "leaflet";
import type { CitizenReport, SpotRisk } from "../../types";
import RiskMarker from "./RiskMarker";

const CENTER: [number, number] = [12.96, 77.64];

const customPinIcon = L.divIcon({
  className: "custom-report-pin",
  html: `<div style="background-color: #d9480f; width: 22px; height: 22px; border-radius: 50%; border: 2.5px solid #ffffff; box-shadow: 0 2px 6px rgba(0,0,0,0.35); display: flex; align-items: center; justify-content: center; color: white; font-size: 11px;">📍</div>`,
  iconSize: [24, 24],
  iconAnchor: [12, 12],
});

const approvedReportIcon = L.divIcon({
  className: "approved-report-pin",
  html: `<div style="background-color: #005a9c; width: 22px; height: 22px; border-radius: 50%; border: 2.5px solid #ffffff; box-shadow: 0 2px 6px rgba(0,90,156,0.4); display: flex; align-items: center; justify-content: center; color: white; font-size: 11px; font-weight: bold;">✓</div>`,
  iconSize: [24, 24],
  iconAnchor: [12, 12],
});

const pendingReportIcon = L.divIcon({
  className: "pending-report-pin",
  html: `<div style="background-color: #e67700; width: 22px; height: 22px; border-radius: 50%; border: 2.5px solid #ffffff; box-shadow: 0 2px 6px rgba(230,119,0,0.4); display: flex; align-items: center; justify-content: center; color: white; font-size: 11px;">⏳</div>`,
  iconSize: [24, 24],
  iconAnchor: [12, 12],
});

const rejectedReportIcon = L.divIcon({
  className: "rejected-report-pin",
  html: `<div style="background-color: #868e96; width: 20px; height: 20px; border-radius: 50%; border: 2px solid #ffffff; box-shadow: 0 1px 4px rgba(0,0,0,0.25); display: flex; align-items: center; justify-content: center; color: white; font-size: 10px;">✕</div>`,
  iconSize: [20, 20],
  iconAnchor: [10, 10],
});

function FlyToSelected({ spots, selectedId }: { spots: SpotRisk[]; selectedId: string | null }) {
  const map = useMap();
  useEffect(() => {
    const s = spots.find((x) => x.spot_id === selectedId);
    if (s) map.flyTo([s.lat, s.lng], Math.max(map.getZoom(), 14), { duration: 0.6 });
  }, [selectedId]);
  return null;
}

function MapClickHandler({ onMapClick }: { onMapClick?: (coords: { lat: number; lng: number }) => void }) {
  useMapEvents({
    click(e) {
      if (onMapClick) {
        onMapClick({ lat: e.latlng.lat, lng: e.latlng.lng });
      }
    },
  });
  return null;
}

interface Props {
  spots: SpotRisk[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  customPin?: { lat: number; lng: number } | null;
  onMapClick?: (coords: { lat: number; lng: number }) => void;
  citizenReports?: CitizenReport[];
  onReportSelect?: (report: CitizenReport) => void;
  isOperatorView?: boolean;
}

export default function FloodMap({
  spots,
  selectedId,
  onSelect,
  customPin,
  onMapClick,
  citizenReports = [],
  onReportSelect,
  isOperatorView = false,
}: Props) {
  const [showSpots, setShowSpots] = useState<boolean>(true);
  const [showApproved, setShowApproved] = useState<boolean>(true);
  const [showPending, setShowPending] = useState<boolean>(true);
  const [showRejected, setShowRejected] = useState<boolean>(false);

  const approvedReports = citizenReports.filter(
    (r) => r.verification_status === "approved" || r.verification_status === "verified"
  );
  const pendingReports = citizenReports.filter((r) =>
    ["submitted", "pending", "under_review", "needs_info"].includes(r.verification_status)
  );
  const rejectedReports = citizenReports.filter((r) => r.verification_status === "rejected");

  return (
    <div className="map-wrapper">
      {/* Floating Map Filter Toolbar */}
      <div className="map-layer-controls">
        <span className="layer-title">Map Layers:</span>
        <label className="layer-toggle-lbl">
          <input
            type="checkbox"
            checked={showSpots}
            onChange={(e) => setShowSpots(e.target.checked)}
          />
          <span>Hotspots ({spots.length})</span>
        </label>
        <label className="layer-toggle-lbl text-blue">
          <input
            type="checkbox"
            checked={showApproved}
            onChange={(e) => setShowApproved(e.target.checked)}
          />
          <span>Approved ({approvedReports.length})</span>
        </label>
        <label className="layer-toggle-lbl text-amber">
          <input
            type="checkbox"
            checked={showPending}
            onChange={(e) => setShowPending(e.target.checked)}
          />
          <span>Pending ({pendingReports.length})</span>
        </label>
        {isOperatorView && (
          <label className="layer-toggle-lbl text-muted">
            <input
              type="checkbox"
              checked={showRejected}
              onChange={(e) => setShowRejected(e.target.checked)}
            />
            <span>Rejected ({rejectedReports.length})</span>
          </label>
        )}
      </div>

      <MapContainer center={CENTER} zoom={12} className="map" scrollWheelZoom>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {/* 1. Monitored Hotspots */}
        {showSpots &&
          spots.map((s) => (
            <RiskMarker
              key={s.spot_id}
              spot={s}
              selected={s.spot_id === selectedId}
              onSelect={onSelect}
            />
          ))}

        {/* 2. Approved Verified Reports */}
        {showApproved &&
          approvedReports.map((r) => (
            <Marker key={r.report_id} position={[r.latitude, r.longitude]} icon={approvedReportIcon}>
              <Popup>
                <div className="report-popup">
                  <div className="popup-badge-row">
                    <span className="status-pill status-approved">✓ Verified Evidence</span>
                    <span className="popup-time">
                      {new Date(r.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  </div>
                  <strong>{r.spot_name || "Crowd Report"}</strong>
                  <p className="popup-notes">&quot;{r.notes || "No notes"}&quot;</p>
                  {r.water_depth_cm && <p className="popup-depth">Observed depth: {r.water_depth_cm} cm</p>}
                  {r.image_url && (
                    <img
                      src={`http://localhost:8000${r.image_url}`}
                      alt="Evidence"
                      className="popup-thumb"
                    />
                  )}
                  {onReportSelect && (
                    <button
                      type="button"
                      className="btn btn-secondary btn-xs popup-btn"
                      onClick={() => onReportSelect(r)}
                    >
                      View Details
                    </button>
                  )}
                </div>
              </Popup>
            </Marker>
          ))}

        {/* 3. Pending Citizen Reports */}
        {showPending &&
          pendingReports.map((r) => (
            <Marker key={r.report_id} position={[r.latitude, r.longitude]} icon={pendingReportIcon}>
              <Popup>
                <div className="report-popup">
                  <div className="popup-badge-row">
                    <span className="status-pill status-review">⏳ Unverified Pending Report</span>
                    <span className="popup-time">
                      {new Date(r.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  </div>
                  <strong>{r.spot_name || "Citizen Observation"}</strong>
                  <p className="popup-notes">&quot;{r.notes || "No notes"}&quot;</p>
                  <p className="popup-disclaimer">
                    <em>Awaiting municipal cross-verification.</em>
                  </p>
                  {onReportSelect && (
                    <button
                      type="button"
                      className="btn btn-secondary btn-xs popup-btn"
                      onClick={() => onReportSelect(r)}
                    >
                      View in Queue
                    </button>
                  )}
                </div>
              </Popup>
            </Marker>
          ))}

        {/* 4. Rejected Reports (Only visible when toggled by operator) */}
        {showRejected &&
          rejectedReports.map((r) => (
            <Marker key={r.report_id} position={[r.latitude, r.longitude]} icon={rejectedReportIcon}>
              <Popup>
                <div className="report-popup">
                  <div className="popup-badge-row">
                    <span className="status-pill status-rejected">✕ Rejected Report</span>
                  </div>
                  <p className="popup-notes">&quot;{r.notes}&quot;</p>
                  {r.decision_reason && <p className="popup-reason">Reason: {r.decision_reason}</p>}
                </div>
              </Popup>
            </Marker>
          ))}

        {/* 5. Custom Pin when in Citizen Reporting Mode */}
        {customPin && (
          <Marker position={[customPin.lat, customPin.lng]} icon={customPinIcon}>
            <Popup>
              <strong>Selected Citizen Pin</strong>
              <br />
              Lat: {customPin.lat.toFixed(4)}, Lng: {customPin.lng.toFixed(4)}
            </Popup>
          </Marker>
        )}

        <MapClickHandler onMapClick={onMapClick} />
        <FlyToSelected spots={spots} selectedId={selectedId} />
      </MapContainer>
    </div>
  );
}
