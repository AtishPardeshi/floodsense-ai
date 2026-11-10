import { useEffect, useState } from "react";
import { flushOfflineQueue, getOfflineQueue } from "../../services/reportsApi";
import type { OfflineQueuedReport } from "../../types";

interface Props {
  onQueueUpdated?: () => void;
}

export default function ConnectionStatusBanner({ onQueueUpdated }: Props) {
  const [isOnline, setIsOnline] = useState<boolean>(navigator.onLine);
  const [queue, setQueue] = useState<OfflineQueuedReport[]>([]);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);

  const refreshQueue = () => {
    const q = getOfflineQueue();
    setQueue(q);
    if (onQueueUpdated) onQueueUpdated();
  };

  useEffect(() => {
    refreshQueue();

    const handleOnline = async () => {
      setIsOnline(true);
      setSyncMsg("Back online. Syncing pending reports...");
      try {
        const { synced, failed } = await flushOfflineQueue();
        refreshQueue();
        if (synced > 0) {
          setSyncMsg(`Successfully synchronized ${synced} queued report${synced > 1 ? "s" : ""} to BBMP!`);
        } else if (failed > 0) {
          setSyncMsg(`Some offline reports could not be synced. Will retry.`);
        } else {
          setSyncMsg(null);
        }
      } catch {
        setSyncMsg("Error syncing offline reports. Will retry.");
      }
      setTimeout(() => setSyncMsg(null), 6000);
    };

    const handleOffline = () => {
      setIsOnline(false);
      refreshQueue();
    };

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    // Periodic check for local queue changes
    const interval = setInterval(refreshQueue, 3000);

    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
      clearInterval(interval);
    };
  }, []);

  if (isOnline && queue.length === 0 && !syncMsg) {
    return null;
  }

  return (
    <div className={`connection-banner ${!isOnline ? "is-offline" : "is-syncing"}`} role="status">
      <div className="banner-content">
        {!isOnline ? (
          <>
            <span className="banner-icon">📡</span>
            <div className="banner-text">
              <strong>Offline Mode</strong> — Reports will be saved locally in draft queue.
              {queue.length > 0 && (
                <span className="queue-badge"> {queue.length} pending sync</span>
              )}
            </div>
          </>
        ) : (
          <>
            <span className="banner-icon">🔄</span>
            <div className="banner-text">
              {syncMsg || `Online — ${queue.length} pending reports syncing...`}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

