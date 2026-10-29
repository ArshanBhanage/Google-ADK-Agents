import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BugAssistant } from './bug';
import { CliInspector } from './cli';
import { CodeReviewer } from './review';
import { LeadResearch } from './lead';
import './style.css';

type Agent = { id: string; name: string; status: string };
type Readiness = { status: string; authentication: string; missing: string[]; gemini: string; agents: Agent[] };
function App() {
  const [status, setStatus] = useState<Readiness | null>(null);
  const [error, setError] = useState('');
  const [route, setRoute] = useState(window.location.hash.slice(1));
  const [token, setToken] = useState('');
  const [session, setSession] = useState('');
  const [pending, setPending] = useState(false);
  useEffect(() => {
    const change = () => { setRoute(window.location.hash.slice(1)); setSession(''); setError(''); };
    window.addEventListener('hashchange', change);
    return () => window.removeEventListener('hashchange', change);
  }, []);
  useEffect(() => {
    const abort = new AbortController();
    fetch('/api/readiness', { signal: abort.signal }).then(async response => {
      if (response.status !== 503 && !response.ok) throw new Error('Readiness request failed.');
      const body: Readiness = await response.json();
      if (!Array.isArray(body.agents)) throw new Error('Unexpected readiness response.');
      setStatus(body);
    }).catch(reason => { if (!abort.signal.aborted) setError('Cannot reach the API. Start make run-api. ' + String(reason)); });
    return () => abort.abort();
  }, []);
  const selected = status?.agents.find(agent => agent.id === route);
  async function createSession() {
    if (!selected) return;
    setPending(true); setError('');
    try {
      const response = await fetch('/api/sessions', { method: 'POST', headers: {
        'Content-Type': 'application/json', 'Authorization': `Bearer ${token}`,
      }, body: JSON.stringify({ agent: selected.id }) });
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail));
      setSession(body.id);
    } catch (reason) { setError(String(reason)); }
    finally { setPending(false); }
  }
  return <div className="layout">
    <aside><a className="brand" href="#">ADK<span>AGENT SUITE</span></a><p className="eyebrow">ASSIGNMENT 03</p>
      <nav aria-label="Applications"><a href="#" aria-current={!route ? 'page' : undefined}>Overview</a>
        {status?.agents.map(agent => <a key={agent.id} href={`#${agent.id}`} aria-current={selected?.id === agent.id ? 'page' : undefined}>{agent.name}</a>)}
      </nav><p className="sidebar-note">Local development<br/>Evidence before completion.</p></aside>
    <main><header><span className="eyebrow">GOOGLE AGENT DEVELOPMENT KIT</span><span className="pill">Foundation · Verified locally</span></header>
      <h1>{selected ? selected.name.slice(4) : 'Five workflows. Verifiable results.'}</h1>
      <p className="intro">{selected ? (selected.id === 'lead_research' ? 'Grounded discovery over live Google Search, with every lead backed by an excerpt from a page this service fetched and hashed itself. Unverifiable candidates are reported, not dropped silently.' : 'This agent has not started. The authenticated session service is available for foundation verification.') : 'Research, tools, debugging, review and commerce. Each application advances only after its milestone gate is verified.'}</p>
      {error && <div className="error" role="alert">{error}</div>}
      {!status && !error && <p role="status">Checking the API…</p>}
      {status && <>
        <section className="connection"><div><span className="eyebrow">CONNECTION READINESS</span><h2>{status.status.replaceAll('_', ' ')}</h2><p>Credential presence does not prove provider connectivity.</p></div><div><strong>Missing configuration</strong><ul>{status.missing.map(field => <li key={field}><code>{field}</code></li>)}</ul>{!status.missing.length && <p>Configured; live verification still pending.</p>}</div></section>
        {selected ? <><section className="panel"><h2>Authenticate this session</h2><p>Use your local access token or an authorized Google ID token. It stays in this page’s memory.</p><label htmlFor="token">Access credential</label><input id="token" type="password" value={token} onChange={event => setToken(event.target.value)} autoComplete="off"/><button onClick={createSession} disabled={!token || pending}>{pending ? 'Creating…' : 'Create session'}</button>{session && <p role="status">Session created: <code>{session}</code>. It is scoped to your identity; another user cannot read it.</p>}</section>
          {selected.id === 'lead_research' && session && <LeadResearch token={token} session={session}/>}
          {selected.id === 'gemini_cli_tool' && session && <CliInspector token={token} session={session}/>}
          {selected.id === 'bug_assistant' && session && <BugAssistant token={token} session={session}/>}
          {selected.id === 'code_reviewer' && session && <CodeReviewer token={token} session={session}/>}
          {!['lead_research', 'gemini_cli_tool', 'bug_assistant', 'code_reviewer'].includes(selected.id) && <p>Agent execution is not implemented for this part.</p>}</>
          : <section className="grid" aria-label="Agent milestones">{status.agents.map(agent => <a className="card" key={agent.id} href={`#${agent.id}`}><span className="eyebrow">PART {agent.name[0]}</span><h2>{agent.name.slice(4)}</h2><span className="state">{agent.status.replaceAll('_', ' ')}</span><span className="arrow" aria-hidden="true">↗</span></a>)}</section>}
      </>}
      <footer>No live results, exports or deployment are claimed. Status reflects the current implementation.</footer>
    </main>
  </div>;
}
createRoot(document.getElementById('root')!).render(<App/>);
