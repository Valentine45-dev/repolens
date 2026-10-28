import { keepPreviousData, useQuery, type UseQueryResult } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";

import {
  getFindings,
  getRules,
  type Finding,
  type FindingsPage,
  type Rule,
  type Severity,
} from "../api";
import type { AnalysisContext } from "../components/AnalysisShell";
import { Icon } from "../components/Icon";
import { SeverityBadge } from "../components/Severity";
import { languageLabel } from "../graphModel";
import { exploreHref, useSetParams } from "../links";

const PAGE = 50;
const SECRET_RULE = "hardcoded-secret";

// Spec §5.6. Filters live in the URL: ?severity=&rule=&language=&path=&tests=hide&page=&finding=
export function Findings() {
  const { snapshotId } = useOutletContext<AnalysisContext>();
  const [params] = useSearchParams();
  const setParams = useSetParams();
  const severity = (params.get("severity") as Severity | null) ?? undefined;
  const rule = params.get("rule") ?? undefined;
  const language = params.get("language") ?? undefined;
  const path = params.get("path") ?? "";
  const hideTests = params.get("tests") === "hide";
  const page = Math.max(Number(params.get("page") ?? 0) || 0, 0);
  const selectedId = params.get("finding") ? Number(params.get("finding")) : null;

  const filter = {
    severity,
    rule,
    language,
    path_prefix: path || undefined,
    in_test: hideTests ? false : undefined,
    limit: PAGE,
    offset: page * PAGE,
  };
  const findings = useQuery({
    queryKey: ["findings", snapshotId, filter],
    queryFn: ({ signal }) => getFindings(snapshotId, filter, signal),
    placeholderData: keepPreviousData,
    staleTime: Infinity,
  });
  const rules = useQuery({ queryKey: ["rules"], queryFn: ({ signal }) => getRules(signal), staleTime: Infinity });
  const ruleById = new Map((rules.data ?? []).map((r) => [r.id, r]));

  // A filter change starts again at the first page and closes the detail panel.
  const setFilter = (key: string, value: string | null) =>
    setParams({ [key]: value, page: null, finding: null });
  const selected = findings.data?.items.find((f) => f.id === selectedId) ?? null;
  const counts = findings.data?.counts;
  const filtered = Boolean(severity || rule || language || path || hideTests);

  return (
    <div className="findings">
      <div className="findings-main">
        <div className="findings-head">
          <h2 className="section-title">
            Findings{counts ? <span className="mono num"> ({counts.total})</span> : null}
          </h2>
          <p className="caption">
            These are rule-based checks. They can miss issues and can flag safe code. Review each
            one.
          </p>
        </div>

        <div className="toolbar findings-filters" role="toolbar" aria-label="Filter findings">
          <FilterSelect
            label="Severity"
            value={severity ?? ""}
            onChange={(v) => setFilter("severity", v || null)}
            options={(["high", "medium", "low"] as const).map((s) => ({
              value: s,
              label: `${s[0].toUpperCase()}${s.slice(1)} (${counts?.by_severity[s] ?? 0})`,
            }))}
          />
          <FilterSelect
            label="Rule"
            value={rule ?? ""}
            onChange={(v) => setFilter("rule", v || null)}
            options={Object.entries(counts?.by_rule ?? {}).map(([id, n]) => ({
              value: id,
              label: `${ruleById.get(id)?.title ?? id} (${n})`,
            }))}
          />
          <FilterSelect
            label="Language"
            value={language ?? ""}
            onChange={(v) => setFilter("language", v || null)}
            options={["python", "javascript", "typescript"].map((l) => ({
              value: l,
              label: languageLabel(l),
            }))}
          />
          <PathFilter value={path} onChange={(v) => setFilter("path", v || null)} />
          <label className="check">
            <input
              type="checkbox"
              checked={hideTests}
              onChange={(e) => setFilter("tests", e.target.checked ? "hide" : null)}
            />
            Hide test and example code
          </label>
        </div>

        <FindingsList
          query={findings}
          filtered={filtered}
          selectedId={selectedId}
          onSelect={(id) => setParams({ finding: String(id) }, false)}
        />

        {findings.data && findings.data.total > PAGE ? (
          <div className="pager">
            <button
              type="button"
              className="button button-secondary button-small"
              disabled={page === 0}
              onClick={() => setParams({ page: page > 1 ? String(page - 1) : null, finding: null })}
            >
              Previous
            </button>
            <span className="caption num">
              {page * PAGE + 1}–{Math.min((page + 1) * PAGE, findings.data.total)} of{" "}
              {findings.data.total}
            </span>
            <button
              type="button"
              className="button button-secondary button-small"
              disabled={(page + 1) * PAGE >= findings.data.total}
              onClick={() => setParams({ page: String(page + 1), finding: null })}
            >
              Next
            </button>
          </div>
        ) : null}
      </div>

      {selected ? (
        <FindingPanel
          snapshotId={snapshotId}
          finding={selected}
          rule={ruleById.get(selected.rule_id)}
          onClose={() => setParams({ finding: null }, false)}
        />
      ) : null}
    </div>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
}) {
  const id = useId();
  return (
    <span className="filter">
      <label htmlFor={id}>{label}</label>
      <select id={id} className="select" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">All</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </span>
  );
}

/** Path prefix, applied on Enter or blur (not on every key: each change is a new request). */
function PathFilter({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const id = useId();
  const [draft, setDraft] = useState(value);
  useEffect(() => {
    setDraft(value);
  }, [value]);
  const apply = () => {
    if (draft.trim() !== value) onChange(draft.trim());
  };
  return (
    <span className="filter">
      <label htmlFor={id}>Path starts with</label>
      <input
        id={id}
        className="input input-small mono"
        value={draft}
        placeholder="e.g. src/"
        spellCheck={false}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={apply}
        onKeyDown={(e) => {
          if (e.key === "Enter") apply();
        }}
      />
    </span>
  );
}

function FindingsList({
  query,
  filtered,
  selectedId,
  onSelect,
}: {
  query: UseQueryResult<FindingsPage>;
  filtered: boolean;
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  if (query.error && !query.data) {
    return (
      <div className="panel-message" role="alert">
        <p>Could not load findings. {query.error.message}</p>
        <button className="button button-secondary" onClick={() => query.refetch()}>
          Try again
        </button>
      </div>
    );
  }
  if (!query.data) {
    return (
      <div className="panel-message" aria-busy="true">
        {[70, 55, 62].map((w, i) => (
          <div key={i} className="skeleton" style={{ width: `${w}%`, marginTop: i ? 12 : 0 }} />
        ))}
      </div>
    );
  }
  if (query.data.items.length === 0) {
    // Never a verdict (spec §5.6): no rows is not "safe".
    return (
      <p className="panel-message">
        {filtered
          ? "No findings match these filters."
          : "No findings from our current rules. This does not guarantee the code is safe."}
      </p>
    );
  }
  return (
    <div className="findings-table" aria-busy={query.isPlaceholderData || undefined}>
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Severity</th>
            <th scope="col">Finding</th>
            <th scope="col">Location</th>
          </tr>
        </thead>
        <tbody>
          {query.data.items.map((f) => (
            <tr key={f.id} aria-selected={f.id === selectedId}>
              <td className="severity-col">
                <SeverityBadge severity={f.severity} />
              </td>
              <td>
                <button type="button" className="row-button" onClick={() => onSelect(f.id)}>
                  {f.message}
                </button>
                {f.in_test ? <span className="tag finding-tag">test or example</span> : null}
              </td>
              <td className="mono location-col">
                {f.path}
                <span className="nowrap">:{f.line}</span>
                {f.rule_id === SECRET_RULE ? (
                  <span className="caption nowrap"> (value hidden)</span>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FindingPanel({
  snapshotId,
  finding,
  rule,
  onClose,
}: {
  snapshotId: number;
  finding: Finding;
  rule: Rule | undefined;
  onClose: () => void;
}) {
  const titleId = useId();
  const titleRef = useRef<HTMLHeadingElement>(null);
  const [copied, setCopied] = useState(false);
  const location = `${finding.path}:${finding.line}`;
  const secret = finding.rule_id === SECRET_RULE;

  useEffect(() => {
    titleRef.current?.focus();
    setCopied(false);
  }, [finding.id]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(location);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <aside className="panel" aria-labelledby={titleId}>
      <header className="panel-header">
        <div className="panel-heading">
          <SeverityBadge severity={finding.severity} />
          <h2 id={titleId} ref={titleRef} tabIndex={-1} className="panel-title finding-title">
            {finding.message}
          </h2>
          <p className="caption mono">
            {location}
            {finding.symbol ? ` · ${finding.symbol}` : null}
          </p>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close panel (Esc)">
          <Icon name="x" />
        </button>
      </header>
      <div className="panel-body finding-body">
        {finding.in_test ? (
          <p className="note">In test or example code, so it is less likely to matter in production.</p>
        ) : null}
        {rule ? (
          <dl className="finding-facts">
            <dt>What this rule looks for</dt>
            <dd>{rule.checks}</dd>
            <dt>Why it can be risky</dt>
            <dd>{rule.why}</dd>
            <dt>Check before acting</dt>
            <dd>{rule.false_positive}</dd>
          </dl>
        ) : null}
        {finding.snippet ? (
          <figure className="finding-snippet">
            <figcaption className="caption">
              Line {finding.line}
              {secret ? " · the value is hidden" : null}
            </figcaption>
            <pre className="mono">{finding.snippet}</pre>
          </figure>
        ) : null}
        <div className="callout-actions">
          <Link
            className="button button-secondary button-small"
            to={exploreHref(snapshotId, {
              fileId: finding.file_id,
              lines: { start: finding.line, end: finding.line },
              tests: finding.in_test,
            })}
          >
            Open in Explorer
          </Link>
          <button type="button" className="button button-secondary button-small" onClick={copy}>
            <Icon name="copy" size={14} />
            {copied ? "Copied" : "Copy location"}
          </button>
        </div>
      </div>
    </aside>
  );
}
