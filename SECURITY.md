# Security

This project is experimental alpha software. Only the current alpha is intended for investigation and fixes; there is no support or response-time guarantee.

## Reporting

If you discover a vulnerability, use [GitHub's private vulnerability reporting feature](https://github.com/milan483/fullscreen-nightlight/security/advisories/new). Otherwise contact the repository owner privately and arrange a secure reporting channel before sharing sensitive details. Do not publish credentials, private logs, working exploits or sensitive host information in a public issue. Include the affected version/commit, prerequisites, impact, a minimal safe reproduction and any suggested mitigation.

## Boundaries

The extension runs as the desktop user. It does not need root, access the network, modify Night Light configuration or intentionally release other applications' inhibitors. The helper validates the current KWin bus owner and uses its own dedicated connection. It cannot protect against arbitrary hostile code already running as the same user. Installation refuses unsafe file/path ownership or permissions and preserves unrelated files; cooperative locking and filesystem assumptions are described in [installer safety](docs/INSTALLER.md).

Obtain release files from a trusted channel and verify SHA256SUMS. A checksum is not a signature or proof of publisher identity. CI does not constitute a comprehensive vulnerability audit. Disable and remove the extension if you suspect a problem; never reset other applications' Night Light inhibitors.
