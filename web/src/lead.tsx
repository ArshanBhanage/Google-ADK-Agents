import { useState } from 'react';

type Citation = { url: string; retrieved_at: string; excerpt: string; content_sha256: string };
type Lead = {
  name: string; domain: string; match_explanation: string; score: number;
  confidence: string; verification: string; citations: Citation[];
};
type Usage = {
  prompt_tokens: number; output_tokens: number; thought_tokens: number; billable_searches: number;
};
export type ResearchResult = {
  report: { leads: Lead[]; limitations: string[] };
  searches: string[];
  grounding_sources: string[];
  search_suggestions: string[];
  tool_calls: { agent: string; tool: string; outcome: string }[];
  retrieved_sources: string[];
  model_versions: string[];
  usage: Usage;
};

const BLANK = { industry: '', region: '', buyer_profile: '', quantity: 3, exclusions: '' };

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === 'string') return body.detail;
    return JSON.stringify(body.detail ?? body);
  } catch {
    return `${response.status} ${response.statusText}`;
  }
}

export function LeadResearch({ token, session }: { token: string; session: string }) {
  const [form, setForm] = useState(BLANK);
  const [confirming, setConfirming] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [error, setError] = useState('');

  const complete = form.industry.trim().length > 1 && form.region.trim().length > 1
    && form.buyer_profile.trim().length > 4;

  function field<K extends keyof typeof BLANK>(key: K, value: (typeof BLANK)[K]) {
    setForm(previous => ({ ...previous, [key]: value }));
    setConfirming(false);
  }

  async function run() {
    setRunning(true); setError(''); setResult(null);
    try {
      const response = await fetch(`/api/agents/lead_research/${session}/research`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          industry: form.industry.trim(),
          region: form.region.trim(),
          buyer_profile: form.buyer_profile.trim(),
          quantity: form.quantity,
          exclusions: form.exclusions.split(',').map(item => item.trim()).filter(Boolean),
        }),
      });
      if (!response.ok) throw new Error(await readError(response));
      setResult(await response.json());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setRunning(false); setConfirming(false);
    }
  }

  async function download() {
    setError('');
    try {
      const response = await fetch(`/api/agents/lead_research/${session}/export.csv`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error(await readError(response));
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `leads-${session}.csv`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  return <>
    <section className="panel">
      <h2>Ideal customer profile</h2>
      <p>Every field is sent to live search. Confirm before running, because each run
        issues real billable search queries.</p>
      <div className="fields">
        <div><label htmlFor="industry">Industry</label>
          <input id="industry" value={form.industry} onChange={e => field('industry', e.target.value)}/></div>
        <div><label htmlFor="region">Region</label>
          <input id="region" value={form.region} onChange={e => field('region', e.target.value)}/></div>
        <div className="wide"><label htmlFor="buyer">Buyer or company profile</label>
          <input id="buyer" value={form.buyer_profile} onChange={e => field('buyer_profile', e.target.value)}/></div>
        <div><label htmlFor="quantity">Leads wanted (1–10)</label>
          <input id="quantity" type="number" min={1} max={10} value={form.quantity}
            onChange={e => field('quantity', Number(e.target.value))}/></div>
        <div className="wide"><label htmlFor="exclusions">Exclusions (comma separated, optional)</label>
          <input id="exclusions" value={form.exclusions} onChange={e => field('exclusions', e.target.value)}/></div>
      </div>
      {!confirming
        ? <button onClick={() => setConfirming(true)} disabled={!complete || running}>Review criteria</button>
        : <div className="confirm" role="group" aria-label="Confirm criteria">
            <p>Search for <strong>{form.quantity}</strong> leads in <strong>{form.industry}</strong>,
              region <strong>{form.region}</strong>, profile “{form.buyer_profile}”
              {form.exclusions.trim() && <> excluding <strong>{form.exclusions}</strong></>}?</p>
            <button onClick={run} disabled={running}>{running ? 'Researching…' : 'Confirm and run live search'}</button>
            <button className="secondary" onClick={() => setConfirming(false)} disabled={running}>Edit</button>
          </div>}
      {running && <p role="status">Running grounded research. This takes roughly a minute.</p>}
      {error && <div className="error" role="alert">{error}</div>}
    </section>

    {result && <section className="panel">
      <h2>Verified leads</h2>
      {result.report.leads.length === 0
        ? <p role="status">No lead met the evidence rule: a cited excerpt must appear in the
            page actually fetched and that page must name the company. This is a real empty
            result, not a failure. See the limitations below and try broader criteria.</p>
        : <>
            <p>{result.report.leads.length} of {result.retrieved_sources.length} retrieved
              sources produced a qualified lead. Scores measure source completeness, not
              commercial fit.</p>
            <button onClick={download}>Download CSV</button>
            <ol className="leads">
              {result.report.leads.map(lead => <li key={lead.domain}>
                <div className="lead-head">
                  <h3>{lead.name}</h3>
                  <span className="state">score {lead.score} · {lead.confidence} · {lead.verification.replaceAll('_', ' ')}</span>
                </div>
                <p className="domain"><a href={`https://${lead.domain}`} target="_blank" rel="noreferrer noopener">{lead.domain}</a></p>
                <p>{lead.match_explanation}</p>
                <ul className="citations">
                  {lead.citations.map(citation => <li key={citation.url + citation.excerpt.slice(0, 24)}>
                    <blockquote>“{citation.excerpt}”</blockquote>
                    <a href={citation.url} target="_blank" rel="noreferrer noopener">{citation.url}</a>
                    <span className="meta">retrieved {new Date(citation.retrieved_at).toISOString()} · sha256 {citation.content_sha256.slice(0, 16)}…</span>
                  </li>)}
                </ul>
              </li>)}
            </ol>
          </>}
      {result.report.limitations.length > 0 && <>
        <h3>Limitations reported by the run</h3>
        <ul className="limitations">{result.report.limitations.map(line => <li key={line}>{line}</li>)}</ul>
      </>}
    </section>}

    {result && result.search_suggestions.length > 0 && <section className="panel">
      <h2>Google Search suggestions</h2>
      <p>Displayed as returned by the grounding API, which its terms of use require.</p>
      {result.search_suggestions.map((markup, index) =>
        // Provider-rendered markup must be shown verbatim; see docs/security.md.
        <div key={index} className="suggestions" dangerouslySetInnerHTML={{ __html: markup }}/>)}
    </section>}

    {result && <section className="panel">
      <h2>Observed trace</h2>
      <p>Model {result.model_versions.join(', ') || 'unreported'} ·
        {' '}{result.usage.billable_searches} billable search queries ·
        {' '}{result.usage.prompt_tokens} prompt, {result.usage.output_tokens} output and
        {' '}{result.usage.thought_tokens} thinking tokens.</p>
      <h3>Search queries actually issued</h3>
      <ul className="queries">{result.searches.map(query => <li key={query}><code>{query}</code></li>)}</ul>
      <h3>Source retrieval outcomes</h3>
      <ul className="queries">
        {result.tool_calls.filter(call => call.outcome !== 'called').map((call, index) =>
          <li key={index}><code>{call.tool}</code> → {call.outcome}</li>)}
      </ul>
      <h3>Pages retrieved and hashed</h3>
      <ul className="queries">{result.retrieved_sources.map(url => <li key={url}><code>{url}</code></li>)}</ul>
    </section>}
  </>;
}
