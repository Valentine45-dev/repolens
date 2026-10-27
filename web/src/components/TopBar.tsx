import { Link, useLocation } from "react-router-dom";

// Only links to pages that exist: no Recent dropdown (the list lives on Home), no About page and
// no theme toggle in this build.
export function TopBar() {
  const { pathname } = useLocation();
  return (
    <header className="topbar">
      <Link to="/" className="wordmark" aria-label="RepoLens home">
        <span className="wordmark-mark" aria-hidden="true" />
        RepoLens
      </Link>
      <nav aria-label="Main">
        <Link
          to="/"
          state={{ focusUrl: true }}
          className="topbar-link"
          aria-current={pathname === "/" ? "page" : undefined}
        >
          New analysis
        </Link>
      </nav>
    </header>
  );
}
