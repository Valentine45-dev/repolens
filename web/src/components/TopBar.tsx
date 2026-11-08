import { Link, useLocation } from "react-router-dom";

import { LogoMark } from "./LogoMark";
import { ThemeToggle } from "./ThemeToggle";

// Only links to pages that exist: no Recent dropdown (the list lives on Home), no About page. The
// theme toggle sits at the far right.
export function TopBar() {
  const { pathname } = useLocation();
  return (
    <header className="topbar">
      <Link to="/" className="wordmark" aria-label="RepoLens home">
        <LogoMark />
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
      <div className="topbar-end">
        <ThemeToggle />
      </div>
    </header>
  );
}
