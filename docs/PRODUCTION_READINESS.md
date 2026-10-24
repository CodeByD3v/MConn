# MConn production-readiness checklist

This checklist records the work needed before MConn is offered to real users.
It is intentionally evidence-based: a checked item must link to a test, runbook,
or demonstrated release artifact. It does not change the current v1 protocol.

## Tier 0 — Trust and operating safety

- [x] Bound unauthenticated JSON requests to 16 KiB, including requests without
  `Content-Length`; regression tests cover both paths.
- [x] Limit pairing claims to 10 attempts per source IP in a rolling 60-second
  window. This applies before the claim body is read.
- [ ] Support private-interface rebinding and mDNS re-advertisement after DHCP,
  Wi-Fi, or Tailscale address changes. Never bind public interfaces.
- [ ] Decide and document a certificate-rotation strategy that preserves the
  pinning invariant while allowing address/SAN changes.
- [~] Add rolling, durable receiver logs. `receiver.log` now rotates under the
  receiver data directory; pairing, revocation, and receipt audit events remain.
- [ ] Protect the local management surface for shared Windows accounts and use
  Windows-appropriate private-key access controls.
- [~] Add Windows CI and exercise locked files, long paths, reserved names,
  OneDrive-style inboxes, and upload-idle timeout handling.
- [ ] Compile and run Android unit tests on a real Android toolchain.

## Tier 1 — Ship readiness

- [~] Verify current Android platform requirements before changing target SDK or
  foreground-service behavior. At target SDK 34, the Android 17 local-network
  permission is not yet required; Android 15 `dataSync` services have a six-hour
  24-hour budget. Add Wi-Fi-network binding where device testing shows that
  default routing can choose cellular for offline-LAN transfers.
- [x] Add Room schema export and a v1→v2 migration for cleanup state; queue data
  will not be wiped by this schema update.
- [~] Implement delayed private-copy cleanup after a stored receipt. Device and
  migration tests remain required before this can be marked fully evidenced.
- [ ] Add a receiver installer/bundled executable, update process, code-signing
  plan, tray/status UI, and robust auto-start behavior.
- [ ] Add a catch-all API error mapper that preserves the documented error shape.
- [ ] Populate failure-recovery tests with receiver restart, interrupted upload,
  lost receipt, and large-file scenarios.
- [ ] Verify a real Android Keystore-produced signature against the receiver.
- [ ] Complete Android release basics: QR scanner, onboarding, settings,
  notifications, R8/release signing, privacy documentation, and crash handling.

## Tier 2 — Repository and release hygiene

- [ ] Add `LICENSE`, `SECURITY.md`, and `CONTRIBUTING.md`.
- [ ] Add dependency lockfiles, dependency auditing, Dependabot, and CodeQL.
- [ ] Add Python type checking and a documented threat model, troubleshooting
  runbook, release/versioning process, and protocol compatibility policy.
- [ ] Define database/nonce retention, health checks, and privacy-safe metrics.

## Evidence log

| Item | Evidence |
| --- | --- |
| Pre-auth JSON bound | `windows-receiver/tests/test_request_limits.py` |
| Pairing claim rate limit | `mconn_receiver/api/rate_limit.py` |
| Certificate SAN handling | `windows-receiver/tests/test_tls.py` |
| Atomic upload baseline | Receiver unit and integration-style tests; full local suite still needs a Windows test-host fix |
