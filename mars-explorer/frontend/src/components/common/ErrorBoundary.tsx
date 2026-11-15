import { Component, type ErrorInfo, type ReactNode } from "react";

interface State {
  error: Error | null;
}

/** Keeps a crash in one view (map, globe) from blanking the whole application (bug B9). */
export default class ErrorBoundary extends Component<{ children: ReactNode; label?: string }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("View crashed:", error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="planet-screen" role="alert">
          <div className="map-error" style={{ position: "static" }}>
            <strong>{this.props.label ?? "This view"} failed to render.</strong> {this.state.error.message}
            <div className="layer-card__actions">
              <button className="btn btn--small" onClick={() => this.setState({ error: null })}>
                Retry
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
