# RNA-TR-Scout hardware profile v0.1.0

Date: 2026-08-17

## Status

**TESTED / RECOMMENDED PROFILE DOCUMENTED — EMPIRICAL MINIMUM NOT YET ESTABLISHED**

This document records what has actually been tested and what is currently recommended for release-scale use. It intentionally does not turn untested lower-resource configurations into a claimed minimum.

## Tested hosts

### Primary validated host

- Linux x86-64
- 24 logical CPUs
- approximately 128 GB available RAM during Stage16Z planning
- Tier3 100k automatic Core profile: `12 shards / 3 concurrent Core units / 2 caller workers per unit`
- Tier3 FASTQ auto-mapping → final: exact five-table parity PASS
- full 5.31M BAM-to-final development run previously completed in approximately 60.04 minutes with the validated production path

### Independent second host (`deeplearningboxii`)

- Linux x86-64
- 36 logical CPUs
- 134,726,070,272 bytes total RAM
- 129,854,144,512 bytes available RAM during Stage16AA planning
- Tier2 automatic Core profile: `1 shard / 1 concurrent Core unit / 2 caller workers per unit`
- fresh clone + fresh environment + network resource installation: PASS
- Tier2 exact five-table scientific parity: PASS
- second-resume no-op: PASS

## Recommended release-scale profile

For a researcher planning to run approximately five-million-read ONT-cDNA datasets with the current restartable workflow, the current **recommended** profile is:

- Linux x86-64
- approximately 24 or more logical CPU threads
- approximately 128 GB RAM
- fast local SSD/NVMe working storage
- enough free working space for large restartable intermediate state

This recommendation is based on the actual primary development/validation host and the independent second-machine validation. It is a practical release-engineering recommendation, not a biological requirement.

## Smaller runs and mapping

Human-genome ONT-cDNA mapping has been observed in the mid-teens of GB of RAM during development. For setup, mapping, and smaller test runs, 32 GB RAM remains a reasonable practical target. A 16 GB system may be tight when mapping a human genome or when other processes are active.

That statement should **not** be interpreted as evidence that 32 GB is sufficient for the current five-million-read release-scale workflow.

## Automatic Core scheduling

`rnatr_resource_policy_v0.1.0` detects CPU, currently available RAM, selected tmp directory, and free space. It chooses conservative Core concurrency when explicit worker values are omitted.

The planner uses a 6 GiB per active-Core-unit planning allowance and limits automatic concurrency to 70% of the selected RAM budget. This is a scheduling guard, not a measured per-unit peak-memory law.

Manual controls remain available for advanced users, and supplied overrides are recorded in run provenance.

## What is not yet established

The following are **not** claimed as empirical minima:

- minimum CPU count for all supported run sizes;
- minimum RAM for the five-million-read workflow;
- minimum free disk space for a five-million-read workflow;
- performance guarantees on slow disks or network filesystems.

The full-scale peak-disk benchmark remains open. The current audited full-scale restart state contained approximately 140 GB of checkpoint/work files at one stage, but that is not a measured peak.

## G30 adjudication

G30 requested empirical minimum/recommended/tested hardware profiles.

Current status:

- **tested profile:** established;
- **recommended profile:** established for the currently validated release-scale Linux x86-64 workflow;
- **empirical minimum profile:** not established and must not be invented from the existing evidence.

Accordingly G30 should be recorded as **PASS_WITH_SCOPE / minimum-unresolved-nonblocking**, rather than as either a false full PASS or a blanket OPEN that ignores the tested and recommended evidence already obtained.
