export type Level = "green" | "amber" | "red";

export interface RetrospectiveOutcome {
  actual_flood: boolean;
  severity: number | null;
  incident_id?: string | null;
  event_id?: string | null;
  source_name?: string | null;
  source_url?: string | null;
  notes?: string | null;
}

export interface SpotRisk {
  spot_id: string;
  name: string;
  lat: number;
  lng: number;
  risk: number;
  level: Level;
  lead_time_min: number | null;
  drivers: string[];
  rain_1h_mm?: number;
  rain_3h_mm?: number;
  rain_24h_mm?: number;
  data_quality_status?: string;
  retrospective_outcome?: RetrospectiveOutcome;
}

export interface RainInput {
  rain_1h_mm: number;
  rain_3h_mm: number;
  forecast_2h_mm: number;
}

export interface ReplayEvent {
  event_id: string;
  name: string;
  date_str: string;
  start_time: string;
  end_time: string;
  description: string;
  impacted_spots: string[];
  max_severity: number;
  citations: string[];
}

export interface ReplaySpotState {
  spot_id: string;
  name: string;
  lat: number;
  lng: number;
  predicted_risk: number;
  predicted_level: Level;
  lead_time_min: number | null;
  drivers: string[];
  rain_1h_mm: number;
  rain_3h_mm: number;
  rain_24h_mm: number;
  data_quality_status: string;
  retrospective_outcome: RetrospectiveOutcome;
}

export interface ReplayState {
  run_id: string;
  event_id: string;
  scenario_name: string;
  current_step: number;
  total_steps: number;
  timestamp: string;
  is_paused: boolean;
  is_completed: boolean;
  max_rainfall_rate_mm_h: number;
  spots: ReplaySpotState[];
  active_incidents_count: number;
}

export interface SpotWeather {
  spot_id: string;
  name: string;
  lat: number;
  lng: number;
  current_rain_mm_h: number;
  past_3h_mm: number;
  past_6h_mm: number;
  forecast_2h_mm: number;
  timestamp: string;
  source: string;
}

export interface LiveWeatherSummary {
  timestamp: string;
  bengaluru_avg_rain_1h: number;
  bengaluru_max_rain_1h: number;
  bengaluru_avg_forecast_2h: number;
  spots_weather: SpotWeather[];
  is_live: boolean;
  data_source: string;
  note: string;
}

export interface CitizenAdvisory {
  english: string;
  kannada: string;
  avoid_underpasses: string[];
  suggested_routes: string[];
}

export interface MunicipalActionPlan {
  priority_level: string;
  pump_deployments: Array<{ spot_id: string; location: string; capacity_gpm: string; action: string }>;
  barricade_orders: Array<{ location: string; action: string }>;
  traffic_diversions: Array<{ route: string; alternate: string }>;
}

export interface EmergencyAdvisory {
  timestamp: string;
  overall_alert_level: Level;
  summary: string;
  high_risk_spots_count: number;
  watch_spots_count: number;
  citizen_advisory: CitizenAdvisory;
  municipal_action_plan: MunicipalActionPlan;
  model_provider: string;
  generation_notes: string;
}

export type ReportType = "flood" | "control_clear";
export type SeverityLevel = "low" | "medium" | "high" | "critical";
export type VerificationStatus =
  | "submitted"
  | "under_review"
  | "approved"
  | "rejected"
  | "needs_info"
  | "pending"
  | "verified";

export interface CitizenReport {
  report_id: string;
  spot_id: string;
  spot_name?: string;
  report_type: ReportType;
  water_depth_cm?: number | null;
  severity?: number | null;
  severity_level?: SeverityLevel;
  latitude: number;
  longitude: number;
  image_url?: string | null;
  reporter_alias?: string;
  verification_status: VerificationStatus;
  verified_at?: string | null;
  verified_by?: string | null;
  notes?: string | null;
  duplicate_of_id?: string | null;
  decision_reason?: string | null;
  created_at: string;
}

export interface OperatorReportItem extends CitizenReport {
  nearby_reports_count: number;
  potential_duplicate_of?: string | null;
  duplicate_warning?: string | null;
}

export interface OperatorDecisionPayload {
  decision: "approved" | "rejected" | "needs_info" | "under_review";
  reviewer_id: string;
  reason?: string;
  duplicate_of_id?: string | null;
}

export interface OperationalEvidence {
  spot_id: string;
  spot_name: string;
  approved_reports_nearby: number;
  pending_reports_nearby: number;
  latest_verified_at: string | null;
  evidence_status: "none" | "watch" | "elevated" | "critical";
  confidence: "none" | "low" | "medium" | "high";
  freshness: "none" | "fresh" | "recent" | "decayed" | "expired";
  source: string;
  radius_meters: number;
  window_hours: number;
  explanation: string;
  approved_report_ids: string[];
  pending_report_ids: string[];
}

export interface OfflineQueuedReport {
  temp_id: string;
  payload: {
    spot_id?: string;
    report_type: ReportType;
    water_depth_cm?: number | null;
    severity_level: SeverityLevel;
    latitude: number;
    longitude: number;
    reporter_alias: string;
    notes: string;
  };
  image_base64?: string;
  image_name?: string;
  queued_at: string;
  sync_status: "pending" | "syncing" | "failed";
  error_message?: string;
}

/* -------------------------------------------------------------------------- */
/*             RESPONSE COORDINATION & IN-APP NOTIFICATIONS                   */
/* -------------------------------------------------------------------------- */

export type TaskStatus = "open" | "assigned" | "in_progress" | "resolved" | "cancelled";
export type TaskPriority = "P1_CRITICAL" | "P2_HIGH" | "P3_MEDIUM" | "P4_LOW";

export interface TaskPriorityFactor {
  factor: string;
  points: number;
  reason: string;
}

export interface TaskPriorityBreakdown {
  calculated_priority: TaskPriority;
  total_score: number;
  factors: TaskPriorityFactor[];
  explanation: string;
}

export interface TaskNote {
  note_id: number;
  task_id: string;
  author_id: string;
  author_role: string;
  note: string;
  created_at: string;
}

export interface ResponseTask {
  task_id: string;
  incident_report_id?: string | null;
  spot_id: string;
  location_name: string;
  latitude: number;
  longitude: number;
  title: string;
  description: string;
  priority: TaskPriority;
  priority_reasons?: TaskPriorityBreakdown | null;
  assigned_responder_id?: string | null;
  assigned_by?: string | null;
  status: TaskStatus;
  due_at?: string | null;
  resolution_notes?: string | null;
  resolution_image_url?: string | null;
  resolved_at?: string | null;
  notes: TaskNote[];
  created_at: string;
  updated_at: string;
}

export interface CreateTaskPayload {
  spot_id: string;
  title: string;
  description: string;
  incident_report_id?: string | null;
  assigned_responder_id?: string | null;
  priority?: TaskPriority | null;
  due_at?: string | null;
  latitude?: number | null;
  longitude?: number | null;
}

export interface InAppNotification {
  notification_id: string;
  task_id?: string | null;
  report_id?: string | null;
  target_audience: "operator" | "responder" | "public_advisory";
  target_responder_id?: string | null;
  title: string;
  message: string;
  severity: "info" | "warning" | "critical";
  delivery_status: "logged_locally" | "delivered_in_app" | "acknowledged" | "pending_approval";
  requires_human_approval: boolean;
  approved_by?: string | null;
  approved_at?: string | null;
  created_at: string;
}

