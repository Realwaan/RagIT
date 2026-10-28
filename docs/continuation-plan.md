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

- [ ] Inspect current auth changes and confirm no pending edits conflict.
- [ ] Choose a local URL/port and explicitly allow that exact frontend origin.
  Prefer an already allowed port, or add `http://127.0.0.1:8001` for this local run.
- [ ] Run `npx -y clerk@latest doctor`; address actionable diagnostics.
- [ ] Start FastAPI and open the built app.
- [ ] Confirm sign-in and sign-up controls render and failures are understandable.
- [ ] Ask the user to sign up/sign in; verify the profile control appears.
- [ ] Verify sign-out clears the displayed workspace and switching accounts never
  displays the previous account's conversation content.
- [ ] Ask which sign-in methods they want before changing provider settings.

Acceptance: a real account can sign in, upload a document, ask a question, view
evidence, export an answer, and sign out. Do not expose secret keys in browser code.

## 2. Prove account isolation

- [ ] With authorized test accounts A and B, verify B cannot list or read A's files.
- [ ] Cover ask/query, streaming chat, audits, AST endpoints, previews, crops,
  direct static image paths, and any legacy routes.
- [ ] Verify missing, tampered, expired, and wrong-origin tokens are rejected.
- [ ] Test encoded/traversal paths against public asset exceptions.
- [ ] Test identical bytes uploaded by different users and different filenames.
- [ ] Restart and verify ownership remains enforced; unowned legacy caches stay private.
- [ ] Verify private responses are not publicly cached and image loading works with
  the chosen session transport. Never place tokens in URLs.
- [ ] Verify token refresh, sign-out, account switching, and concurrent requests.
- [ ] Verify export requests cannot read another user's server-side material.
- [ ] Check authentication-provider outages return safe, useful errors.

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

- [ ] Adapt browser fixtures to Clerk. Keep mock auth isolated to tests; never
  introduce a frontend production bypass merely to make fixtures pass.
- [ ] Review `tests/conftest.py`: legacy tests explicitly use local mode; security
  tests must override it and exercise the protected default.
- [ ] Add end-to-end authenticated browser coverage using Clerk's supported testing
  approach, separate from deterministic backend tests.
- [ ] Resolve test failures and record exact results and remaining warnings.
- [ ] Investigate startup cache MemoryError without deleting user documents.
- [ ] Verify local checks fail correctly when an earlier command fails.

Acceptance: reproducible local checks, with clear separation between mocked
behavior, verified JWT behavior, and real Clerk sessions.

## 4. Public deployment readiness

- [ ] Confirm deployment host, public domain, storage, and process topology.
- [ ] Configure Clerk production instance and HTTPS for that deployment; restrict
  authorized origins to the real frontend origins.
- [ ] Ensure `RAGIT_AUTH_MODE=local` cannot accidentally bypass authentication in
  production. Validate configuration at startup and fail closed.
- [ ] Add request-body limits at the proxy/server layer. The current bounded read
  happens after multipart parsing and is not a complete ingress limit.
- [ ] Add per-user rate limits, upload/job quotas, concurrency controls, and timeouts.
- [ ] Plan backup/restore, retention, account/document deletion, and error monitoring.
- [ ] Verify storage and job behavior across multiple workers, or explicitly deploy
  a supported single-worker configuration until shared state is resolved.
- [ ] Run production diagnostics and a final access-control smoke check before
  public deployment. Do not deploy as part of an unreviewed local test.

Acceptance: production keys/configuration, enforceable access controls and resource
limits, and documented operational behavior. Development keys are not production-ready.

## 5. Finish maintainability and performance work

- [ ] Extract remaining document/query orchestration from `app/main.py` into
  services/routers with explicit dependencies.
- [ ] Replace shared active-document state where still used. Keep document and
  user identity explicit across background work and streaming.
- [ ] Refresh dependency constraints after Clerk installation; validate a clean
  installation in a separate virtual environment.
- [ ] Inspect npm audit findings before making targeted dependency changes.
  Do not use `npm audit fix --force` blindly.
- [ ] Address the Vite configuration warning and measure remaining bundle size.
- [ ] Review generated assets and documentation for stale paths or obsolete claims.

Acceptance: setup reproducibility and measurable maintainability/performance gains,
without breaking document processing or removing existing work.

## 6. Evaluate answer quality

- [ ] Freeze a representative, independently authored real-document evaluation set.
- [ ] Include native PDFs, scans, tables, visuals, paraphrases, and unanswerable queries.
- [ ] Separate retrieval failures, extraction failures, unsupported answers, and
  unnecessary refusals.
- [ ] Have a reviewer inspect answers and citations against original documents.
- [ ] Report accuracy, citation correctness, unsupported claims, false refusals,
  latency, and provider usage with scope and limitations.
- [ ] Do not tune on held-out cases or present synthetic matching as general accuracy.

Acceptance: a saved, reviewable report with provenance and honest limitations.
Existing synthetic results and passing unit tests alone are insufficient.

## 7. Final scoring and handoff

- [ ] Summarize changes and verification, including any remaining blockers.
- [ ] Score **project quality / 10** for usefulness, UX, accuracy, reliability,
  security, and deployment readiness.
- [ ] Score **codebase quality / 10** for architecture, clarity, testing,
  reproducibility, maintainability, and operational behavior.
- [ ] Explain deductions using concrete evidence. Do not promise 10/10 in advance.
- [ ] Offer Clerk Organizations only after individual-account flows are complete;
  do not enable organizations or change sign-in methods without user direction.

## Suggested continuation prompt

> Continue from `docs/continuation-plan.md`. Preserve existing edits, use the
> already linked Clerk application, do not read environment files or rerun init,
> and use local checks rather than GitHub workflows. Start by verifying current
> auth changes and completing the real sign-in/account-isolation flow. Update the
> checklist with evidence, then finish the remaining work and reassess both scores.
