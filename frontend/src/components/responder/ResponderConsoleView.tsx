import React, { useEffect, useState } from "react";
import {
  addTaskNote,
  fetchResponseTasks,
  getSavedResponderId,
  resolveTaskWithEvidence,
  saveResponderId,
  updateTaskStatus,
} from "../../services/reportsApi";
import type { ResponseTask, TaskPriority, TaskStatus } from "../../types";

const RESPONDER_PRESETS = [
  { id: "BBMP_Rapid_Unit_1", label: "BBMP Rapid Response 1 (Central)" },
  { id: "BBMP_Unit_7", label: "BBMP Stormwater Unit 7 (South)" },
  { id: "BBMP_East_Rescue_2", label: "BBMP Rescue Unit 2 (East / ORR)" },
  { id: "Traffic_Warden_South", label: "Bengaluru Traffic Police (Ward 10)" },
];

export default function ResponderConsoleView() {
  const [responderId, setResponderId] = useState<string>(getSavedResponderId());
  const [tasks, setTasks] = useState<ResponseTask[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [onlyMine, setOnlyMine] = useState<boolean>(true);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Expanded priority breakdown per task
  const [expandedBreakdown, setExpandedBreakdown] = useState<Record<string, boolean>>({});

  // Note addition state
  const [noteInputs, setNoteInputs] = useState<Record<string, string>>({});
  const [submittingNote, setSubmittingNote] = useState<Record<string, boolean>>({});

  // Resolution state
  const [resolvingTaskId, setResolvingTaskId] = useState<string | null>(null);
  const [resolutionNotes, setResolutionNotes] = useState<string>("");
  const [resolutionPhoto, setResolutionPhoto] = useState<File | null>(null);
  const [resolutionPreview, setResolutionPreview] = useState<string | null>(null);
  const [submittingResolution, setSubmittingResolution] = useState<boolean>(false);

  const loadTasks = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchResponseTasks({
        status: statusFilter,
        responder_id: onlyMine ? responderId : undefined,
      });
      setTasks(data);
    } catch (err: any) {
      setError(err?.message || "Failed to load response tasks.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTasks();
  }, [responderId, statusFilter, onlyMine]);

  const handleSelectResponder = (newId: string) => {
    setResponderId(newId);
    saveResponderId(newId);
  };

  const toggleBreakdown = (taskId: string) => {
    setExpandedBreakdown((prev) => ({ ...prev, [taskId]: !prev[taskId] }));
  };

  const handleStartTask = async (task: ResponseTask) => {
    setError(null);
    try {
      await updateTaskStatus(task.task_id, "in_progress", responderId, "responder", "Field unit en route / work begun.");
      setSuccessMsg(`Task ${task.task_id} transitioned to In-Progress.`);
      setTimeout(() => setSuccessMsg(null), 4000);
      loadTasks();
    } catch (err: any) {
      setError(err?.message || "Failed to start task.");
    }
  };

  const handleAddNote = async (taskId: string) => {
    const text = noteInputs[taskId]?.trim();
    if (!text) return;

    setSubmittingNote((prev) => ({ ...prev, [taskId]: true }));
    setError(null);
    try {
      await addTaskNote(taskId, text, responderId, "responder");
      setNoteInputs((prev) => ({ ...prev, [taskId]: "" }));
      setSuccessMsg("Field progress note added.");
      setTimeout(() => setSuccessMsg(null), 3000);
      loadTasks();
    } catch (err: any) {
      setError(err?.message || "Failed to add progress note.");
    } finally {
      setSubmittingNote((prev) => ({ ...prev, [taskId]: false }));
    }
  };

  const handlePhotoSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const f = e.target.files[0];
      setResolutionPhoto(f);
      setResolutionPreview(URL.createObjectURL(f));
    }
  };

  const handleConfirmResolution = async (taskId: string) => {
    if (!resolutionNotes.trim()) {
      setError("Please describe the actions taken and clearance status before resolving.");
      return;
    }

    setSubmittingResolution(true);
    setError(null);
    try {
      await resolveTaskWithEvidence(taskId, responderId, resolutionNotes.trim(), resolutionPhoto, "responder");
      setSuccessMsg(`Task ${taskId} successfully resolved with completion notes!`);
      setResolvingTaskId(null);
      setResolutionNotes("");
      setResolutionPhoto(null);
      setResolutionPreview(null);
      setTimeout(() => setSuccessMsg(null), 5000);
      loadTasks();
    } catch (err: any) {
      setError(err?.message || "Failed to resolve task.");
    } finally {
      setSubmittingResolution(false);
    }
  };

  const getPriorityBadgeClass = (priority: TaskPriority) => {
    switch (priority) {
      case "P1_CRITICAL":
        return "priority-p1";
      case "P2_HIGH":
        return "priority-p2";
      case "P3_MEDIUM":
        return "priority-p3";
      case "P4_LOW":
        return "priority-p4";
    }
  };

  const getStatusBadgeClass = (status: TaskStatus) => {
    switch (status) {
      case "open":
        return "badge-open";
      case "assigned":
        return "badge-assigned";
      case "in_progress":
        return "badge-inprogress";
      case "resolved":
        return "badge-resolved";
      case "cancelled":
        return "badge-cancelled";
    }
  };

  return (
    <div className="responder-console">
      <div className="console-header">
        <div className="unit-selector-card">
          <label className="unit-label">
            <span>🚜 Active Responder Unit:</span>
            <select
              className="form-select"
              value={responderId}
              onChange={(e) => handleSelectResponder(e.target.value)}
            >
              {RESPONDER_PRESETS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label} ({p.id})
                </option>
              ))}
              {!RESPONDER_PRESETS.some((p) => p.id === responderId) && (
                <option value={responderId}>{responderId} (Custom)</option>
              )}
            </select>
          </label>
        </div>

        {/* Filter Toolbar */}
        <div className="filter-toolbar">
          <div className="mine-toggle">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={onlyMine}
                onChange={(e) => setOnlyMine(e.target.checked)}
              />
              <span>Assigned to My Unit Only</span>
            </label>
          </div>

          <div className="status-chips">
            {["all", "assigned", "in_progress", "resolved"].map((s) => (
              <button
                key={s}
                type="button"
                className={`chip-btn ${statusFilter === s ? "active" : ""}`}
                onClick={() => setStatusFilter(s)}
              >
                {s === "all" ? "All" : s.replace("_", " ").toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Messages */}
      {error && (
        <div className="alert-banner alert-error" role="alert">
          <span>⚠️ {error}</span>
          <button type="button" className="close-btn" onClick={() => setError(null)}>
            ✕
          </button>
        </div>
      )}

      {successMsg && (
        <div className="alert-banner alert-success" role="status">
          <span>✅ {successMsg}</span>
        </div>
      )}

      {/* Task List */}
      <div className="tasks-container">
        {loading ? (
          <div className="loading-state">Loading assigned tasks...</div>
        ) : tasks.length === 0 ? (
          <div className="empty-state">
            <p>No response tasks found for filter.</p>
            <small>New flood dispatches will appear here in real-time.</small>
          </div>
        ) : (
          tasks.map((task) => {
            const isAssignedToMe = task.assigned_responder_id === responderId;
            const isResolving = resolvingTaskId === task.task_id;
            const isBreakdownOpen = expandedBreakdown[task.task_id];

            return (
              <div key={task.task_id} className={`task-card ${getPriorityBadgeClass(task.priority)}`}>
                <div className="task-card-header">
                  <div className="task-title-group">
                    <span className={`priority-tag ${getPriorityBadgeClass(task.priority)}`}>
                      {task.priority.replace("_", " ")}
                    </span>
                    <span className={`status-tag ${getStatusBadgeClass(task.status)}`}>
                      {task.status.replace("_", " ")}
                    </span>
                    <h3 className="task-title">{task.title}</h3>
                  </div>

                  <span className="task-id-pill">{task.task_id}</span>
                </div>

                <div className="task-meta-grid">
                  <div>
                    <strong>Location:</strong> {task.location_name}
                  </div>
                  <div>
                    <strong>GPS:</strong> {task.latitude.toFixed(4)}, {task.longitude.toFixed(4)}
                  </div>
                  <div>
                    <strong>Assigned Unit:</strong> {task.assigned_responder_id || "Unassigned"}
                  </div>
                  {task.due_at && (
                    <div>
                      <strong>Target Due:</strong> {new Date(task.due_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </div>
                  )}
                </div>

                <p className="task-desc">{task.description}</p>

                {/* Deterministic Prioritisation Explainability */}
                {task.priority_reasons && (
                  <div className="priority-breakdown-box">
                    <button
                      type="button"
                      className="breakdown-toggle-btn"
                      onClick={() => toggleBreakdown(task.task_id)}
                    >
                      <span>Prioritisation Score: {task.priority_reasons.total_score}/100</span>
                      <span>{isBreakdownOpen ? "▲ Hide Factors" : "▼ Explain Reason"}</span>
                    </button>

                    {isBreakdownOpen && (
                      <div className="breakdown-factors-list">
                        <p className="breakdown-summary">{task.priority_reasons.explanation}</p>
                        <ul>
                          {task.priority_reasons.factors.map((f, i) => (
                            <li key={i}>
                              <strong>+{f.points} pts:</strong> {f.reason}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}

                {/* Progress Notes History */}
                {task.notes && task.notes.length > 0 && (
                  <div className="task-notes-history">
                    <h4>Field Log & Timeline:</h4>
                    <ul>
                      {task.notes.map((n) => (
                        <li key={n.note_id} className="note-entry">
                          <span className="note-time">
                            {new Date(n.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                          </span>
                          <span className="note-author">[{n.author_id}]:</span>
                          <span className="note-body">{n.note}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Resolution proof display if already resolved */}
                {task.status === "resolved" && (
                  <div className="resolved-summary-box">
                    <h4>Resolution Summary</h4>
                    <p>{task.resolution_notes}</p>
                    {task.resolution_image_url && (
                      <div className="resolved-photo">
                        <img
                          src={task.resolution_image_url}
                          alt="Resolution proof"
                          className="resolution-thumb"
                        />
                      </div>
                    )}
                    <small>Resolved at {task.resolved_at}</small>
                  </div>
                )}

                {/* Responder Actions (if assigned to current responder) */}
                {isAssignedToMe && task.status !== "resolved" && task.status !== "cancelled" && (
                  <div className="task-actions-pane">
                    {task.status === "assigned" && (
                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
                        onClick={() => handleStartTask(task)}
                      >
                        🚀 Begin Response Work (Set In-Progress)
                      </button>
                    )}

                    {task.status === "in_progress" && !isResolving && (
                      <button
                        type="button"
                        className="btn btn-success btn-sm"
                        onClick={() => setResolvingTaskId(task.task_id)}
                      >
                        ✅ Complete & Resolve Task
                      </button>
                    )}

                    {/* Quick Progress Note Input */}
                    <div className="quick-note-row">
                      <input
                        type="text"
                        className="form-input form-input-sm"
                        placeholder="Add quick progress note (e.g. Pump active, level -10cm)..."
                        value={noteInputs[task.task_id] || ""}
                        onChange={(e) =>
                          setNoteInputs({ ...noteInputs, [task.task_id]: e.target.value })
                        }
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleAddNote(task.task_id);
                        }}
                      />
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => handleAddNote(task.task_id)}
                        disabled={submittingNote[task.task_id] || !noteInputs[task.task_id]?.trim()}
                      >
                        {submittingNote[task.task_id] ? "Saving..." : "Add Note"}
                      </button>
                    </div>

                    {/* Expandable Resolution Drawer */}
                    {isResolving && (
                      <div className="resolution-drawer">
                        <h4>Task Resolution Proof & Clearance</h4>
                        <label className="action-field">
                          <span>Action Taken & Roadway Clearance Notes (Required):</span>
                          <textarea
                            className="form-input"
                            rows={3}
                            value={resolutionNotes}
                            onChange={(e) => setResolutionNotes(e.target.value)}
                            placeholder="e.g. Cleared 2 culvert drains, pump drained 1.2m water, traffic flow restored."
                          />
                        </label>

                        <label className="action-field">
                          <span>Verification Photo (Camera / Gallery):</span>
                          <input
                            type="file"
                            accept="image/*"
                            capture="environment"
                            onChange={handlePhotoSelect}
                          />
                        </label>

                        {resolutionPreview && (
                          <div className="photo-preview-wrap">
                            <img src={resolutionPreview} alt="Preview" className="preview-thumb" />
                            <button
                              type="button"
                              className="btn btn-text btn-sm"
                              onClick={() => {
                                setResolutionPhoto(null);
                                setResolutionPreview(null);
                              }}
                            >
                              Remove Photo
                            </button>
                          </div>
                        )}

                        <div className="action-submit-row">
                          <button
                            type="button"
                            className="btn btn-success btn-sm"
                            onClick={() => handleConfirmResolution(task.task_id)}
                            disabled={submittingResolution || !resolutionNotes.trim()}
                          >
                            {submittingResolution ? "Submitting..." : "Submit Task Resolution"}
                          </button>
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() => {
                              setResolvingTaskId(null);
                              setResolutionNotes("");
                              setResolutionPhoto(null);
                              setResolutionPreview(null);
                            }}
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

