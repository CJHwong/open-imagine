---
type: llm
---

Pass if the response says `long-form` is not a supported value for `settings.profile` and names `drama` and `short` as the supported values. It may offer to use `drama` or ask the producer to choose a supported profile. Do not require it to reject every video longer than 60 seconds.

Fail if the response accepts `long-form`, writes `settings.profile: "long-form"`, or presents the former 8-to-20-minute limit or re-engagement windows as supported rules.
