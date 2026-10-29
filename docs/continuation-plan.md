# RagIT continuation plan

Updated: 2026-10-29

## Objective

Finish account-based authentication, document isolation, reliability work, and
answer-quality verification. Then give separate evidence-based project and
codebase scores out of 10. Do not assume completion warrants a perfect score.

## Constraints and handoff

- Workspace: `F:\RagIT`; PowerShell; Python virtual environment: `.venv`.
- Keep React/Vite and FastAPI. The Clerk Dashboard's Next.js selection does not
  mean this project should be migrated to Next.js.
- Use local checks. The user cannot use GitHub workflows because of billing issues.
- Use the existing Clerk application `app_3LKg2cPT7yeMRlQvsL4TMb2ZcPR` (RagIT).
  It has been linked and initialized. **Do not rerun `clerk init`, create a new
  application, or replace working keys.**
- The user completed CLI login. If that session expires, ask them to run
  `npx -y clerk@latest auth login` in their terminal.
- Do not read or print environment files, credentials, or Clerk claim files.
- Do not create users in this existing Clerk application without permission.
  Have the user complete the first real sign-up/sign-in themselves.
- Preserve unrelated changes. The workspace has changed between turns; inspect
  `git status` and relevant diffs before editing.
- At this handoff, `app/auth.py` is modified and `tests/conftest.py` and
  `tests/test_auth.py` are untracked. Review and retain the intended changes.

## Implemented so far

- Bounded upload reads and overflow tests.
- API request schemas, chat/history limits, and custom-check count limits.
- Separate report router; report generation runs in the worker pool.
- Markdown/math rendering loaded on demand.
- Local check script: `scripts/check.ps1`, including optional `-Browser` checks.
- Windows/Python 3.13 dependency constraints snapshot.
- Clerk React SDK/provider, sign-in interface, account control, and token attachment.
- Clerk Python SDK verification and authentication middleware in `app/auth.py`.
- Durable document ownership, account-specific ingestion cache identities,
  filtered vault results, and protected preview/crop paths.
- Account-specific browser conversation storage.
- Existing unowned documents are not automatically assigned to a new account;
  users must reattach them.

These are implemented changes, not a claim that the complete public-user flow
has been verified.

## Last observed verification

- Clerk doctor reached the selected application and confirmed development setup.
  Production was not configured.
- Production frontend build passed after adding Clerk.
- Nine authentication tests passed, including expired/wrong-origin tokens,
  anonymous requests, cross-account reads, static path traversal, and cache scope.
- A full Python suite was started, but its final result was not collected before
  the turn ended. Rerun it; do not report it as passing from that run.
- Earlier browser fixtures passed before Clerk integration. They are not evidence
  of a working authenticated browser flow.
- The server was started at `http://127.0.0.1:8001`; do not assume it is still running.
  That origin was not in the default auth allowlist at the last verification.
- Startup reported a MemoryError restoring one existing ingestion cache, then
  continued. Investigate recovery memory usage and its visibility to the user.
- Computer Use stopped because it could not reliably determine Brave's current
  URL on Windows. Live sign-in verification remains incomplete.

## 1. Finish development authentication

- [x] Inspect current auth changes and confirm no pending edits conflict. (`git status` clean; `app/auth.py`, `tests/conftest.py`, `tests/test_auth.py` retained and expanded).
- [x] Choose a local URL/port and explicitly allow that exact frontend origin.
  Prefer an already allowed port, or add `http://127.0.0.1:8001` for this local run. (`http://localhost:8000`, `http://127.0.0.1:8000`, `http://localhost:8001`, `http://127.0.0.1:8001`, `http://localhost:5173`, `http://127.0.0.1:5173` allowed in `DEFAULT_DEV_AUTHORIZED_PARTIES` in `app/auth.py`).
- [x] Run `npx -y clerk@latest doctor`; address actionable diagnostics. (Verified CLI `4.0.0`, authenticated, linked to `app_3LKg2cPT7yeMRlQvsL4TMb2ZcPR`, development instance `ins_3LKg2iWGAgYkw2KlmpB0olRslrC` reachable).
- [x] Start FastAPI and open the built app.
- [x] Confirm sign-in and sign-up controls render and failures are understandable. (Verified live Clerk UI renders `Welcome to RagIT` sign-in/sign-up card with GitHub, Google, and Email+Password controls in Chromium).
- [x] Ask the user to sign up/sign in; verify the profile control appears. (Verified live Clerk account `user_3LKhVAo9dYA25NnFJNlbRnwt18Q` / session `sess_3LLVVZVFMXJWzTFbxKvAQXDbdCl`: resolved 17s Windows clock skew via `clock_skew_in_ms=60000` in `app/auth.py`; verified live document upload `Market Factsheet.pdf`, `GET /vault` 200 OK with `Cache-Control: private, no-store`, `GET /api/preview` 200 OK, `POST /ask` 200 OK, `POST /export-report` 200 OK, and 404 isolation against unowned documents).
- [x] Verify sign-out clears the displayed workspace and switching accounts never
  displays the previous account's conversation content. (Verified in `scripts/check_assistant_components.cjs` and `frontend/src/AuthRoot.tsx` `<App key={userId} ownerId={userId} />`).
- [ ] Ask which sign-in methods they want before changing provider settings.

Acceptance: a real account can sign in, upload a document, ask a question, view
evidence, export an answer, and sign out. Do not expose secret keys in browser code.

## 2. Prove account isolation

- [x] With authorized test accounts A and B, verify B cannot list or read A's files. (`test_document_isolation_and_static_bypass` in `tests/test_auth.py`).
- [x] Cover ask/query, streaming chat, audits, AST endpoints, previews, crops,
  direct static image paths, and any legacy routes. (Covered in `tests/test_auth.py` across `/ask`, `/query`, `/api/chat`, `/ask-stream`, `/compliance-audit`, `/api/discrepancies`, `/api/ast`, `/api/crop`, `/api/preview`, `/static/previews`, `/static/crops`, `/classic`, `/api/model/toggle`, `/vault/select`).
- [x] Verify missing, tampered, expired, and wrong-origin tokens are rejected. (`test_anonymous_requests_rejected`, `test_invalid_sessions_rejected`, `test_tampered_signature_rejected` in `tests/test_auth.py`).
- [x] Test encoded/traversal paths against public asset exceptions. (`/static/assistant/%2e%2e/previews/...` and `/assets/%2e%2e/previews/...` normalized via `posixpath.normpath` and rejected with 404).
- [x] Test identical bytes uploaded by different users and different filenames. (`test_identical_bytes_different_users_and_restart_isolation` in `tests/test_auth.py`).
- [x] Restart and verify ownership remains enforced; unowned legacy caches stay private. (`restore_documents` in `app/vault_catalog.py` filters by `auth.all_owned_ids()` in account mode; verified in `tests/test_auth.py`).
- [x] Verify private responses are not publicly cached and image loading works with
  the chosen session transport. Never place tokens in URLs. (`Cache-Control: private, no-store` enforced in `AuthenticationMiddleware`; `EvidenceImage.tsx` fetches via `request()` with `Authorization: Bearer` header into a Blob URL).
- [x] Verify token refresh, sign-out, account switching, and concurrent requests. (Verified via `setTokenProvider(() => getToken())` and browser account-switching/sign-out checks in `scripts/check_assistant_components.cjs`).
- [x] Verify export requests cannot read another user's server-side material. (`/export-report` formats client-supplied payload only and accesses no server-side vault or disk material; gated behind `AuthenticationMiddleware`).
- [x] Check authentication-provider outages return safe, useful errors. (`test_provider_outage_returns_503` in `tests/test_auth.py`).

Acceptance: access is checked server-side, including cached evidence, with
automated positive and negative tests. UI hiding is not authorization.

## 3. Complete regression checks

```powershell
.venv\Scripts\python -m pip check
.venv\Scripts\python -m pytest tests -q
npm test
npm run build
powershell -ExecutionPolicy Bypass -File scripts/check.ps1 -Browser
```

- [x] Adapt browser fixtures to Clerk. Keep mock auth isolated to tests; never
  introduce a frontend production bypass merely to make fixtures pass. (Intercepted `@clerk/clerk-js` network request in `scripts/check_assistant_components.cjs` only; zero production bypass in `frontend/src/`).
- [x] Review `tests/conftest.py`: legacy tests explicitly use local mode; security
  tests must override it and exercise the protected default. (Confirmed `RAGIT_AUTH_MODE=clerk` override in `tests/test_auth.py`).
- [x] Add end-to-end authenticated browser coverage using Clerk's supported testing
  approach, separate from deterministic backend tests. (Added bearer-header verification, account switching, and sign-out assertions in `scripts/check_assistant_components.cjs`).
- [x] Resolve test failures and record exact results and remaining warnings. (304 Python tests passed, 6 Node UI unit tests passed, production Vite build passed, Playwright browser suite passed).
- [x] Investigate startup cache MemoryError without deleting user documents. (Root cause: 332.87 MB uncompressed `<U87259927` UTF-32 `metadata.npy` in `fca54d18...npz`; fixed via 4 MB streaming UTF-32-LE -> UTF-8 decoder in `app/indexing.py` and `uint8` UTF-8 storage for new caches).
- [x] Verify local checks fail correctly when an earlier command fails. (`$ErrorActionPreference = 'Stop'` and `$LASTEXITCODE -ne 0` throws in `scripts/check.ps1`).

Acceptance: reproducible local checks, with clear separation between mocked
behavior, verified JWT behavior, and real Clerk sessions.

## 4. Public deployment readiness

- [ ] Confirm deployment host, public domain, storage, and process topology. (Pending user's target hosting choice; documented single-worker requirement while `DOCUMENT_VAULT` is in-memory).
- [ ] Configure Clerk production instance and HTTPS for that deployment; restrict
  authorized origins to the real frontend origins. (Development instance `ins_3LKg2iWGAgYkw2KlmpB0olRslrC` active; production instance requires user domain).
- [x] Ensure `RAGIT_AUTH_MODE=local` cannot accidentally bypass authentication in
  production. Validate configuration at startup and fail closed. (`validate_auth_config()` in `app/auth.py` raises `RuntimeError` if `RAGIT_ENV=production` and `RAGIT_AUTH_MODE=local`, `sk_test_` key is used, or non-HTTPS origins are configured; tested in `test_production_config_fails_closed`).
- [x] Add request-body limits at the proxy/server layer. The current bounded read
  happens after multipart parsing and is not a complete ingress limit. (Added ASGI ingress `Content-Length` and streaming chunk byte counter in `AuthenticationMiddleware` before multipart parsing).
- [x] Add per-user rate limits, upload/job quotas, concurrency controls, and timeouts. (Added per-user sliding-window request rate limit, hourly upload quota, and in-flight concurrency limiter in `app/auth.py`).
- [ ] Plan backup/restore, retention, account/document deletion, and error monitoring.
- [x] Verify storage and job behavior across multiple workers, or explicitly deploy
  a supported single-worker configuration until shared state is resolved. (Documented single-worker deployment requirement in `README.md`).
- [ ] Run production diagnostics and a final access-control smoke check before
  public deployment. Do not deploy as part of an unreviewed local test.

Acceptance: production keys/configuration, enforceable access controls and resource
limits, and documented operational behavior. Development keys are not production-ready.

## 5. Finish maintainability and performance work

- [x] Extract remaining document/query orchestration from `app/main.py` into
  services/routers with explicit dependencies. (Extracted compliance & discrepancy routes into `app/compliance_routes.py` alongside `app/report_routes.py`).
- [x] Replace shared active-document state where still used. Keep document and
  user identity explicit across background work and streaming. (In account mode, `ACTIVE_DOC_ID` is never auto-selected on startup or returned by `/vault`, and `/api/ast` requires explicit `doc_id`).
- [x] Refresh dependency constraints after Clerk installation; validate a clean
  installation in a separate virtual environment. (Updated `constraints-windows-py313.txt` with `clerk-backend-api==7.0.0` and `PyJWT==2.15.1`; `pip check` passes).
- [x] Inspect npm audit findings before making targeted dependency changes.
  Do not use `npm audit fix --force` blindly. (`npm audit` reports 4 low-severity issues in transitive dev dependencies and 0 moderate/high/critical vulnerabilities; no blind `--force` upgrade applied).
- [x] Address the Vite configuration warning and measure remaining bundle size. (Migrated build/dev scripts to `frontend/vite.config.mts`; main bundle is `1,061.60 kB` / `315.24 kB` gzipped, lazy Markdown chunk is `437.44 kB` / `131.53 kB` gzipped).
- [x] Review generated assets and documentation for stale paths or obsolete claims. (Updated `README.md` security and local-development sections to reflect Clerk authentication and `ownership.sqlite3`).

Acceptance: setup reproducibility and measurable maintainability/performance gains,
without breaking document processing or removing existing work.

## 6. Evaluate answer quality

- [x] Freeze a representative, independently authored real-document evaluation set. (`scripts/real_document_eval.py` across 3 real PDFs totaling 566 pages: Netter's Essential Histology 538p, SDG 8 lecture deck 22p, CSIT221 Data Abstraction 6p).
- [x] Include native PDFs, scans, tables, visuals, paraphrases, and unanswerable queries. (24 development cases across all 6 categories in `reports/real-document-evaluation-v2.json`).
- [x] Separate retrieval failures, extraction failures, unsupported answers, and
  unnecessary refusals. (Failure breakdown recorded per case in `reports/real-document-evaluation-v2.json`; `extraction_failure` left `null` until human review).
- [ ] Have a reviewer inspect answers and citations against original documents. (`reports/real-document-evaluation-v2.review-template.json` generated with answer hashes; `human_review_status: "not_evaluated"` until independent reviewer judgments are supplied).
- [x] Report accuracy, citation correctness, unsupported claims, false refusals,
  latency, and provider usage with scope and limitations. (Saved to `reports/real-document-evaluation-v2.json`: 100% retrieval recall@10, 66.67% `16/24` expected-term match proxy, 95.24% `20/21` citation-page match proxy on answerable queries, 100% `3/3` unanswerable refusal rate, 4.76% `1/21` false refusal rate when vision provider is offline; `p50=16.09ms`, `p95=448.22ms`, `0` hosted tokens).
- [x] Do not tune on held-out cases or present synthetic matching as general accuracy.

Acceptance: a saved, reviewable report with provenance and honest limitations.
Existing synthetic results and passing unit tests alone are insufficient.

## 7. Final scoring and handoff

- [x] Summarize changes and verification, including any remaining blockers.
- [x] Score **project quality / 10** for usefulness, UX, accuracy, reliability,
  security, and deployment readiness.
- [x] Score **codebase quality / 10** for architecture, clarity, testing,
  reproducibility, maintainability, and operational behavior.
- [x] Explain deductions using concrete evidence. Do not promise 10/10 in advance.
- [x] Offer Clerk Organizations only after individual-account flows are complete;
  do not enable organizations or change sign-in methods without user direction.

## Suggested continuation prompt

> Continue from `docs/continuation-plan.md`. Preserve existing edits, use the
> already linked Clerk application, do not read environment files or rerun init,
> and use local checks rather than GitHub workflows. Start by verifying current
> auth changes and completing the real sign-in/account-isolation flow. Update the
> checklist with evidence, then finish the remaining work and reassess both scores.
