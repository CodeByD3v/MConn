# MConn production-readiness checklist

This checklist records the work needed before MConn is offered to real users.
It is intentionally evidence-based: a checked item must link to a test, runbook,
or demonstrated release artifact. It does not change the current v1 protocol.

## Tier 0 — Trust and operating safety

- [x] Bound unauthenticated JSON requests to 16 KiB, including requests without
  `Content-Length`; regression tests cover both paths.
- [ ] Add an agreed per-IP rate-limit policy for pairing claim and other
  unauthenticated entry points. This is deferred pending a product decision.
- [ ] Support private-interface rebinding and mDNS re-advertisement after DHCP,
  Wi-Fi, or Tailscale address changes. Never bind public interfaces.
- [ ] Decide and document a certificate-rotation strategy that preserves the
  pinning invariant while allowing address/SAN changes.
- [ ] Add rolling, durable receiver logs and an audit trail for pairings,
  revocations, transfer state changes, and receipts. Do not log contents, keys,
  tokens, or signatures.
- [ ] Protect the local management surface for shared Windows accounts and use
  Windows-appropriate private-key access controls.
- [ ] Add Windows CI and exercise locked files, long paths, reserved names,
  OneDrive-style inboxes, and upload-idle timeout handling.
- [ ] Compile and run Android unit tests on a real Android toolchain.

## Tier 1 — Ship readiness

- [ ] Verify current Android platform requirements before changing target SDK or
  foreground-service behavior; add Wi-Fi-network binding where device testing
  shows that default routing can choose cellular for offline-LAN transfers.
- [ ] Add Room migrations and export schemas; queue data must survive app updates.
- [ ] Implement the delayed private-copy cleanup worker and test its retention rule.
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
| Certificate SAN handling | `windows-receiver/tests/test_tls.py` |
| Atomic upload baseline | Receiver unit and integration-style tests; full local suite still needs a Windows test-host fix |
