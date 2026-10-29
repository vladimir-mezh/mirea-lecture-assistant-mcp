# Windows distribution change, 0.2.1

## Observation

On 29 October 2026, Windows Defender blocked the installed 0.2.0 adapter as
`Trojan:Win32/Bearfoos.A!ml`, including attempts to read its SHA-256. It remained
blocked after signature updates. The installed manifest named the expected hash
`752b53bc149a3905cbdbec520b89ee8cff47215e1fdfa624c32f3a7add3ceabf`, but the blocked
file's current contents could not be independently verified. We do not assert
that the old detection was a confirmed false positive.

The 0.2.0 source at `3dfcc1daf34d9eb84f039bf9e8f936715ad9bac0` was inspected. The
adapter exposes the app's bounded local API; it has no arbitrary shell, file,
credential, QR-submission or lecture-chat tool. Its Windows delivery used two
PyInstaller onefile executables, with a Python payload unpacked at startup.

## Replacement

The Windows distribution now uses normal native executables built with pinned
Go 1.27.3 and the official MCP Go SDK 1.8.0. No UPX, obfuscation, self-extracting
bootloader, embedded Python runtime or unpacked `_MEI` folder is used. Python
remains available for source development and as the reference MCP contract.

The same 13 tool definitions, their schemas, the two prompts, server instructions
and app protocol 1 are preserved. A generated, compiled-in contract and SDK
interoperability tests check this against the Python implementation. An omitted
optional prompt argument list and an empty list are normalized as equivalent.

The archive still has the same five files expected by existing Lecture Assistant
installers. The launcher verifies the installed adapter's SHA-256 before starting
it. Pairing files are reread after app restart. HTTP traffic is restricted to
`127.0.0.1`, without environment proxies or redirect following. Errors do not
include pairing keys, private paths or low-level request details. Application-side
permissions remain authoritative. No authentication, attendance or chat action is
performed by the native compatibility checks on the real profile.

## Validation

- Native unit tests and Go dependency checksum verification passed.
- 13 Python/SDK integration tests passed, including actual stdio sessions,
  direct/launcher access to a synthetic app API, denied and allowed fixture writes,
  wait defaults/bounds, tool/prompt parity, update during an existing connection,
  old-version cleanup and forced exit without runtime extraction.
- A real-profile read-only `check_health` call reported `verdict=ok` through the
  native 0.2.1 adapter. No repair or settings command was called on that profile.
- With real-time protection enabled and Defender signatures 1.463.22.0, a custom
  scan and subsequent native launches produced no new detection for the candidate.

Release acceptance also requires the Windows CI result, public archive checksum,
and a scan/stdio check of the exact released artifacts before local installation.
The running Lecture Assistant is kept in place; this is an independent MCP update.

No Defender exclusion, allow rule, disabled protection or quarantine restoration
is required. No sample was submitted externally. Old detection records are not
erased. A clean result with current definitions cannot guarantee how all future
antivirus models will classify an unsigned application.

References: [official MCP Go SDK](https://github.com/modelcontextprotocol/go-sdk),
[Go downloads and checksums](https://go.dev/dl/),
[Microsoft file analysis](https://www.microsoft.com/en-us/wdsi/filesubmission).
