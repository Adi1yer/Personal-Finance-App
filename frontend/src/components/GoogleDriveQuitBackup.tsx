import { useEffect } from "react";
import { api } from "../api/client";

/**
 * On Electron quit, upload a Drive backup when connected.
 * Always resolves so the main process is never stuck waiting.
 */
export default function GoogleDriveQuitBackup() {
  useEffect(() => {
    const unsub = window.personalFinance?.onBackupBeforeQuit?.(async () => {
      try {
        const status = await api.googleDriveStatus();
        if (status.connected) {
          await api.googleDriveBackupNow();
        }
      } catch {
        // Quit must proceed even if backup fails.
      }
    });
    return () => unsub?.();
  }, []);

  return null;
}
