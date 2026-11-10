import type { SpotRisk } from "../../types";
import { LEVEL_COLOR, LEVEL_LABEL } from "../map/RiskMarker";

interface Props {
  spots: SpotRisk[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export default function RiskOverview({ spots, selectedId, onSelect }: Props) {
  return (
    <ol className="spot-list">
      {spots.map((s) => (
        <li key={s.spot_id}>
          <button
            className={`spot-row${s.spot_id === selectedId ? " is-selected" : ""}`}
            onClick={() => onSelect(s.spot_id)}
          >
            <span className="dot" style={{ background: LEVEL_COLOR[s.level] }} aria-hidden />
            <span className="spot-main">
              <span className="spot-name">{s.name}</span>
              <span className="spot-meta">
                {LEVEL_LABEL[s.level]}
                {s.lead_time_min ? ` · warn ${s.lead_time_min} min ahead` : ""}
              </span>
            </span>
            <span className="spot-score">{Math.round(s.risk * 100)}%</span>
          </button>
        </li>
      ))}
    </ol>
  );
}
