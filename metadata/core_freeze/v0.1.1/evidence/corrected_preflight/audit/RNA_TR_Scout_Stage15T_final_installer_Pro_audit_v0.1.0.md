# RNA-TR-Scout Stage15T final installer Pro audit v0.1.0

## Decision

`PASS_CORRECTED_PAYLOAD_REQUIRED_BEFORE_MUTATION`

The uploaded v0.1.2 preflight bundle is internally intact and its live-project prestate guards passed, but its proposed install payload is not byte-identical to the owner-approved artifacts. The installer must not use the rewritten payload.

## Material discrepancies detected

- owner-approved Packet SHA: `af5c437f3e419f58c4daeaa865777751410bd006cc65ca02e40c78ed4d87aa68`
- rewritten preflight Packet SHA: `89b145fb3216657b99bb19e6ac7438b3abfceda696aac46dfa67fff0a6e0abb2`
- owner-approved release gates SHA: `ba57781d12bf8638a95da94cd73bb845a7e35e0123fe7690b4559a09d5deed3f`
- rewritten preflight release gates SHA: `80f823d922b5f17254352f6f4d267d527026f7649067bfecdb7d6550cc3aa461`
- owner-approved CTC v0.1.2 source was omitted and replaced by an unapproved scope addendum.

The rewritten files contain substantive status/evidence wording changes, including G24/G31/G32-G34 and a restructured Freeze Packet. They are rejected as installer payload even though their general direction is compatible.

## Corrective rule

1. Preserve the exact owner-approved Packet and CTC sources byte-for-byte.
2. Build canonical registered documents as transparent registration headers plus the exact approved source bodies.
3. Install the exact owner-approved release-gate v0.3.4 table without textual rewriting.
4. Retain the audited Stage15R and Stage15S technical contracts from preflight only where they do not replace owner-approved content.
5. Simulate SSOT changes on a copy and require the current pipeline export to remain byte-identical.
6. Perform no project mutation in this corrected preflight.

No Core code, schema, scientific output, active pipeline or Downloads cleanup change is authorized by this audit.
