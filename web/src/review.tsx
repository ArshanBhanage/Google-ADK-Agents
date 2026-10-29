import { useState } from 'react';

type Stage = { name: string; kind: string; outcome: string };
type Comment = {
  path: string; line: number; severity: string; category: string;
  finding: string; recommendation: string; confidence: string; rule: string;
};
type Evidence = {
  path: string; line: number; rule: string; message: string; source: string; severity: string;
};
type Report = {
  repository: string; pull_request: number; title: string; head_sha: string; url: string;
  summary: string; blocking: boolean;
  verified_comments: Comment[]; unverified_comments: Comment[]; discarded_comments: string[];
  tool_evidence: Evidence[]; evidence_outside_diff: number;
  files_analysed: string[]; files_unanalysed: string[];
  tool_versions: Record<string, string>;
  test_status: string; test_reason: string; test_isolation: Record<string, string>;
  limitations: string[];
};
type Proposed = { owner: string; repo: string; pull_request: number; body: string };
type ReviewResult = {
  report: Report; markdown: string; proposed_comment: Proposed;
  approval: {
    approval_token: string; content_sha256: string; repository: string;
    expires_in_seconds: number; write_path_blocked_by: string[];
  };
  stages: Stage[];
  usage: { prompt_tokens: number; output_tokens: number; thought_tokens: number };
};
type Posted = { id: number; url: string };

const KIND_LABEL: Record<string, string> = {
  adk_deterministic_agent: 'ADK deterministic step (no model)',
  adk_llm_agent: 'ADK model step',
};

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    return typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body);
  } catch {
    return `${response.status} ${response.statusText}`;
  }
}

function CommentList({ comments, heading, note }: { comments: Comment[]; heading: string; note: string }) {
  if (comments.length === 0) return null;
  return <>
    <h3>{heading} <span className="meta">({note})</span></h3>
    <ul className="citations">
      {comments.map((c, i) => <li key={i}>
        <strong><code>{c.path}:{c.line}</code></strong>
        <span className="state"> {c.severity} · {c.category}{c.rule ? ` · ${c.rule}` : ''}</span>
        <p>{c.finding}</p>
        <p className="meta">Recommendation ({c.confidence} confidence): {c.recommendation}</p>
      </li>)}
    </ul>
  </>;
}

export function CodeReviewer({ token, session }: { token: string; session: string }) {
  const [owner, setOwner] = useState('');
  const [repo, setRepo] = useState('');
  const [number, setNumber] = useState('');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<ReviewResult | null>(null);
  const [posted, setPosted] = useState<Posted | null>(null);
  const [confirmPost, setConfirmPost] = useState(false);
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState('');

  const ready = owner.trim() && repo.trim() && Number(number) > 0;

  async function run() {
    setRunning(true); setError(''); setResult(null); setPosted(null); setConfirmPost(false);
    try {
      const response = await fetch(`/api/agents/code_reviewer/${session}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ owner: owner.trim(), repo: repo.trim(), pull_request: Number(number) }),
      });
      if (!response.ok) throw new Error(await readError(response));
      setResult(await response.json());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally { setRunning(false); }
  }

  async function publish() {
    if (!result) return;
    setPosting(true); setError('');
    try {
      const response = await fetch(`/api/agents/code_reviewer/${session}/comment`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          approval_token: result.approval.approval_token,
          proposed_comment: result.proposed_comment,
        }),
      });
      if (!response.ok) throw new Error(await readError(response));
      setPosted(await response.json());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally { setPosting(false); setConfirmPost(false); }
  }

  const blocked = result?.approval.write_path_blocked_by ?? [];

  return <>
    <section className="panel">
      <h2>Review a pull request</h2>
      <p>Only repositories the operator allowlisted can be reviewed. Review is read-only:
        nothing is posted, approved or merged unless you separately authorize a comment.</p>
      <div className="fields">
        <div><label htmlFor="r-owner">Owner</label>
          <input id="r-owner" value={owner} onChange={e => setOwner(e.target.value)} placeholder="google"/></div>
        <div><label htmlFor="r-repo">Repository</label>
          <input id="r-repo" value={repo} onChange={e => setRepo(e.target.value)} placeholder="adk-python"/></div>
        <div><label htmlFor="r-num">Pull request number</label>
          <input id="r-num" type="number" min={1} value={number} onChange={e => setNumber(e.target.value)}/></div>
      </div>
      <button onClick={run} disabled={!ready || running}>{running ? 'Reviewing…' : 'Review'}</button>
      {running && <p role="status">Fetching the diff, running Ruff and the AST parser, then synthesising.</p>}
      {error && <div className="error" role="alert">{error}</div>}
    </section>

    {result && <section className="panel">
      <h2>Pipeline stages</h2>
      <ol className="stages">
        {result.stages.map((stage, index) => <li key={index} className={stage.kind}>
          <span className="eyebrow">{KIND_LABEL[stage.kind] ?? stage.kind}</span>
          <strong>{stage.name}</strong>
          <span className="state">{stage.outcome}</span>
        </li>)}
      </ol>
      <p className="meta">Retrieval, diff mapping, Ruff and the AST parser all run in the
        deterministic stages. The model only reasons about lines they declared admissible.</p>
    </section>}

    {result && <section className="panel">
      <h2>
        <a href={result.report.url} target="_blank" rel="noreferrer noopener">
          {result.report.repository}#{result.report.pull_request}
        </a>
      </h2>
      <p><strong>{result.report.title}</strong></p>
      <p>
        <span className={result.report.blocking ? 'error' : 'state'}>
          {result.report.blocking ? 'Changes requested' : 'No blocking findings'}
        </span>
        {' · '}tests <code>{result.report.test_status}</code>
        {' · '}commit <code>{result.report.head_sha.slice(0, 12)}</code>
      </p>
      <p>{result.report.summary}</p>

      <CommentList comments={result.report.verified_comments} heading="Verified findings"
        note="backed by a tool diagnostic that actually ran"/>
      <CommentList comments={result.report.unverified_comments} heading="Unverified findings"
        note="the reviewer's reading, not tool-confirmed"/>

      {result.report.discarded_comments.length > 0 && <>
        <h3>Discarded comments</h3>
        <ul className="limitations">
          {result.report.discarded_comments.map(line => <li key={line}>{line}</li>)}
        </ul>
      </>}

      <h3>Tool evidence on changed lines ({result.report.tool_evidence.length},
        {' '}{result.report.evidence_outside_diff} suppressed as outside the diff)</h3>
      <ul className="queries">
        {result.report.tool_evidence.map((e, i) => <li key={i}>
          <code>{e.path}:{e.line}</code> [{e.severity}] {e.rule} ({e.source}) — {e.message}
        </li>)}
      </ul>

      {result.report.files_unanalysed.length > 0 && <>
        <h3>Not analysed</h3>
        <ul className="limitations">
          {result.report.files_unanalysed.map(line => <li key={line}>{line}</li>)}
        </ul>
      </>}

      <h3>Test execution</h3>
      <p><code>{result.report.test_status}</code>
        {result.report.test_reason && <> — {result.report.test_reason}</>}</p>
      {Object.keys(result.report.test_isolation).length > 0 && <dl className="invocation">
        {Object.entries(result.report.test_isolation).map(([key, value]) =>
          <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{value}</dd></div>)}
      </dl>}

      <h3>Limitations</h3>
      <ul className="limitations">
        {result.report.limitations.map(line => <li key={line}>{line}</li>)}
      </ul>
      <p className="meta">{result.usage.prompt_tokens} prompt, {result.usage.output_tokens} output
        and {result.usage.thought_tokens} thinking tokens.</p>
    </section>}

    {result && <section className="panel">
      <h2>Post this review as a comment — nothing has been posted</h2>
      <p>Approval is bound to the SHA-256 of this exact text. Posting adds one comment to
        the pull request thread; it never approves and never merges.</p>
      <dl className="invocation">
        <dt>Target</dt><dd><code>{result.proposed_comment.owner}/{result.proposed_comment.repo}
          #{result.proposed_comment.pull_request}</code></dd>
        <dt>Content SHA-256</dt><dd><code>{result.approval.content_sha256.slice(0, 32)}…</code></dd>
      </dl>
      <pre className="answer">{result.markdown}</pre>
      {posted
        ? <p role="status">Posted as <a href={posted.url} target="_blank" rel="noreferrer noopener">
            comment {posted.id}</a>. The id and URL come from GitHub.</p>
        : blocked.length > 0
          ? <div className="error" role="status">Posting is disabled. To enable it set
              {' '}<code>REVIEW_COMMENT_ENABLED</code> and <code>REVIEW_COMMENT_TOKEN</code> in
              {' '}<code>agents/code_reviewer/.env</code>, using a token scoped to write Pull
              Requests on a repository you own. ({blocked.join(', ')})</div>
          : !confirmPost
            ? <button onClick={() => setConfirmPost(true)}>Post this comment…</button>
            : <div className="confirm" role="group" aria-label="Confirm posting">
                <p><strong>This posts a public comment on
                  {' '}{result.proposed_comment.owner}/{result.proposed_comment.repo}
                  #{result.proposed_comment.pull_request}.</strong> It cannot be undone from here.</p>
                <button onClick={publish} disabled={posting}>{posting ? 'Posting…' : 'Yes, post it'}</button>
                <button className="secondary" onClick={() => setConfirmPost(false)} disabled={posting}>Cancel</button>
              </div>}
    </section>}
  </>;
}
