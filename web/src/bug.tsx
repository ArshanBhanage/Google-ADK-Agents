import { useState } from 'react';

type Stage = { name: string; kind: string; outcome: string; detail: string };
type Duplicate = {
  number: number; title: string; url: string; state: string; updated_at: string; why_similar: string;
};
type Report = {
  severity: string; severity_rationale: string; root_cause_hypothesis: string;
  reproduction_steps: string[]; debugging_checklist: string[];
  duplicate_candidates: Duplicate[]; next_action: string; limitations: string[];
};
type Proposed = { owner: string; repo: string; title: string; body: string };
type Approval = {
  approval_token: string; content_sha256: string; repository: string;
  expires_in_seconds: number; write_path_blocked_by: string[];
};
type TriageResult = {
  triage: {
    report: Report; verified_duplicates: Duplicate[]; discarded_duplicates: string[];
    repository: string; issues_searched: number;
  };
  proposed_issue: Proposed | null;
  approval: Approval | null;
  stages: Stage[];
  mcp_actually_used: boolean;
  usage: { prompt_tokens: number; output_tokens: number; thought_tokens: number };
};
type Created = { number: number; url: string; state: string };

const KIND_LABEL: Record<string, string> = {
  adk_llm_agent: 'ADK model step',
  adk_deterministic_agent: 'ADK deterministic step (no model)',
  mcp_tool_call: 'MCP tool call',
};

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    return typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body);
  } catch {
    return `${response.status} ${response.statusText}`;
  }
}

export function BugAssistant({ token, session }: { token: string; session: string }) {
  const [owner, setOwner] = useState('');
  const [repo, setRepo] = useState('');
  const [description, setDescription] = useState('');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<TriageResult | null>(null);
  const [created, setCreated] = useState<Created | null>(null);
  const [filing, setFiling] = useState(false);
  const [confirmFile, setConfirmFile] = useState(false);
  const [error, setError] = useState('');

  const ready = owner.trim() && repo.trim() && description.trim().length >= 20;

  async function run() {
    setRunning(true); setError(''); setResult(null); setCreated(null); setConfirmFile(false);
    try {
      const response = await fetch(`/api/agents/bug_assistant/${session}/triage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ owner: owner.trim(), repo: repo.trim(), description: description.trim() }),
      });
      if (!response.ok) throw new Error(await readError(response));
      setResult(await response.json());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally { setRunning(false); }
  }

  async function fileIssue() {
    if (!result?.approval || !result.proposed_issue) return;
    setFiling(true); setError('');
    try {
      const response = await fetch(`/api/agents/bug_assistant/${session}/create-issue`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          approval_token: result.approval.approval_token,
          proposed_issue: result.proposed_issue,
        }),
      });
      if (!response.ok) throw new Error(await readError(response));
      setCreated(await response.json());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally { setFiling(false); setConfirmFile(false); }
  }

  const blocked = result?.approval?.write_path_blocked_by ?? [];

  return <>
    <section className="panel">
      <h2>Report a bug</h2>
      <p>Only repositories the operator allowlisted can be searched. The repository is
        fixed server-side; nothing in the description can redirect it.</p>
      <div className="fields">
        <div><label htmlFor="owner">Owner</label>
          <input id="owner" value={owner} onChange={e => setOwner(e.target.value)} placeholder="google"/></div>
        <div><label htmlFor="repo">Repository</label>
          <input id="repo" value={repo} onChange={e => setRepo(e.target.value)} placeholder="adk-python"/></div>
        <div className="wide"><label htmlFor="desc">What goes wrong (20–4000 characters)</label>
          <input id="desc" value={description} onChange={e => setDescription(e.target.value)}/></div>
      </div>
      <button onClick={run} disabled={!ready || running}>{running ? 'Triaging…' : 'Triage against live issues'}</button>
      {running && <p role="status">Searching real issues over MCP. Usually under a minute.</p>}
      {error && <div className="error" role="alert">{error}</div>}
    </section>

    {result && <section className="panel">
      <h2>Pipeline stages</h2>
      <p>{result.mcp_actually_used
        ? 'Issue data came from live MCP tool calls, shown below.'
        : 'No MCP tool call was observed, so nothing here is presented as verified.'}</p>
      <ol className="stages">
        {result.stages.map((stage, index) => <li key={index} className={stage.kind}>
          <span className="eyebrow">{KIND_LABEL[stage.kind] ?? stage.kind}</span>
          <strong>{stage.name}</strong>
          <span className="state">{stage.outcome}</span>
          {stage.detail && <p className="meta">{stage.detail}</p>}
        </li>)}
      </ol>
    </section>}

    {result && <section className="panel">
      <h2>Triage</h2>
      <p><span className="state">severity {result.triage.report.severity}</span></p>
      <p>{result.triage.report.severity_rationale}</p>
      <h3>Root cause hypothesis</h3>
      <p>{result.triage.report.root_cause_hypothesis}</p>
      <h3>Possible duplicates ({result.triage.verified_duplicates.length} verified of
        {' '}{result.triage.issues_searched} issues searched)</h3>
      {result.triage.verified_duplicates.length === 0
        ? <p role="status">No existing issue matched closely enough to call a duplicate.</p>
        : <ul className="citations">
            {result.triage.verified_duplicates.map(duplicate => <li key={duplicate.number}>
              <a href={duplicate.url} target="_blank" rel="noreferrer noopener">
                #{duplicate.number} {duplicate.title}
              </a>
              <span className="meta">{duplicate.state} · updated {duplicate.updated_at}</span>
              <p>{duplicate.why_similar}</p>
            </li>)}
          </ul>}
      {result.triage.discarded_duplicates.length > 0 && <>
        <h3>Discarded claims</h3>
        <ul className="limitations">
          {result.triage.discarded_duplicates.map(line => <li key={line}>{line}</li>)}
        </ul>
      </>}
      <h3>Reproduction steps</h3>
      <ol>{result.triage.report.reproduction_steps.map(step => <li key={step}>{step}</li>)}</ol>
      <h3>Debugging checklist</h3>
      <ol>{result.triage.report.debugging_checklist.map(step => <li key={step}>{step}</li>)}</ol>
      <h3>Next action</h3>
      <p>{result.triage.report.next_action}</p>
      <h3>Limitations</h3>
      <ul className="limitations">
        {result.triage.report.limitations.map(line => <li key={line}>{line}</li>)}
      </ul>
      <p className="meta">{result.usage.prompt_tokens} prompt, {result.usage.output_tokens} output
        and {result.usage.thought_tokens} thinking tokens.</p>
    </section>}

    {result?.proposed_issue && <section className="panel">
      <h2>Draft issue — nothing has been filed</h2>
      <p>This is the exact content a write would create. Approval is bound to its
        SHA-256, so any edit invalidates it.</p>
      <dl className="invocation">
        <dt>Target</dt><dd><code>{result.proposed_issue.owner}/{result.proposed_issue.repo}</code></dd>
        <dt>Title</dt><dd>{result.proposed_issue.title}</dd>
        {result.approval && <>
          <dt>Content SHA-256</dt><dd><code>{result.approval.content_sha256.slice(0, 32)}…</code></dd>
          <dt>Approval expires</dt><dd>in {Math.round(result.approval.expires_in_seconds / 60)} minutes</dd>
        </>}
      </dl>
      <pre className="answer">{result.proposed_issue.body}</pre>

      {created
        ? <p role="status">Filed as <a href={created.url} target="_blank" rel="noreferrer noopener">
            #{created.number}</a> ({created.state}). The number and URL come from GitHub.</p>
        : blocked.length > 0
          ? <div className="error" role="status">The write path is disabled. To enable it set
              {' '}<code>{blocked.join(', ')}</code> in <code>agents/bug_assistant/.env</code>,
              using a second token scoped to write Issues on this repository only.</div>
          : !confirmFile
            ? <button onClick={() => setConfirmFile(true)}>File this issue…</button>
            : <div className="confirm" role="group" aria-label="Confirm filing">
                <p><strong>This creates a real, public issue in
                  {' '}{result.proposed_issue.owner}/{result.proposed_issue.repo}.</strong> It
                  cannot be undone from here.</p>
                <button onClick={fileIssue} disabled={filing}>
                  {filing ? 'Filing…' : 'Yes, file it'}
                </button>
                <button className="secondary" onClick={() => setConfirmFile(false)} disabled={filing}>
                  Cancel
                </button>
              </div>}
    </section>}
  </>;
}
