import type {
  CitizenReport,
  OfflineQueuedReport,
  OperationalEvidence,
  OperatorDecisionPayload,
  OperatorReportItem,
} from "../types";

const API_BASE = "http://localhost:8000/api";
const QUEUE_STORAGE_KEY = "floodsense_offline_reports_queue_v1";
const DRAFT_STORAGE_KEY = "floodsense_report_draft_v1";
const RECENT_IDS_KEY = "floodsense_recent_submitted_ids_v1";
const OPERATOR_KEY_STORAGE = "floodsense_operator_key_v1";

export function getSavedOperatorKey(): string {
  return localStorage.getItem(OPERATOR_KEY_STORAGE) || "bbmp-operator-secret-2026";
}

export function saveOperatorKey(key: string): void {
  localStorage.setItem(OPERATOR_KEY_STORAGE, key.trim());
}

/**
 * Submits a citizen report to the backend.
 */
export async function submitCitizenReport(formData: FormData): Promise<CitizenReport> {
  const res = await fetch(`${API_BASE}/reports`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({ detail: "Network error submitting report." }));
    throw new Error(errorBody.detail || `Server returned ${res.status}`);
  }

  const data: CitizenReport = await res.json();
  addRecentSubmittedId(data.report_id);
  return data;
}

/**
 * Retrieves report status and details by tracking token.
 */
export async function fetchReportById(reportId: string): Promise<CitizenReport> {
  const cleanId = reportId.trim();
  const res = await fetch(`${API_BASE}/reports/${encodeURIComponent(cleanId)}`);

  if (!res.ok) {
    if (res.status === 404) {
      throw new Error(`Report ID "${cleanId}" not found. Please verify the tracking token.`);
    }
    throw new Error(`Unable to fetch report details (${res.status})`);
  }

  return res.json();
}

/**
 * Fetches recent citizen reports with optional filters.
 */
export async function fetchCitizenReports(spotId?: string, status?: string): Promise<CitizenReport[]> {
  const params = new URLSearchParams();
  if (spotId) params.append("spot_id", spotId);
  if (status && status !== "all") params.append("status", status);

  const res = await fetch(`${API_BASE}/reports?${params.toString()}`);
  if (!res.ok) {
    throw new Error("Failed to load citizen reports ledger.");
  }
  return res.json();
}

/* -------------------------------------------------------------------------- */
/*                       MUNICIPAL OPERATOR API CALLS                         */
/* -------------------------------------------------------------------------- */

export async function fetchOperatorQueue(
  operatorKey: string,
  status?: string
): Promise<OperatorReportItem[]> {
  const params = new URLSearchParams();
  if (status && status !== "all") params.append("status", status);

  const res = await fetch(`${API_BASE}/operator/queue?${params.toString()}`, {
    headers: {
      "X-Operator-Key": operatorKey,
    },
  });

  if (!res.ok) {
    if (res.status === 401) {
      throw new Error("Unauthorized: Invalid municipal operator key.");
    }
    throw new Error(`Failed to load operator review queue (${res.status}).`);
  }

  return res.json();
}

export async function submitOperatorDecision(
  reportId: string,
  payload: OperatorDecisionPayload,
  operatorKey: string
): Promise<CitizenReport> {
  const res = await fetch(`${API_BASE}/operator/reports/${encodeURIComponent(reportId)}/decision`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Operator-Key": operatorKey,
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Operation failed" }));
    throw new Error(err.detail || `Server returned ${res.status}`);
  }

  return res.json();
}

export async function linkOperatorDuplicate(
  reportId: string,
  parentReportId: string,
  operatorKey: string,
  reason?: string
): Promise<CitizenReport> {
  const params = new URLSearchParams({ parent_report_id: parentReportId });
  if (reason) params.append("reason", reason);

  const res = await fetch(
    `${API_BASE}/operator/reports/${encodeURIComponent(reportId)}/link-duplicate?${params.toString()}`,
    {
      method: "POST",
      headers: {
        "X-Operator-Key": operatorKey,
      },
    }
  );

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Linking duplicate failed" }));
    throw new Error(err.detail || `Server returned ${res.status}`);
  }

  return res.json();
}

/* -------------------------------------------------------------------------- */
/*                    OPERATIONAL EVIDENCE OVERLAY API CALLS                  */
/* -------------------------------------------------------------------------- */

export async function fetchOperationalEvidence(
  radiusMeters: number = 1500,
  windowHours: number = 6
): Promise<OperationalEvidence[]> {
  const params = new URLSearchParams({
    radius_meters: String(radiusMeters),
    window_hours: String(windowHours),
  });
  const res = await fetch(`${API_BASE}/evidence?${params.toString()}`);
  if (!res.ok) {
    throw new Error("Failed to fetch operational evidence overlay.");
  }
  return res.json();
}

export async function fetchSpotEvidence(
  spotId: string,
  radiusMeters: number = 1500,
  windowHours: number = 6
): Promise<OperationalEvidence> {
  const params = new URLSearchParams({
    radius_meters: String(radiusMeters),
    window_hours: String(windowHours),
  });
  const res = await fetch(`${API_BASE}/evidence/${encodeURIComponent(spotId)}?${params.toString()}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch evidence overlay for spot ${spotId}.`);
  }
  return res.json();
}

/* -------------------------------------------------------------------------- */
/*                        OFFLINE DRAFT & QUEUE STORAGE                       */
/* -------------------------------------------------------------------------- */

export function saveDraft(draft: Partial<OfflineQueuedReport["payload"]>): void {
  try {
    localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(draft));
  } catch (e) {
    console.warn("Could not save draft to localStorage:", e);
  }
}

export function getDraft(): Partial<OfflineQueuedReport["payload"]> | null {
  try {
    const raw = localStorage.getItem(DRAFT_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function clearDraft(): void {
  try {
    localStorage.removeItem(DRAFT_STORAGE_KEY);
  } catch {}
}

export function getOfflineQueue(): OfflineQueuedReport[] {
  try {
    const raw = localStorage.getItem(QUEUE_STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function saveOfflineQueue(queue: OfflineQueuedReport[]): void {
  try {
    localStorage.setItem(QUEUE_STORAGE_KEY, JSON.stringify(queue));
  } catch (e) {
    console.warn("Could not save offline queue:", e);
  }
}

export function enqueueOfflineReport(
  payload: OfflineQueuedReport["payload"],
  imageBase64?: string,
  imageName?: string
): OfflineQueuedReport {
  const queue = getOfflineQueue();
  const queuedItem: OfflineQueuedReport = {
    temp_id: `offline_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
    payload,
    image_base64: imageBase64,
    image_name: imageName,
    queued_at: new Date().toISOString(),
    sync_status: "pending",
  };

  queue.push(queuedItem);
  saveOfflineQueue(queue);
  return queuedItem;
}

export function removeOfflineReport(tempId: string): void {
  const queue = getOfflineQueue().filter((item) => item.temp_id !== tempId);
  saveOfflineQueue(queue);
}

/**
 * Attempts to flush and synchronize all locally queued offline reports to the server.
 */
export async function flushOfflineQueue(): Promise<{ synced: number; failed: number }> {
  const queue = getOfflineQueue();
  if (queue.length === 0) return { synced: 0, failed: 0 };

  let synced = 0;
  let failed = 0;
  const remainingQueue: OfflineQueuedReport[] = [];

  for (const item of queue) {
    try {
      const formData = new FormData();
      if (item.payload.spot_id) formData.append("spot_id", item.payload.spot_id);
      formData.append("report_type", item.payload.report_type);
      if (item.payload.water_depth_cm !== null && item.payload.water_depth_cm !== undefined) {
        formData.append("water_depth_cm", String(item.payload.water_depth_cm));
      }
      formData.append("severity_level", item.payload.severity_level);
      formData.append("latitude", String(item.payload.latitude));
      formData.append("longitude", String(item.payload.longitude));
      formData.append("reporter_alias", item.payload.reporter_alias);
      formData.append("notes", item.payload.notes);

      // Reconstruct file from base64 if present
      if (item.image_base64 && item.image_name) {
        const res = await fetch(item.image_base64);
        const blob = await res.blob();
        formData.append("image", blob, item.image_name);
      }

      await submitCitizenReport(formData);
      synced++;
    } catch (err: any) {
      failed++;
      remainingQueue.push({
        ...item,
        sync_status: "failed",
        error_message: err?.message || "Sync attempt failed",
      });
    }
  }

  saveOfflineQueue(remainingQueue);
  return { synced, failed };
}

/* -------------------------------------------------------------------------- */
/*                       RECENT SUBMITTED TOKENS HELPER                       */
/* -------------------------------------------------------------------------- */

export function getRecentSubmittedIds(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_IDS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function addRecentSubmittedId(id: string): void {
  try {
    const existing = getRecentSubmittedIds().filter((existingId) => existingId !== id);
    existing.unshift(id);
    // keep last 10
    localStorage.setItem(RECENT_IDS_KEY, JSON.stringify(existing.slice(0, 10)));
  } catch {}
}

/* -------------------------------------------------------------------------- */
/*             RESPONSE COORDINATION & IN-APP NOTIFICATIONS API               */
/* -------------------------------------------------------------------------- */

const RESPONDER_ID_STORAGE = "floodsense_responder_id_v1";

export function getSavedResponderId(): string {
  return localStorage.getItem(RESPONDER_ID_STORAGE) || "BBMP_Rapid_Unit_1";
}

export function saveResponderId(id: string): void {
  localStorage.setItem(RESPONDER_ID_STORAGE, id.trim());
}

/**
 * Creates a response task from verified flood intelligence. Requires operator authorization.
 */
export async function createResponseTask(
  payload: import("../types").CreateTaskPayload,
  operatorKey: string
): Promise<import("../types").ResponseTask> {
  const res = await fetch(`${API_BASE}/coordination/tasks`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Operator-Key": operatorKey,
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(err.detail || `Failed to create task (${res.status})`);
  }

  return res.json();
}

/**
 * Lists civic response tasks with optional filters.
 */
export async function fetchResponseTasks(params?: {
  status?: string;
  responder_id?: string;
  spot_id?: string;
}): Promise<import("../types").ResponseTask[]> {
  const urlParams = new URLSearchParams();
  if (params?.status && params.status !== "all") urlParams.append("status", params.status);
  if (params?.responder_id) urlParams.append("responder_id", params.responder_id);
  if (params?.spot_id) urlParams.append("spot_id", params.spot_id);

  const res = await fetch(`${API_BASE}/coordination/tasks?${urlParams.toString()}`);
  if (!res.ok) {
    throw new Error(`Failed to load response tasks (${res.status})`);
  }

  return res.json();
}

/**
 * Previews deterministic prioritization breakdown before task creation.
 */
export async function fetchTaskPriorityPreview(
  spotId: string,
  reportId?: string,
  overrideSeverity?: number
): Promise<import("../types").TaskPriorityBreakdown> {
  const params = new URLSearchParams({ spot_id: spotId });
  if (reportId) params.append("incident_report_id", reportId);
  if (overrideSeverity) params.append("override_severity", String(overrideSeverity));

  const res = await fetch(`${API_BASE}/coordination/tasks/priority-preview?${params.toString()}`);
  if (!res.ok) {
    throw new Error("Failed to precalculate priority breakdown.");
  }

  return res.json();
}

/**
 * Fetches single response task by ID.
 */
export async function fetchTaskById(taskId: string): Promise<import("../types").ResponseTask> {
  const res = await fetch(`${API_BASE}/coordination/tasks/${encodeURIComponent(taskId)}`);
  if (!res.ok) {
    throw new Error(`Task ${taskId} not found.`);
  }
  return res.json();
}

/**
 * Assigns an open task to a field unit. Requires operator authorization.
 */
export async function assignResponseTask(
  taskId: string,
  responderId: string,
  operatorKey: string,
  operatorId: string = "BBMP_Control_Operator"
): Promise<import("../types").ResponseTask> {
  const res = await fetch(`${API_BASE}/coordination/tasks/${encodeURIComponent(taskId)}/assign`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Operator-Key": operatorKey,
    },
    body: JSON.stringify({ responder_id: responderId, operator_id: operatorId }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(err.detail || `Failed to assign task (${res.status})`);
  }

  return res.json();
}

/**
 * Updates status of a task (e.g. assigned -> in_progress).
 */
export async function updateTaskStatus(
  taskId: string,
  status: import("../types").TaskStatus,
  actorId: string,
  actorRole: string = "responder",
  notes?: string
): Promise<import("../types").ResponseTask> {
  const res = await fetch(`${API_BASE}/coordination/tasks/${encodeURIComponent(taskId)}/status`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      "X-Responder-Id": actorId,
    },
    body: JSON.stringify({ status, actor_id: actorId, actor_role: actorRole, notes }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(err.detail || `Failed to update status (${res.status})`);
  }

  return res.json();
}

/**
 * Resolves a task with completion notes and optional photographic proof.
 */
export async function resolveTaskWithEvidence(
  taskId: string,
  actorId: string,
  notes: string,
  file?: File | null,
  actorRole: string = "responder"
): Promise<import("../types").ResponseTask> {
  const formData = new FormData();
  formData.append("notes", notes);
  formData.append("actor_id", actorId);
  formData.append("actor_role", actorRole);
  if (file) {
    formData.append("file", file);
  }

  const res = await fetch(`${API_BASE}/coordination/tasks/${encodeURIComponent(taskId)}/resolve`, {
    method: "POST",
    headers: {
      "X-Responder-Id": actorId,
    },
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(err.detail || `Failed to resolve task (${res.status})`);
  }

  return res.json();
}

/**
 * Appends a field progress note to a task.
 */
export async function addTaskNote(
  taskId: string,
  note: string,
  authorId: string,
  authorRole: string = "responder"
): Promise<import("../types").TaskNote> {
  const res = await fetch(`${API_BASE}/coordination/tasks/${encodeURIComponent(taskId)}/notes`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Responder-Id": authorId,
    },
    body: JSON.stringify({ note, author_id: authorId, author_role: authorRole }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(err.detail || `Failed to add note (${res.status})`);
  }

  return res.json();
}

/**
 * Queries in-app notifications.
 */
export async function fetchInAppNotifications(
  targetAudience?: string,
  responderId?: string
): Promise<import("../types").InAppNotification[]> {
  const params = new URLSearchParams();
  if (targetAudience && targetAudience !== "all") params.append("target_audience", targetAudience);
  if (responderId) params.append("responder_id", responderId);

  const res = await fetch(`${API_BASE}/coordination/notifications?${params.toString()}`);
  if (!res.ok) {
    throw new Error(`Failed to load notifications (${res.status})`);
  }

  return res.json();
}

/**
 * Human operator approves public/emergency broadcast.
 */
export async function approveInAppNotification(
  notificationId: string,
  operatorKey: string,
  operatorId: string = "BBMP_Chief_Duty_Officer"
): Promise<import("../types").InAppNotification> {
  const res = await fetch(
    `${API_BASE}/coordination/notifications/${encodeURIComponent(notificationId)}/approve`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Operator-Key": operatorKey,
      },
      body: JSON.stringify({ operator_id: operatorId }),
    }
  );

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(err.detail || `Failed to approve broadcast (${res.status})`);
  }

  return res.json();
}


