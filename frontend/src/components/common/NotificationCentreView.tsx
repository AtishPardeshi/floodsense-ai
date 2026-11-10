import React, { useEffect, useState } from "react";
import {
  approveInAppNotification,
  fetchInAppNotifications,
  getSavedOperatorKey,
} from "../../services/reportsApi";
import type { InAppNotification } from "../../types";

export default function NotificationCentreView() {
  const [notifications, setNotifications] = useState<InAppNotification[]>([]);
  const [filterAudience, setFilterAudience] = useState<string>("all");
  const [operatorKey, setOperatorKey] = useState<string>(getSavedOperatorKey());
  const [loading, setLoading] = useState<boolean>(false);
  const [approvingId, setApprovingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const loadNotifications = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchInAppNotifications(filterAudience);
      setNotifications(data);
    } catch (err: any) {
      setError(err?.message || "Failed to load in-app notifications.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadNotifications();
    const interval = setInterval(loadNotifications, 6000);
    return () => clearInterval(interval);
  }, [filterAudience]);

  const handleApproveAlert = async (notifId: string) => {
    setApprovingId(notifId);
    setError(null);
    try {
      await approveInAppNotification(notifId, operatorKey, "BBMP_Chief_Duty_Officer");
      setSuccessMsg(`Public emergency broadcast ${notifId} approved and delivered.`);
      setTimeout(() => setSuccessMsg(null), 4000);
      loadNotifications();
    } catch (err: any) {
      setError(err?.message || "Failed to authorize broadcast.");
    } finally {
      setApprovingId(null);
    }
  };

  const getSeverityBadge = (sev: string) => {
    switch (sev) {
      case "critical":
        return "badge-critical";
      case "warning":
        return "badge-warning";
      default:
        return "badge-info";
    }
  };

  const getDeliveryStatusBadge = (status: string) => {
    switch (status) {
      case "delivered_in_app":
        return { text: "Delivered In-App", className: "badge-success" };
      case "pending_approval":
        return { text: "Pending Operator Approval", className: "badge-danger" };
      case "logged_locally":
      default:
        return { text: "Logged Locally (No Spam)", className: "badge-secondary" };
    }
  };

  const pendingCount = notifications.filter(
    (n) => n.requires_human_approval && n.delivery_status === "pending_approval"
  ).length;

  return (
    <div className="notification-centre-view">
      <div className="notif-header">
        <div className="notif-title-row">
          <h2>🔔 Local In-App Notification Centre</h2>
          <span className="notif-disclaimer">
            Local-first event feed • No external SMS or spam gateways
          </span>
        </div>

        {pendingCount > 0 && (
          <div className="pending-alert-banner">
            <span>⚠️ {pendingCount} emergency alert(s) awaiting operator broadcast authorization</span>
          </div>
        )}

        {/* Filter Tabs */}
        <div className="notif-filter-tabs">
          {[
            { id: "all", label: "All Feeds" },
            { id: "operator", label: "🛡️ Operator Logs" },
            { id: "responder", label: "🚜 Field Units" },
            { id: "public_advisory", label: "📢 Public Advisories" },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`tab-btn ${filterAudience === tab.id ? "active" : ""}`}
              onClick={() => setFilterAudience(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

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

      <div className="notif-list-container">
        {loading && notifications.length === 0 ? (
          <div className="loading-state">Loading notification stream...</div>
        ) : notifications.length === 0 ? (
          <div className="empty-state">
            <p>No notifications for selected audience.</p>
            <small>State transitions and dispatches will log here automatically.</small>
          </div>
        ) : (
          notifications.map((n) => {
            const delivery = getDeliveryStatusBadge(n.delivery_status);
            const isPendingGate =
              n.requires_human_approval && n.delivery_status === "pending_approval";

            return (
              <div key={n.notification_id} className={`notif-card notif-${n.severity}`}>
                <div className="notif-top-row">
                  <div className="badge-row">
                    <span className={`badge ${getSeverityBadge(n.severity)}`}>
                      {n.severity.toUpperCase()}
                    </span>
                    <span className={`badge ${delivery.className}`}>{delivery.text}</span>
                    <span className="badge badge-outline">
                      Audience: {n.target_audience.replace("_", " ")}
                    </span>
                  </div>

                  <span className="notif-time">
                    {new Date(n.created_at).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                      second: "2-digit",
                    })}
                  </span>
                </div>

                <h3 className="notif-title">{n.title}</h3>
                <p className="notif-message">{n.message}</p>

                <div className="notif-footer-meta">
                  {n.task_id && <span className="meta-pill">Task: {n.task_id}</span>}
                  {n.target_responder_id && (
                    <span className="meta-pill">Target: {n.target_responder_id}</span>
                  )}
                  {n.approved_by && (
                    <span className="meta-pill">
                      Approved by {n.approved_by} at {n.approved_at}
                    </span>
                  )}
                </div>

                {/* Operator Approval Gate for Public Emergency Alerts */}
                {isPendingGate && (
                  <div className="operator-gate-box">
                    <div className="gate-instructions">
                      <strong>Human Operator Approval Required:</strong>
                      <p>
                        Strict safety rule: Public emergency advisories cannot be delivered until
                        explicitly verified and authorized by BBMP command.
                      </p>
                    </div>

                    <div className="gate-actions-row">
                      <input
                        type="password"
                        className="form-input form-input-sm"
                        placeholder="Operator Secret Key"
                        value={operatorKey}
                        onChange={(e) => setOperatorKey(e.target.value)}
                        style={{ maxWidth: "220px" }}
                      />
                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
                        disabled={approvingId === n.notification_id || !operatorKey.trim()}
                        onClick={() => handleApproveAlert(n.notification_id)}
                      >
                        {approvingId === n.notification_id
                          ? "Authorizing..."
                          : "📢 Authorize & Broadcast Public Alert"}
                      </button>
                    </div>
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

