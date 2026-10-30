# RagIT operations and recovery

Status: deployment rehearsal remains incomplete. The user has no production host or domain yet. Do not expose the local development server publicly or describe live HTTPS/sign-in as verified.

## Deployment contract

Use one application worker and one writable storage volume. Admission, background jobs, and the resident vault are process-local; multiple workers are unsupported. Compose binds port 8000 to loopback. A future reverse proxy must terminate HTTPS and forward to that listener. Set the exact HTTPS origin in `CLERK_AUTHORIZED_PARTIES`, use the matching live Clerk application and publishable key, and store secret values outside version control. Rebuild the frontend when its publishable key changes.

`/health` indicates process liveness. `/ready` additionally checks startup model loading, storage probes and catalog recovery; in production it requires configured inference credentials. It does not prove external inference or Clerk availability. Verify sign-in and a grounded answer separately before release.

Current Compose limits are 8 GiB RAM, four CPUs, 256 processes, and rotated logs. These are configuration limits, not validated capacity guarantees. Monitor disk usage, failed jobs, readiness, memory, and response latency. Keep free storage for uploads, extraction, caches and backups. Application-wide disk quotas are still outstanding.

Upload admission checks free space on the source, index, preview, and crop locations. It requires a 512 MiB reserve plus twice the input size by default; configure the reserve with `RAGIT_MIN_STORAGE_FREE_BYTES`. A 507 response indicates storage or resident-vault capacity is exhausted. This check cannot prevent other applications from consuming disk space after admission, and does not bound all derived artifacts. Enforce a storage-volume quota and monitor headroom on the deployment host before release.

## Cold backup

Schedule a maintenance window. Stop new uploads and wait for existing jobs to finish or cancel cooperatively. Stop only RagIT, then confirm its container is stopped before copying. Do not take a filesystem copy while ingestion or background indexing is writing.

Back up the entire `/var/lib/ragit` tree: `data` includes source documents, ingestion/vector caches, ownership, catalog and job databases; `previews` and `crops` retain evidence images. Copy all SQLite files and sidecars together. Preserve the deployed image digest, source revision and non-secret configuration alongside the backup; keep credentials separately in protected storage.

Docker supports copying from a stopped container using `docker cp`. See [Docker's copy reference](https://docs.docker.com/reference/cli/docker/container/cp/) and [volume backup guidance](https://docs.docker.com/engine/storage/volumes/). Copy into a fresh dated destination, record file checksums, protect backup access, and keep an off-machine copy. Resume RagIT only after the copy completes.

## Restore rehearsal and rollback

Restore into a new empty volume, never over the only working copy. Mount it at `/var/lib/ragit`, restore the complete tree, and ensure UID/GID 10001 can read and write it. Start the same image and configuration against that volume on an isolated listener. Keep the original volume intact for rollback.

Verify readiness, catalog recovery, document/page counts, original evidence previews, and ownership with two accounts. Confirm one account cannot access the other's evidence. Exercise a new upload, deletion, restart, and a cited answer. An old cache may require reindexing after a model or pipeline change; keep the original source files. Record unavailable recovery entries instead of treating a partially restored vault as complete.

The isolated local filesystem rehearsal passed (`reports/backup-restore.json`): 16 restored files matched checksums, a fresh process recovered the catalog and PDF evidence, two signed fixture users remained isolated, and new upload/deletion worked. Reproduce with `python -m scripts.check_backup_restore --input PATH_TO_PDF`. The script uses disposable directories and terminates the source process before copying. It does not validate Docker volume copying or live Clerk/HTTPS.

Production release still requires a deployment-volume rehearsal, agreed recovery objectives and retention, a host/domain, real HTTPS and Clerk verification, and the remaining checks in `production-readiness.md`.
