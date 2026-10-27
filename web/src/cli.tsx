import { useState } from 'react';

type Stage = { name: string; kind: string; outcome: string; detail: string };
type Invocation = {
  executable: string; arguments: string[]; workspace: string; exit_code: number;
  duration_ms: number; stderr_summary: string; session_id: string; stats: Record<string, unknown>;
};
type Grounding = {
  paths_claimed: string[]; paths_present: string[]; paths_absent: string[];
  grounded: boolean; limitations: string[];
};
type InspectResult = {
  answer: { answer: string; limitations: string[] };
  grounding: Grounding;
  plan: { task: string; rationale: string; expected_evidence: string[] } | null;
  stages: Stage[];
  cli_invocation: Invocation | null;
  cli_actually_ran: boolean;
  usage: { prompt_tokens: number; output_tokens: number; thought_tokens: number };
};

const KIND_LABEL: Record<string, string> = {
  adk_llm_agent: 'ADK model step',
  adk_deterministic_agent: 'ADK deterministic step (no model)',
  gemini_cli_subprocess: 'Gemini CLI subprocess',
};

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    return typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body);
  } catch {
    return `${response.status} ${response.statusText}`;
  }
}

export function CliInspector({ token, session }: { token: string; session: string }) {
  const [question, setQuestion] = useState('');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<InspectResult | null>(null);
  const [error, setError] = useState('');

  async function run() {
    setRunning(true); setError(''); setResult(null);
    try {
      const response = await fetch(`/api/agents/gemini_cli_tool/${session}/inspect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ question: question.trim() }),
      });
      if (!response.ok) throw new Error(await readError(response));
      setResult(await response.json());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setRunning(false);
    }
  }

  return <>
    <section className="panel">
      <h2>Ask about the authorized workspace</h2>
      <p>The ADK pipeline plans the task, then a separate <code>gemini</code> process
        inspects one read-only directory. A deterministic step then checks that the files
        it named really exist.</p>
      <label htmlFor="question">Question (10–2000 characters)</label>
      <input id="question" value={question} onChange={event => setQuestion(event.target.value)}
        placeholder="How does this project load configuration and authenticate requests?"/>
      <button onClick={run} disabled={question.trim().length < 10 || running}>
        {running ? 'Running pipeline…' : 'Run pipeline'}
      </button>
      {running && <p role="status">Planning, then invoking the CLI subprocess. Usually under two minutes.</p>}
      {error && <div className="error" role="alert">{error}</div>}
    </section>

    {result && <section className="panel">
      <h2>Pipeline stages</h2>
      <p>{result.cli_actually_ran
        ? 'The Gemini CLI subprocess completed. Planning and execution are separate steps below.'
        : 'The Gemini CLI subprocess did not complete; no answer is presented as verified.'}</p>
      <ol className="stages">
        {result.stages.map((stage, index) => <li key={index} className={stage.kind}>
          <span className="eyebrow">{KIND_LABEL[stage.kind] ?? stage.kind}</span>
          <strong>{stage.name}</strong>
          <span className="state">{stage.outcome}</span>
          {stage.detail && <p className="meta">{stage.detail}</p>}
        </li>)}
      </ol>
      {result.plan && <>
        <h3>What the ADK planning step decided</h3>
        <blockquote>{result.plan.task}</blockquote>
        <p className="meta">{result.plan.rationale}</p>
      </>}
    </section>}

    {result?.cli_invocation && <section className="panel">
      <h2>Actual process invocation</h2>
      <p>Safe fields only. The task text is redacted so a prompt never reaches a log.</p>
      <dl className="invocation">
        <dt>Executable</dt><dd><code>{result.cli_invocation.executable}</code></dd>
        <dt>Arguments</dt><dd><code>{result.cli_invocation.arguments.join(' ')}</code></dd>
        <dt>Workspace</dt><dd><code>{result.cli_invocation.workspace}</code></dd>
        <dt>Exit code</dt><dd>{result.cli_invocation.exit_code}</dd>
        <dt>Duration</dt><dd>{result.cli_invocation.duration_ms} ms</dd>
        <dt>CLI session</dt><dd><code>{result.cli_invocation.session_id || 'unreported'}</code></dd>
        {result.cli_invocation.stderr_summary && <>
          <dt>Stderr</dt><dd className="meta">{result.cli_invocation.stderr_summary}</dd></>}
      </dl>
    </section>}

    {result && <section className="panel">
      <h2>Answer</h2>
      <p className={result.grounding.grounded ? 'state' : 'error'}>
        {result.grounding.grounded
          ? `Grounded: all ${result.grounding.paths_present.length} named paths exist in the inspected workspace.`
          : `Not fully grounded: ${result.grounding.paths_present.length} named paths verified, ${result.grounding.paths_absent.length} not found.`}
      </p>
      <pre className="answer">{result.answer.answer}</pre>
      <h3>Verified paths</h3>
      <ul className="queries">{result.grounding.paths_present.map(path => <li key={path}><code>{path}</code></li>)}</ul>
      {result.grounding.paths_absent.length > 0 && <>
        <h3>Named but absent</h3>
        <ul className="queries">{result.grounding.paths_absent.map(path => <li key={path}><code>{path}</code></li>)}</ul>
      </>}
      <h3>Limitations</h3>
      <ul className="limitations">{result.answer.limitations.map(line => <li key={line}>{line}</li>)}</ul>
      <p className="meta">{result.usage.prompt_tokens} prompt, {result.usage.output_tokens} output
        and {result.usage.thought_tokens} thinking tokens across the ADK steps.</p>
    </section>}
  </>;
}
