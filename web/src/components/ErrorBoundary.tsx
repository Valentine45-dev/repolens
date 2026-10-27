import { Component, type ErrorInfo, type ReactNode } from "react";

// A render crash shows a message instead of a blank page. Navigating elsewhere (resetKey is the
// location) clears it.
export class ErrorBoundary extends Component<
  { resetKey: string; children: ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("RepoLens UI crashed", error, info.componentStack);
  }

  componentDidUpdate(prev: { resetKey: string }) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="page">
        <div className="callout" data-tone="error" role="alert">
          <p className="callout-title">Something went wrong on this page.</p>
          <p>The page hit an unexpected error. Your analysis is not affected.</p>
          <div className="callout-actions">
            <button className="button button-secondary" onClick={() => window.location.reload()}>
              Reload page
            </button>
            <a className="text-link" href="/">
              Start a new analysis
            </a>
          </div>
        </div>
      </div>
    );
  }
}
