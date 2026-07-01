import React from "react";

/**
 * Global runtime crash guard. Historically a single misbehaving
 * component (e.g. a Radix `<SelectItem value="">` when the backend
 * returned an empty `path` for a not-yet-uploaded host image) took
 * the whole standalone app to a blank navy screen with no recovery.
 *
 * ErrorBoundary keeps the shell alive: it shows a card with the
 * error text, a "reload window" button, and (in dev) a stack trace.
 * The user can dismiss the modal and keep working in other tools.
 */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null, info: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("[ErrorBoundary]", error, info);
    this.setState({ info });
    // Best-effort telemetry to the local backend so we can grep logs
    // for repeat offenders across the merchant's install.
    try {
      const url = `${process.env.REACT_APP_BACKEND_URL}/api/native/errors/report`;
      fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: String(error && error.message),
          stack: String(error && error.stack),
          componentStack: String(info && info.componentStack),
          location: window.location.href,
          ts: new Date().toISOString(),
        }),
        keepalive: true,
      }).catch(() => {});
    } catch (_) { /* noop */ }
  }

  handleReset = () => {
    this.setState({ error: null, info: null });
  };

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (!this.state.error) return this.props.children;
    const isDev = process.env.NODE_ENV !== "production";
    return (
      <div
        data-testid="app-error-boundary"
        style={{
          minHeight: "100vh",
          background: "#0b1220",
          color: "#e5e7eb",
          padding: "48px 24px",
          fontFamily: "system-ui, -apple-system, sans-serif",
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "center",
        }}
      >
        <div style={{
          maxWidth: 720,
          width: "100%",
          background: "#111827",
          border: "1px solid #374151",
          borderRadius: 12,
          padding: 32,
          boxShadow: "0 20px 40px rgba(0,0,0,0.4)",
        }}>
          <div style={{ fontSize: 22, fontWeight: 600, marginBottom: 12, color: "#fbbf24" }}>
            Something went sideways
          </div>
          <div style={{ color: "#9ca3af", marginBottom: 20, lineHeight: 1.55 }}>
            A tool inside BIG Hat Entertainment threw an error. Nothing on disk was lost — you can either try again or reload the window.
          </div>
          <div style={{
            background: "#0b1220",
            border: "1px solid #1f2937",
            borderRadius: 8,
            padding: 12,
            fontFamily: "ui-monospace, monospace",
            fontSize: 12,
            color: "#f87171",
            marginBottom: 20,
            wordBreak: "break-word",
            whiteSpace: "pre-wrap",
          }}>
            {String(this.state.error && this.state.error.message) || "Unknown error"}
          </div>
          {isDev && this.state.info && this.state.info.componentStack && (
            <details style={{ marginBottom: 20 }}>
              <summary style={{ cursor: "pointer", color: "#9ca3af", fontSize: 12 }}>
                Component stack
              </summary>
              <pre style={{
                marginTop: 8, fontSize: 11, color: "#6b7280",
                whiteSpace: "pre-wrap", wordBreak: "break-word",
              }}>{this.state.info.componentStack}</pre>
            </details>
          )}
          <div style={{ display: "flex", gap: 12 }}>
            <button
              data-testid="error-boundary-try-again"
              onClick={this.handleReset}
              style={{
                background: "transparent",
                border: "1px solid #374151",
                color: "#e5e7eb",
                padding: "10px 18px",
                borderRadius: 8,
                cursor: "pointer",
                fontSize: 14,
              }}
            >
              Try again
            </button>
            <button
              data-testid="error-boundary-reload"
              onClick={this.handleReload}
              style={{
                background: "#fbbf24",
                border: "none",
                color: "#0b1220",
                padding: "10px 18px",
                borderRadius: 8,
                cursor: "pointer",
                fontWeight: 600,
                fontSize: 14,
              }}
            >
              Reload window
            </button>
          </div>
        </div>
      </div>
    );
  }
}
