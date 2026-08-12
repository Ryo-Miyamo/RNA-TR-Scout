# RNA-TR-Scout regression fixture v0.3.2

This fixture freezes edge cases discovered during the
ENCSR307SHM 100k-read pilot. It is a software regression set,
not a disease or expansion truth set.

- Cases: 20
- Unique raw reads: 19
- Decision rules: 16
- Missing raw reads: 0

Version 0.3.2 adds two P3 negative controls:

- reverse-orientation bridge compatibility
- plus-orientation mononucleotide homopolymer review

Every future caller revision must preserve the expected
classification and sizing guardrail for these cases, unless the
fixture version is deliberately updated.
