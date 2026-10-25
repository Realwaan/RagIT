# Frontend completion

The existing assistant-ui, Radix, Tailwind, and Lucide components are retained.

Delivered:

- Searchable document library with document details and PDF page navigation.
- Conversation renaming, active conversation restoration, and immediate draft persistence.
- Separate conversations when switching documents after messages have been sent.
- Empty-file validation, upload retry and cancellation, and missing-document recovery.
- Image zoom that changes the rendered image size, retry, fit, and correct page navigation.
- Inline export failures and retry, stopped-response controls, and interrupted-stream recovery.
- Responsive library, evidence controls, and composer at 320, 390, and 768 pixels.
- Dialog focus restoration using Radix triggers for the new library and rename flows.

Validation:

- Production TypeScript and Vite build: passed.
- Six existing UI rendering tests: passed.
- Extended Chromium fixture checks: passed with no page errors; see `verification.json`.
- Real-backend browser checks: passed, including PDF upload, local table retrieval,
  page 3 citation, actual crop/preview requests, PDF export, and persisted conversations;
  see `../assistant-ui-check.json`.
- Real PDF screenshots: `library-real-pdf.png`, `evidence-real-pdf.png`, and `answer-real-pdf.png`.

Limits:

- Real-backend checks used local embeddings and extractive answers with external
  models disabled. The offline definition fallback refused “What is the uptime
  guarantee?”; the UI displayed that refusal and successfully allowed editing to
  “Which availability percentage is guaranteed?”.
- Vite reports an existing large JavaScript bundle and a config-loader migration warning.
- Files are held in the running backend vault; conversation history is browser-local.
  Server-side work may finish after a browser upload is cancelled.
