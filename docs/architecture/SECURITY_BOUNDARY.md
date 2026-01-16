# Security Boundary Notes

## Capability Tokens

- Capability token signatures are computed over RFC 8785 canonical JSON bytes.
- Verification rejects non-canonical payload encodings (e.g., reordered keys or whitespace changes).
- This ensures deterministic signing and prevents signature confusion across equivalent payloads.
