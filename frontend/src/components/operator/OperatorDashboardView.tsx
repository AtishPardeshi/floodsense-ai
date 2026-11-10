import React, { useEffect, useState } from "react";
import {
  createResponseTask,
  fetchOperatorQueue,
  fetchTaskPriorityPreview,
  getSavedOperatorKey,
  linkOperatorDuplicate,
  saveOperatorKey,
  submitOperatorDecision,
} from "../../services/reportsApi";
import type { OperatorReportItem, TaskPriorityBreakdown } from "../../types";

interface Props {
  onReportSelect?: (report: OperatorReportItem) => void;
}

export default function OperatorDashboardView({ onReportSelect }: Props) {
  const [operatorKey, setOperatorKey] = useState<string>(getSavedOperatorKey());
  const [isKeySaved, setIsKeySaved] = useState<boolean>(true);
  const [reviewerName, setReviewerName] = useState<string>("BBMP_Zone_Operator");

  const [queue, setQueue] = useState<OperatorReportItem[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("submitted");
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Active decision state per report
  const [activeActionReportId, setActiveActionReportId] = useState<string | null>(null);
  const [actionType, setActionType] = useState<"approve" | "reject" | "needs_info" | "link_duplicate">("approve");
  const [actionReason, setActionReason] = useState<string>("");
  const [targetParentId, setTargetParentId] = useState<string>("");
  const [actionLoading, setActionLoading] = useState<boolean>(false);

  // Modal photo preview
  const [expandedPhoto, setExpandedPhoto] = useState<string | null>(null);

  // Convert report to Response Task modal state
  const [taskModalReport, setTaskModalReport] = useState<OperatorReportItem | null>(null);
  const [taskTitle, setTaskTitle] = useState<string>("");
  const [taskDescription, setTaskDescription] = useState<string>("");
  const [taskResponderId, setTaskResponderId] = useState<string>("BBMP_Rapid_Unit_1");
  const [priorityPreview, setPriorityPreview] = useState<TaskPriorityBreakdown | null>(null);
  const [taskLoading, setTaskLoading] = useState<boolean>(false);
  const [taskSuccessMsg, setTaskSuccessMsg] = useState<string | null>(null);

  const handleOpenTaskModal = async (report: OperatorReportItem) => {
    setTaskModalReport(report);
    setTaskTitle(`Clear waterlogging at ${report.spot_name || report.spot_id}`);
    setTaskDescription(report.notes || `Field response required at (${report.latitude.toFixed(4)}, ${report.longitude.toFixed(4)})`);
    setPriorityPreview(null);
    try {
      const prev = await fetchTaskPriorityPreview(report.spot_id, report.report_id, report.severity || undefined);
      setPriorityPreview(prev);
    } catch {}
  };

  const handleCreateTask = async () => {
    if (!taskModalReport) return;
    setTaskLoading(true);
    setError(null);
    try {
      const created = await createResponseTask(
        {
          spot_id: taskModalReport.spot_id,
          incident_report_id: taskModalReport.report_id,
          title: taskTitle.trim(),
          description: taskDescription.trim(),
          assigned_responder_id: taskResponderId.trim() || undefined,
          latitude: taskModalReport.latitude,
          longitude: taskModalReport.longitude,
        },
        operatorKey
      );
      setTaskSuccessMsg(`Dispatched task ${created.task_id} to ${taskResponderId || "Unassigned"} (${created.priority})`);
      setTaskModalReport(null);
      setTimeout(() => setTaskSuccessMsg(null), 5000);
    } catch (err: any) {
      setError(err?.message || "Failed to create response task.");
    } finally {
      setTaskLoading(false);
    }
  };

  const loadQueue = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchOperatorQueue(operatorKey, statusFilter);
      setQueue(data);
    } catch (err: any) {
      setError(err?.message || "Failed to load operator review queue.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadQueue();
  }, [statusFilter, operatorKey]);

  const handleSaveKey = (e: React.FormEvent) => {
    e.preventDefault();
    saveOperatorKey(operatorKey);
    setIsKeySaved(true);
    loadQueue();
  };

  const handleOpenAction = (reportId: string, type: "approve" | "reject" | "needs_info" | "link_duplicate", defaultParentId?: string | null) => {
    setActiveActionReportId(reportId);
    setActionType(type);
    setActionReason("");
    setTargetParentId(defaultParentId || "");
  };

  const handleExecuteDecision = async (reportId: string) => {
    setActionLoading(true);
    setError(null);
    try {
      if (actionType === "link_duplicate") {
        if (!targetParentId.trim()) {
          setError("Please specify the primary report ID to link to.");
          setActionLoading(false);
          return;
        }
        await linkOperatorDuplicate(reportId, targetParentId.trim(), operatorKey, actionReason.trim());
      } else {
        const decisionMap = {
          approve: "approved" as const,
          reject: "rejected" as const,
          needs_info: "needs_info" as const,
        };
        await submitOperatorDecision(
          reportId,
          {
            decision: decisionMap[actionType],
            reviewer_id: reviewerName.trim() || "BBMP_Control_Operator",
            reason: actionReason.trim() || undefined,
          },
          operatorKey
        );
      }
      setActiveActionReportId(null);
      loadQueue();
    } catch (err: any) {
      setError(err?.message || "Action failed.");
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div className="operator-dashboard">
      <div className="operator-header">
        <div>
          <h2>BBMP Municipal Triage Console</h2>
          <p className="sub">Operational Verification & Evidence Dispatch</p>
        </div>
        <button type="button" className="btn btn-secondary btn-sm" onClick={loadQueue} disabled={loading}>
          {loading ? "Refreshing..." : "🔄 Refresh Queue"}
        </button>
      </div>

      {/* Operator Credentials & Passcode Bar */}
      <div className="operator-auth-bar">
        <span className="auth-status-indicator">🔑 Key: {operatorKey ? "Configured" : "None"}</span>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() => setIsKeySaved(!isKeySaved)}
        >
          {isKeySaved ? "Edit Credentials" : "Hide"}
        </button>
      </div>

      {!isKeySaved && (
        <form className="auth-edit-form" onSubmit={handleSaveKey}>
          <label>
            <span>Operator Access Key:</span>
            <input
              type="password"
              className="form-input"
              value={operatorKey}
              onChange={(e) => setOperatorKey(e.target.value)}
              placeholder="Enter municipal authorization key"
            />
          </label>
          <label>
            <span>Reviewer Alias / ID:</span>
            <input
              type="text"
              className="form-input"
              value={reviewerName}
              onChange={(e) => setReviewerName(e.target.value)}
              placeholder="e.g. BBMP_Control_Desk"
            />
          </label>
          <button type="submit" className="btn btn-primary btn-sm">
            Save Credentials
          </button>
        </form>
      )}

      {error && <div className="error-alert" role="alert">{error}</div>}
      {taskSuccessMsg && <div className="success-alert" role="status">✅ {taskSuccessMsg}</div>}

      {/* Queue Filter Tabs */}
      <div className="queue-filter-tabs" role="tablist">
        {[
          { id: "submitted", label: "Pending Review" },
          { id: "approved", label: "Approved" },
          { id: "rejected", label: "Rejected" },
          { id: "needs_info", label: "Needs Info" },
          { id: "all", label: "All Records" },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={`tab-btn ${statusFilter === tab.id ? "active" : ""}`}
            onClick={() => setStatusFilter(tab.id)}
            role="tab"
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Queue List */}
      <div className="operator-queue-list">
        {queue.length === 0 ? (
          <div className="empty-queue-msg">
            <p>No reports currently matching filter &quot;{statusFilter}&quot;.</p>
          </div>
        ) : (
          queue.map((item) => {
            const isActioning = activeActionReportId === item.report_id;
            return (
              <div
                key={item.report_id}
                className={`operator-report-card ${
                  item.verification_status === "approved"
                    ? "is-card-approved"
                    : item.verification_status === "rejected"
                    ? "is-card-rejected"
                    : "is-card-pending"
                }`}
              >
                {/* Header & Badges */}
                <div className="card-top-row">
                  <div className="card-id-block">
                    <span className="card-report-id font-mono">{item.report_id}</span>
                    <span className="card-time">
                      {new Date(item.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  </div>
                  <div className="card-status-badges">
                    {item.report_type === "control_clear" ? (
                      <span className="badge badge-clear">Clear Corridor</span>
                    ) : (
                      <span className={`badge badge-sev-${item.severity_level || "medium"}`}>
                        {item.severity_level || "Medium"} ({item.water_depth_cm || "?"} cm)
                      </span>
                    )}
                    <span className={`status-pill status-${item.verification_status}`}>
                      {item.verification_status}
                    </span>
                  </div>
                </div>

                {/* Location & Proximity */}
                <div className="card-location-row">
                  <span className="location-name">📍 {item.spot_name || item.spot_id}</span>
                  <span className="coords font-mono">
                    ({item.latitude.toFixed(4)}, {item.longitude.toFixed(4)})
                  </span>
                </div>

                {/* Ground Notes / Description */}
                {item.notes && (
                  <p className="card-desc">
                    <strong>Report:</strong> &quot;{item.notes}&quot;
                  </p>
                )}

                {/* Photo Thumbnail */}
                {item.image_url && (
                  <div className="card-photo-row">
                    <img
                      src={`http://localhost:8000${item.image_url}`}
                      alt="Citizen evidence thumbnail"
                      className="card-photo-thumb"
                      onClick={() => setExpandedPhoto(`http://localhost:8000${item.image_url}`)}
                      title="Click to expand photo"
                    />
                    <span className="photo-hint">📷 Attached Photo (click to expand)</span>
                  </div>
                )}

                {/* Duplicate Alert Banner */}
                {item.duplicate_warning && item.verification_status !== "rejected" && (
                  <div className="duplicate-alert-banner">
                    <span className="dup-icon">⚠️</span>
                    <div className="dup-text">
                      <strong>Duplicate Alert:</strong> {item.duplicate_warning}
                    </div>
                    {item.potential_duplicate_of && (
                      <button
                        type="button"
                        className="btn btn-secondary btn-xs"
                        onClick={() => handleOpenAction(item.report_id, "link_duplicate", item.potential_duplicate_of)}
                      >
                        Link Duplicate
                      </button>
                    )}
                  </div>
                )}

                {/* Duplicate Link Tag */}
                {item.duplicate_of_id && (
                  <div className="linked-duplicate-tag">
                    Linked as duplicate of <code>{item.duplicate_of_id}</code> (excluded from active evidence)
                  </div>
                )}

                {/* Context: Nearby Reports count */}
                <div className="card-meta-row">
                  <span className="reporter-alias">Reported by: {item.reporter_alias || "Anonymous"}</span>
                  <span className="nearby-count">
                    {item.nearby_reports_count > 0
                      ? `📡 ${item.nearby_reports_count} other report${item.nearby_reports_count > 1 ? "s" : ""} nearby`
                      : "📡 Isolated report"}
                  </span>
                </div>

                {/* Operator Audit History if already reviewed */}
                {item.verified_by && (
                  <div className="card-audit-box">
                    <span>
                      Reviewed by <strong>{item.verified_by}</strong> at{" "}
                      {item.verified_at && new Date(item.verified_at).toLocaleTimeString()}:
                    </span>
                    {item.decision_reason && <p className="audit-reason">&quot;{item.decision_reason}&quot;</p>}
                  </div>
                )}

                {/* Operator Action Buttons */}
                {!isActioning ? (
                  <div className="card-action-bar">
                    <button
                      type="button"
                      className="btn btn-primary btn-sm btn-approve"
                      onClick={() => handleOpenAction(item.report_id, "approve")}
                    >
                      ✓ Approve
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm btn-reject"
                      onClick={() => handleOpenAction(item.report_id, "reject")}
                    >
                      ✕ Reject
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => handleOpenAction(item.report_id, "needs_info")}
                    >
                      ? Needs Info
                    </button>
                    {onReportSelect && (
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={() => onReportSelect(item)}
                      >
                        View on Map
                      </button>
                    )}
                    <button
                      type="button"
                      className="btn btn-warning btn-sm btn-dispatch"
                      onClick={() => handleOpenTaskModal(item)}
                    >
                      🚜 Dispatch Task
                    </button>
                  </div>
                ) : (
                  <div className="action-inline-form">
                    <div className="action-form-header">
                      <strong>
                        {actionType === "approve"
                          ? "Approve Report as Verified Evidence"
                          : actionType === "reject"
                          ? "Reject Report"
                          : actionType === "link_duplicate"
                          ? "Link as Duplicate Report"
                          : "Request Additional Information"}
                      </strong>
                      <button
                        type="button"
                        className="btn btn-ghost btn-xs"
                        onClick={() => setActiveActionReportId(null)}
                      >
                        Cancel
                      </button>
                    </div>

                    {actionType === "link_duplicate" && (
                      <label className="action-field">
                        <span>Primary Report ID to link to:</span>
                        <input
                          type="text"
                          className="form-input"
                          value={targetParentId}
                          onChange={(e) => setTargetParentId(e.target.value)}
                          placeholder="e.g. rep_8a3f9e..."
                        />
                      </label>
                    )}

                    <label className="action-field">
                      <span>
                        {actionType === "reject"
                          ? "Rejection Reason (Required):"
                          : actionType === "needs_info"
                          ? "Requested Clarification (Required):"
                          : "Verification Notes / CCTV Corroboration:"}
                      </span>
                      <input
                        type="text"
                        className="form-input"
                        value={actionReason}
                        onChange={(e) => setActionReason(e.target.value)}
                        placeholder={
                          actionType === "approve"
                            ? "e.g. Confirmed on CCTV camera 14, drain overflow active"
                            : actionType === "reject"
                            ? "e.g. False alarm / road clear on inspection"
                            : "e.g. Please provide photo of underpass gauge"
                        }
                      />
                    </label>

                    <div className="action-submit-row">
                      <button
                        type="button"
                        className={`btn btn-sm ${
                          actionType === "approve" ? "btn-primary" : "btn-secondary"
                        }`}
                        onClick={() => handleExecuteDecision(item.report_id)}
                        disabled={
                          actionLoading ||
                          ((actionType === "reject" || actionType === "needs_info") && !actionReason.trim())
                        }
                      >
                        {actionLoading ? "Recording..." : `Confirm ${actionType}`}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Fullscreen Photo Modal */}
      {expandedPhoto && (
        <div className="modal-backdrop" onClick={() => setExpandedPhoto(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <img src={expandedPhoto} alt="Full evidence preview" className="modal-img" />
            <button
              type="button"
              className="btn btn-secondary btn-sm modal-close"
              onClick={() => setExpandedPhoto(null)}
            >
              ✕ Close
            </button>
          </div>
        </div>
      )}

      {/* Response Task Dispatch Modal */}
      {taskModalReport && (
        <div className="modal-backdrop" onClick={() => setTaskModalReport(null)}>
          <div className="modal-content task-dispatch-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>🚜 Convert Report to Civic Response Task</h3>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setTaskModalReport(null)}
              >
                ✕
              </button>
            </div>

            <div className="modal-body">
              <div className="task-preview-banner">
                <strong>Source:</strong> {taskModalReport.report_id} • {taskModalReport.spot_name || taskModalReport.spot_id}
              </div>

              {priorityPreview && (
                <div className="priority-preview-card">
                  <div className="preview-top">
                    <span>Deterministic Priority:</span>
                    <strong className="priority-pill">{priorityPreview.calculated_priority}</strong>
                    <span>(Score: {priorityPreview.total_score}/100)</span>
                  </div>
                  <p className="preview-exp">{priorityPreview.explanation}</p>
                </div>
              )}

              <label className="action-field">
                <span>Task Title:</span>
                <input
                  type="text"
                  className="form-input"
                  value={taskTitle}
                  onChange={(e) => setTaskTitle(e.target.value)}
                />
              </label>

              <label className="action-field">
                <span>Description / Field Directive:</span>
                <textarea
                  className="form-input"
                  rows={3}
                  value={taskDescription}
                  onChange={(e) => setTaskDescription(e.target.value)}
                />
              </label>

              <label className="action-field">
                <span>Assign Field Unit:</span>
                <select
                  className="form-select"
                  value={taskResponderId}
                  onChange={(e) => setTaskResponderId(e.target.value)}
                >
                  <option value="BBMP_Rapid_Unit_1">BBMP Rapid Unit 1 (Central)</option>
                  <option value="BBMP_Unit_7">BBMP Stormwater Unit 7 (South)</option>
                  <option value="BBMP_East_Rescue_2">BBMP Rescue Unit 2 (East / ORR)</option>
                  <option value="Traffic_Warden_South">Bengaluru Traffic Police (Ward 10)</option>
                </select>
              </label>
            </div>

            <div className="modal-footer">
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => setTaskModalReport(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={handleCreateTask}
                disabled={taskLoading || !taskTitle.trim()}
              >
                {taskLoading ? "Dispatching..." : "🚀 Dispatch Task to Field Unit"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

