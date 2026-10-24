# MConn — Roadmap

> Build order, deliverables and exit criteria. Behavioural detail lives in [DESIGN.md](DESIGN.md); rationale in [ARCHITECTURE.md](ARCHITECTURE.md).

**Principle:** build the local-first path end to end before adding anything remote. A phase is done only when its exit criterion has been demonstrated, not when the code is merged.

## Overview

| Phase | Name | Outcome |
| --- | --- | --- |
| 0 | Foundations | Decisions locked, repo scaffolded, protocol contract written |
| 1 | Local transfer MVP | A shared file arrives intact over Wi-Fi |
| 2 | Reliable deferred delivery | Offline PC, retries and duplicates handled |
| 3 | Remote connectivity | Delivery across different networks via a private network |
| 4 | Polish and harden | Resume, revocation, UX and security hardening |
| 5+ | Later | Integrated remote transport and other extensions |

## Phase 0 — Foundations

**Deliverables**

- [ ] Resolve open questions in ARCHITECTURE.md §11 (minimum Android version, admin UI approach, default limits).
- [ ] Write `protocol/transfer-contracts.md` from DESIGN.md §5, including example requests and error codes.
- [ ] Scaffold the monorepo with empty modules, formatter and linter configs, and CI that builds both sides.
- [ ] Prove the two riskiest assumptions with throwaway spikes:
  - [ ] Android pins a self-signed certificate by fingerprint and uploads to a local FastAPI server.
  - [ ] The Windows receiver is reachable from the phone through the firewall rule and (separately) through mDNS.

**Exit criterion:** the spikes pass on real devices, and the contract document is agreed.

## Phase 1 — Local transfer MVP

Build the Windows receiver and Android sender. Pair via QR, choose a destination directory, transfer over the same Wi-Fi.

**Windows**

- [ ] Config loading, SQLite and migrations.
- [ ] TLS certificate generation and fingerprint exposure.
- [ ] Pairing session, QR display, approve/deny, device registration.
- [ ] Request signature verification.
- [ ] `POST /v1/transfers` and single-request `PUT /v1/transfers/{id}/content`.
- [ ] Staging, size and SHA-256 verification, filename sanitising, conflict suffixing, atomic commit, receipt.
- [ ] Management page: start pairing, list and revoke devices.

**Android**

- [ ] Share Target for single and multiple files.
- [ ] Copy to private storage with streaming SHA-256.
- [ ] QR pairing, keypair in Keystore, certificate pinning.
- [ ] Manual address entry fallback.
- [ ] Basic transfer list with state and errors.
- [ ] Direct upload (no background retry yet).

**Exit criterion:** a shared ZIP and a Python file from the Share menu arrive byte-identical (hash-verified) in the selected folder, with internet disconnected.

## Phase 2 — Reliable deferred delivery

**Deliverables**

- [ ] Room queue as the single source of truth; reboot and app-update survival.
- [ ] WorkManager workers with network constraint, exponential backoff, and app-open or network-change retry triggers.
- [ ] Foreground or expedited execution for large uploads.
- [ ] State machine implemented exactly as in DESIGN.md §7.
- [ ] Idempotency: PC returns the existing receipt for a committed transfer ID.
- [ ] Receipt handling and delayed cleanup of the private copy.
- [ ] Receiver start at logon via Task Scheduler, with install script.
- [ ] Startup reconciliation of staging files.

**Exit criterion:** send a file, shut the PC down, power it on later, and the file arrives without any manual resend.

## Phase 3 — Remote connectivity

**Deliverables**

- [ ] Document Tailscale setup for PC and phone, including the single-VPN-slot caveat on Android.
- [ ] Add private-network hosts to pairing payload and the connection manager's host order.
- [ ] Bind receiver to LAN and private-network interfaces only; scope firewall rule accordingly.
- [ ] Cellular-data setting and remote-path UI indicator.
- [ ] Verify behaviour over a direct connection and over Tailscale's relayed path.
- [ ] Confirm the local path still works with no internet.

**Exit criterion:** a file is delivered between two different networks with no cloud file storage involved, and local delivery continues to work offline.

## Phase 4 — Polish and harden

**Deliverables**

- [ ] Chunked, resumable uploads using `Upload-Offset` (8 MiB chunks).
- [ ] Interrupted-upload recovery tests (network cut, PC restart, app kill).
- [ ] Device revocation end to end, including phone-side `REJECTED` display.
- [ ] Replay protection tests (stale timestamp, reused nonce).
- [ ] Disk-space, size-limit and hostile-filename handling.
- [ ] Progress notifications, clear error messages, diagnostics export.
- [ ] Log rotation and basic metrics in logs.
- [ ] Decide between Task Scheduler and a Windows Service.

**Exit criterion:** interrupted transfers resume safely, untrusted requests are rejected, and the user always sees a clear status.

## Later (not scheduled)

- Integrated remote transport (WebRTC data channels, signalling, TURN) to remove the Tailscale dependency.
- Windows tray app and installer.
- Optional per-device inbox subfolders.
- Windows → phone direction.
- Multiple PCs per phone.
- Store distribution of the Android app.

## Acceptance test matrix (first release)

| # | Test | Phase |
| --- | --- | --- |
| 1 | Small file over Wi-Fi with internet disconnected | 1 |
| 2 | Files shared from other Android apps via the Share menu | 1 |
| 3 | Large ZIP arrives with matching SHA-256 | 1 |
| 4 | Unpaired device cannot upload | 1 |
| 5 | Send while PC is off; delivered after PC starts | 2 |
| 6 | Same transfer sent twice creates one file | 2 |
| 7 | Network disconnected mid-upload; recovery without corruption | 2 / 4 |
| 8 | Name collision creates a suffixed copy, never overwrites | 2 |
| 9 | Remote delivery across different networks | 3 |
| 10 | Relayed remote path does not persist file contents | 3 |
| 11 | Revoked phone can no longer send | 4 |
| 12 | Stale or replayed request is rejected | 4 |

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Android background limits delay or kill uploads | Late delivery | WorkManager plus foreground/expedited work for large files; set expectations in UI. |
| mDNS unreliable on some Wi-Fi | Phone cannot find PC | Manual address fallback and remembered host in MVP. |
| Windows firewall blocks receiver | Total failure on first run | Setup script adds a scoped rule; spike in Phase 0. |
| Certificate pinning bugs | Pairing or uploads fail | Spike early; test cert regeneration path. |
| Tailscale conflicts with another VPN on Android | Remote path unusable | Document; revisit integrated transport later. |
| Receiver only runs while the user is logged in | Missed deliveries while logged out | Accept for v1; reconsider Windows Service in Phase 4. |
| Scope creep into sync features | Delays core goal | Non-goals listed in ARCHITECTURE.md §1. |
