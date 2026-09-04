# Secret-scanning alert #1 — resolved as false positive (evidence)

**Date:** 2026-09-04 · **Alert:** `twilio_account_sid` · **Resolution:** `false_positive`

## What happened

GitHub Secret Scanning flagged `vendor/source_snapshot/samples/Apex/TwilioAPI.cls:94`
in commit 9f46b0a4:

```
twilioCfg.AccountSid__c = 'ACba8bc05eacf94afdae398e642c9cc32d'; // dummy sid
twilioCfg.AuthToken__c = '12345678901234567890123456789012';    // dummy token
```

The strings are annotated in the source itself as **dummy** values, inside a
test fixture of the linguist corpus.

## Byte-exact provenance audit

| Artifact | SHA-256 |
|---|---|
| upstream raw @ befd3af35e70150b76458085208435eef9286bb3 | F572BFB373F9928A6B54A5709E454179AFA041C5A342C15821D2F434A549262B |
| local snapshot file | F572BFB373F9928A6B54A5709E454179AFA041C5A342C15821D2F434A549262B |

Identical. The flagged bytes originate verbatim in `github-linguist/linguist`.

## Verdict

FALSE_POSITIVE — test credential by construction. Nothing to rotate (nothing of
ours), no history rewrite (the value is public upstream and dummy).

Moral: MALBOGUISTIC transporta Linguist tan literalmente que hasta se traga sus
strings con forma de secreto. 😄
