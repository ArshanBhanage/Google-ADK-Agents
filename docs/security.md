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
