# Foundation security boundaries

Local mode binds to loopback and uses a minimum-32-character bearer secret with
constant-time comparison. Its subject derives from the credential, never a
client/model-supplied user ID. Google mode validates issuer/signature/audience
through google-auth and checks the returned subject against an explicit allowlist.
Remote Google verification has not been exercised with a real identity token.

ADK session reads/deletes are scoped by subject, app and session ID. Tests use a
real on-disk database, restart the service and verify another identity cannot read
or delete the first user's session. No provider payloads or secret values enter
request logs; correlation logs contain only method, status, duration and random ID.

The API exposes no agent execution or external mutation endpoint in milestone 0.
Future side effects require server-enforced, expiring approval bound to the exact
user/action/payload, with atomic consumption. Prompt text cannot grant approval.
Future network tools must enforce SSRF defenses, limits and per-provider auth.
These future protections are design requirements, not implemented capabilities.

Use TLS and a shared durable session database before remote deployment. Local
SQLite stores conversation data on disk; `.local/` is ignored. Restrict its host
permissions, delete sessions through the authenticated DELETE endpoint, and define
retention before production use. API readiness lists missing names but never values.

## Rendering Google Search Suggestions (A2)

Grounding responses carry `groundingMetadata.searchEntryPoint.renderedContent`, and
Google's grounding terms require displaying those suggestions. The React results page
therefore injects that markup with `dangerouslySetInnerHTML` in `web/src/lead.tsx`.

This is a deliberate exception to the rule that provider and tool output is untrusted
data. The reasoning: the markup is first-party content from the Gemini API received
over TLS, it is required verbatim for compliance, and sanitising it would break the
rendering the terms oblige us to show. The exception is narrow — it applies only to
this one field, and no other provider or page content is ever rendered as HTML.

Everything else from the run is rendered as text or as an attribute. Citation
excerpts, lead names, match explanations and retrieved URLs all come from untrusted
web pages and are rendered through React's normal escaping. Outbound links carry
`rel="noreferrer noopener"`. The CSV export separately neutralises spreadsheet
formula injection, because a lead name scraped from a hostile page could otherwise
begin with `=`, `+`, `-` or `@`; `tests/unit/test_lead_export.py` covers that.

If the compliance position changes, the alternative is rendering the suggestion
chips from the structured fields rather than the supplied markup.
