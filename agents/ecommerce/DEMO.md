# Part E video and execution artifacts

- [Public GitHub repository](https://github.com/ArshanBhanage/adk-ecommerce-postgresql).
- Local MP4: [Narrated code and execution walkthrough](video/part-e-walkthrough.mp4).
- Narration source: [chapters.json](video/chapters.json).
- Actual browser execution: appended to the MP4 after the code/evidence chapters.
- YouTube URL: **PENDING — no upload or channel authorization has been verified**.

The narration is synthesized using macOS `say`; it is not represented as the
student's own voice. The code excerpts come from the current repository, and the
browser segment was recorded against the live local app and authorized Shopify
store. Credentials remain masked and raw cart secrets are not displayed. The video
makes no payment, AlloyDB, public hosting or production inventory claim.

## Video sections

1. Approved PostgreSQL substitution, architecture and connected-store caveat.
2. Actual Shopify import and transactional source-ID synchronization.
3. Restricted MCP tools and Vertex ADK orchestration.
4. Server-side account/cart ownership and local authentication.
5. Confirmed, duplicate-safe Shopify operations and failure handling.
6. Live API/Vertex evidence, explicit limitations, followed by browser execution.

## Reproduce the browser recording

Start PostgreSQL, MCP and the app using README.md. Issue the two demo credentials
only if absent. Put an actual available product title from the imported catalog in
`.local/browser-query.txt`. Then, from repository root:

```sh
cd agents/ecommerce/web
npx playwright install chromium
node browser-check.mjs
node render-video.mjs
```

Rendering additionally requires macOS `say`, FFmpeg and ffprobe. The raw video,
audio and intermediate frames stay in ignored `.local/`; the finished MP4 is an
artifact suitable for review/upload. Use `PLAYWRIGHT_BROWSERS_PATH` if your browser
runtime was installed outside the default location.

## Submission

Upload the reviewed MP4 to the student's YouTube channel (or record the supplied
walkthrough in the student's own voice if required by course policy). Add the real
YouTube URL here and to the final assignment submission. Never invent a video URL.
GitHub source/evidence alone does not satisfy the separate YouTube requirement.
