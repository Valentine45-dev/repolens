import { Link } from "react-router-dom";

export function NotFound() {
  return (
    <div className="page">
      <h1 className="page-title">This page does not exist.</h1>
      <p className="lede">
        <Link to="/">Start a new analysis</Link>
      </p>
    </div>
  );
}
