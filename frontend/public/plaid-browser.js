/* Shared Plaid Link helpers for system-browser bank connection. */
window.plaidBrowser = {
  async fetchSession() {
    const res = await fetch("/api/v1/plaid/browser-session");
    if (!res.ok) {
      const text = await res.text();
      if (text.includes("Not signed in")) {
        throw new Error(
          "Session expired. In the Personal Finance app, click Connect bank again, then use the Safari tab that opens."
        );
      }
      throw new Error(text || "No pending bank connection. Click Connect bank in the app again.");
    }
    return res.json();
  },

  async exchange(publicToken) {
    const res = await fetch("/api/v1/plaid/browser-exchange", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ public_token: publicToken }),
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || "Could not save bank connection");
    }
    return res.json();
  },

  formatError(err) {
    if (!err) return "";
    if (typeof err === "string") return err;
    if (err.display_message) return err.display_message;
    if (err.error_message) return err.error_message;
    try {
      return JSON.stringify(err);
    } catch {
      return "Plaid Link failed";
    }
  },

  async startLinkFlow({ statusEl, errorEl, hintEl, successMessage, receivedRedirectUri }) {
    function showError(msg) {
      statusEl.textContent = "Connection failed";
      errorEl.hidden = false;
      errorEl.textContent = msg;
    }

    try {
      const { link_token } = await this.fetchSession();
      if (!window.Plaid) throw new Error("Plaid Link failed to load.");

      const handler = window.Plaid.create({
        token: link_token,
        receivedRedirectUri,
        onSuccess: async (public_token) => {
          try {
            statusEl.textContent = "Saving connection…";
            await this.exchange(public_token);
            statusEl.textContent = successMessage || "Connected!";
            statusEl.className = "ok";
            if (hintEl) hintEl.hidden = false;
          } catch (e) {
            showError(e.message || String(e));
          }
        },
        onExit: (err) => {
          if (err) showError(this.formatError(err));
        },
      });
      statusEl.textContent = receivedRedirectUri
        ? "Finishing sign-in…"
        : "Choose your bank in the window below…";
      handler.open();
    } catch (e) {
      showError(e.message || String(e));
    }
  },
};
