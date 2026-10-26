# API foundation

`make run-api` starts the local FastAPI service at 127.0.0.1:8000.
GET /api/health is liveness. GET /api/readiness returns 503 while agents are
unimplemented or dependencies are missing; configuration is never labeled live.

Authenticated POST /api/sessions accepts `{ "agent": "lead_research" }` (or another
of the five fixed IDs). It returns the persisted session ID and agent. GET/DELETE
/api/sessions/{agent}/{session_id} enforce server-derived ownership. Extra fields,
including user_id, are rejected. See /docs for the generated OpenAPI schemas.

Sessions use actual ADK DatabaseSessionService. No Runner invocation is delivered
until agent A's implementation gate. The session endpoint alone is not an agent.
