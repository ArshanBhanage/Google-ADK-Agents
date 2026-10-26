# React interface

`make run-web` starts Vite on loopback. The proxy forwards /api to port 8000.
The overview and five hash routes show actual backend readiness. A part page can
create an authenticated persistent session; agent execution is not implemented.
Credentials remain in component memory and are never saved in browser storage.

`npm run build` checks TypeScript and builds the app. `npm run test:e2e` runs a real
Chromium test against a locally started API; it does not intercept API requests.
