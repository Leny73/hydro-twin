# HydroTwin — Pitch Flow & Architecture

> **One-line pitch:** _"NIMH delivers the warning. bg-ALERT delivers the alarm. **HydroTwin delivers the decision.**"_
>
> Real-time Copernicus Sentinel EO + OpenMeteo weather → AWS Bedrock (Claude 3 Sonnet) → email + Discord alerts on every status transition, for 32 Bulgarian regions, every 30 minutes.

---

## 1. High-Level Architecture

Browser-only frontend on Vercel, 8 Lambdas behind API Gateway, 3 DynamoDB tables, Bedrock for AI, plus Sentinel Hub + OpenMeteo + Brevo + Discord on the outside.

![diagram](https://mermaid.ink/img/Zmxvd2NoYXJ0IFRCCiAgICBVc2VyWyJNYXlvciAvIENpdmlsIFByb3RlY3Rpb24iXQogICAgQnJvd3NlclsiQnJvd3Nlcjxici8-VmVyY2VsIMK3IFZpdGUgKyBSZWFjdDxici8-TWFwYm94Il0KCiAgICBzdWJncmFwaCBBV1NbIkFXUyBDbG91ZCJdCiAgICAgICAgQVBJR1dbIkFQSSBHYXRld2F5Il0KICAgICAgICBzdWJncmFwaCBMYW1iZGFzWyJMYW1iZGFzICg4KSJdCiAgICAgICAgICAgIEwxWyIvYXNzZXNzIl0KICAgICAgICAgICAgTDJbImNyb24gMzAgbWluIl0KICAgICAgICAgICAgTDNbIi9zdWJzY3JpYmUiXQogICAgICAgICAgICBMNFsiL3Vuc3Vic2NyaWJlIl0KICAgICAgICAgICAgTDVbIi9zdGF0dXMiXQogICAgICAgICAgICBMNlsiL2NoYXQtYWxlcnQiXQogICAgICAgICAgICBMN1siL2RhbXMiXQogICAgICAgICAgICBMOFsiL3JlcG9ydHMiXQogICAgICAgIGVuZAogICAgICAgIHN1YmdyYXBoIEREQlsiRHluYW1vREIiXQogICAgICAgICAgICBUMVsoIkh5ZHJvVHdpblN0YXR1cyIpXQogICAgICAgICAgICBUMlsoIkh5ZHJvVHdpblN1YnNjcmlwdGlvbnMiKV0KICAgICAgICAgICAgVDNbKCJIeWRyb1R3aW5SZXBvcnRzIildCiAgICAgICAgZW5kCiAgICAgICAgQmVkcm9ja1siQVdTIEJlZHJvY2s8YnIvPkNsYXVkZSAzIFNvbm5ldCJdCiAgICBlbmQKCiAgICBzdWJncmFwaCBFeHRlcm5hbFsiRXh0ZXJuYWwiXQogICAgICAgIFNIWyJTZW50aW5lbCBIdWI8YnIvPk5EVkkgwrcgTkRXSSJdCiAgICAgICAgT01bIk9wZW5NZXRlbzxici8-cHJlY2lwIMK3IHNvaWwgwrcgdGVtcCJdCiAgICAgICAgQnJldm9bIkJyZXZvIEVtYWlsIl0KICAgICAgICBEaXNjb3JkWyJEaXNjb3JkIFdlYmhvb2tzIl0KICAgIGVuZAoKICAgIFVzZXIgLS0-IEJyb3dzZXIKICAgIEJyb3dzZXIgPC0tPnxIVFRQUyArIEpTT058IEFQSUdXCiAgICBBUElHVyAtLT4gTGFtYmRhcwoKICAgIEwxIC0tPiBTSAogICAgTDEgLS0-IE9NCiAgICBMMSAtLT4gQmVkcm9jawogICAgTDEgLS0-IFQxCiAgICBMMiAtLT4gU0gKICAgIEwyIC0tPiBPTQogICAgTDIgLS0-IEJlZHJvY2sKICAgIEwyIC0tPiBUMQogICAgTDIgLS0-IFQyCiAgICBMMiAtLT4gQnJldm8KICAgIEwyIC0tPiBEaXNjb3JkCiAgICBMMyAtLT4gVDIKICAgIEwzIC0tPiBCcmV2bwogICAgTDMgLS0-IERpc2NvcmQKICAgIEw0IC0tPiBUMgogICAgTDUgLS0-IFQxCiAgICBMNiAtLT4gQmVkcm9jawogICAgTDcgLS0-IFNICiAgICBMNyAtLT4gRGlzY29yZAogICAgTDggLS0-IFQz?theme=dark&bgColor=0f172a)

---

## 2. The 8 Lambdas

| # | Lambda | Trigger | What it does |
|---|---|---|---|
| 1 | `/assess` | API GW POST | Pulls live EO + weather, calls Claude, returns structured risk assessment |
| 2 | **cron** | EventBridge `rate(30 min)` | Re-runs `/assess` for **all 32 regions**, writes snapshots, fires alerts on **transitions only** |
| 3 | `/subscribe` | API GW POST | Saves to DDB, sends welcome email + Discord embed |
| 4 | `/unsubscribe` | API GW GET/POST | HMAC-signed one-click, idempotent delete |
| 5 | `/status` | API GW GET | Pre-computed snapshots for instant map paint |
| 6 | `/chat-alert` | API GW POST | "HydroSentry" assistant — Q&A scoped to active alert |
| 7 | `/dams` | API GW GET | Monitors 3 Bulgarian dams (Kardzhali · Studen Kladenets · Ivaylovgrad) |
| 8 | `/reports` | API GW POST/GET | Citizen incident submissions + triage feed |

---

## 3. Database Schema (3 DynamoDB Tables)

![diagram](https://mermaid.ink/img/ZXJEaWFncmFtCiAgICBIeWRyb1R3aW5TdGF0dXMgewogICAgICAgIHN0cmluZyByZWdpb25faWQgUEsKICAgICAgICBzdHJpbmcgc3RhdHVzCiAgICAgICAgZGVjaW1hbCBjb25maWRlbmNlCiAgICAgICAgc3RyaW5nIHJlYXNvbmluZwogICAgICAgIG1hcCByZWFzb25pbmdfc3RydWN0dXJlZAogICAgICAgIGxpc3Qgc291cmNlcwogICAgICAgIHN0cmluZyBhc3Nlc3NlZF9hdAogICAgfQogICAgSHlkcm9Ud2luU3Vic2NyaXB0aW9ucyB7CiAgICAgICAgc3RyaW5nIGVtYWlsIFBLCiAgICAgICAgc3RyaW5nIHJlZ2lvbl9pZCBTSwogICAgICAgIHN0cmluZyBkaXNjb3JkX3dlYmhvb2sKICAgICAgICBzdHJpbmcgcGhvbmUKICAgICAgICBzdHJpbmcgdGVsZWdyYW1fY2hhdAogICAgICAgIHN0cmluZyBjcmVhdGVkX2F0CiAgICB9CiAgICBIeWRyb1R3aW5SZXBvcnRzIHsKICAgICAgICBzdHJpbmcgcmVwb3J0X2lkIFBLCiAgICAgICAgc3RyaW5nIGVtYWlsCiAgICAgICAgc3RyaW5nIHJlZ2lvbl9pZAogICAgICAgIHN0cmluZyBkZXNjcmlwdGlvbgogICAgICAgIGRlY2ltYWwgbGF0CiAgICAgICAgZGVjaW1hbCBsbmcKICAgICAgICBzdHJpbmcgc3VibWl0dGVkX2F0CiAgICB9?theme=dark&bgColor=0f172a)

- **Composite key on Subscriptions** — PK `email` + SK `region_id` so one user can subscribe to multiple oblasts cleanly.
- **Municipality roll-up** — clicking `BGR.13.6_1` saves to parent oblast `pleven`. One subscription per oblast, not 29 per municipality.
- **Status table is a snapshot** — 1 row per region, cron upserts on `region_id`.

---

## 4. Real Data Sources (no stubs)

![diagram](https://mermaid.ink/img/Zmxvd2NoYXJ0IExSCiAgICBTMlsiU2VudGluZWwtMiBMMkE8YnIvPk5EVkkgwrcgTkRXSTxici8-MTQtZGF5LCBjbG91ZC1maWx0ZXJlZCJdCiAgICBPTURbIk9wZW5NZXRlbzxici8-MzAtZGF5IHByZWNpcDxici8-Ny1kYXkgdGVtcDxici8-c29pbCBtb2lzdHVyZTxici8-MjRoIGZvcmVjYXN0Il0KICAgIEdldFsic2VudGluZWxfZXh0cmFjdG9yLnB5PGJyLz5nZXRfZW9fYW5kX3dlYXRoZXJfZGF0YShiYm94KSJdCiAgICBLWyJMb2NrZWQgb3V0cHV0IHNjaGVtYTxici8-PGJyLz5uZHZpIMK3IHNvaWxfbW9pc3R1cmVfcGN0PGJyLz5wcmVjaXBfbW1fN2QgwrcgcHJlY2lwX21tXzMwZDxici8-Zmxvb2RfZXh0ZW50X2ttMiDCtyB0ZW1wX21heF9jPGJyLz5uZHdpIMK3IHNvaWxfbW9pc3R1cmVfN2RfZGVsdGE8YnIvPmZvcmVjYXN0X3ByZWNpcF8yNGhfbW08YnIvPmRhdGFfdGltZXN0YW1wIMK3IHNvdXJjZSJdCgogICAgUzIgLS0-IEdldAogICAgT01EIC0tPiBHZXQKICAgIEdldCAtLT4gSw==?theme=dark&bgColor=0f172a)

- **Sentinel Hub Statistical API** (Copernicus Data Space) — OAuth2, evalscript filters clouds (SCL 4/5).
- **OpenMeteo** — free, no key, 30-day historical window.
- **Fallback:** if SH credentials missing, skip SH and use OpenMeteo only — note it in the `source` field.

---

## 5. The AI Layer (Bedrock + Claude 3 Sonnet)

![diagram](https://mermaid.ink/img/Zmxvd2NoYXJ0IFRCCiAgICBBWyIxLiBBdWRpZW5jZSBmcmFtaW5nPGJyLz5Zb3UncmUgYWR2aXNpbmcgQnVsZ2FyaWFuIG1heW9ycyw8YnIvPmNpdmlsLXByb3RlY3Rpb24gb2ZmaWNlcnMuLi4iXQogICAgQlsiMi4gbWV0ZW9yb2xvZ3lfcnVsZXMubWQ8YnIvPmluamVjdGVkIHZlcmJhdGltPGJyLz4odGhyZXNob2xkcywgY29tcG91bmQgcnVsZXMsPGJyLz41IHN0YXR1cyBjb2RlcykiXQogICAgQ1siMy4gTGl2ZSBzZW5zb3IgZGF0YSBhcyBKU09OPGJyLz4oTkRWSSwgTkRXSSwgcHJlY2lwLDxici8-c29pbCBtb2lzdHVyZSwgZm9yZWNhc3QpIl0KICAgIENsYXVkZVsiQ2xhdWRlIDMgU29ubmV0PGJyLz50ZW1wZXJhdHVyZSAwLjE8YnIvPm1heF90b2tlbnMgMTIwMDxici8-c3RyaWN0IEpTT04gb3V0cHV0Il0KICAgIFIxWyJzdGF0dXM6IEZMT09EX1dBVENIIl0KICAgIFIyWyJjb25maWRlbmNlOiAwLjgyIl0KICAgIFIzWyJyZWFzb25pbmdfc3RydWN0dXJlZDo8YnIvPndoYXRzX2hhcHBlbmluZzxici8-d2h5X2l0X21hdHRlcnMgKG51bWJlcnMgaW4gYm9sZCk8YnIvPmN1cnJlbnRfY29udGV4dDxici8-bmV4dF9zdGVwIChhY3Rpb24gVE9EQVkpIl0KCiAgICBBIC0tPiBDbGF1ZGUKICAgIEIgLS0-IENsYXVkZQogICAgQyAtLT4gQ2xhdWRlCiAgICBDbGF1ZGUgLS0-IFIxCiAgICBDbGF1ZGUgLS0-IFIyCiAgICBDbGF1ZGUgLS0-IFIz?theme=dark&bgColor=0f172a)

Temperature 0.1 = deterministic, parseable, repeatable. Rules injected verbatim → Claude reasons against the same thresholds NIMH would use. Audience-locked → no jargon (no NDVI/SPI/SAR), translates EO into actions a mayor takes.

---

## 6. User Click Flow (the 3-second magic)

![diagram](https://mermaid.ink/img/c2VxdWVuY2VEaWFncmFtCiAgICBhY3RvciBVc2VyCiAgICBwYXJ0aWNpcGFudCBGRSBhcyBGcm9udGVuZAogICAgcGFydGljaXBhbnQgQVBJIGFzIEFQSSBHYXRld2F5CiAgICBwYXJ0aWNpcGFudCBMIGFzIM67IC9hc3Nlc3MKICAgIHBhcnRpY2lwYW50IFNIIGFzIFNlbnRpbmVsIEh1YgogICAgcGFydGljaXBhbnQgT00gYXMgT3Blbk1ldGVvCiAgICBwYXJ0aWNpcGFudCBCUiBhcyBCZWRyb2NrCiAgICBwYXJ0aWNpcGFudCBEQiBhcyBIeWRyb1R3aW5TdGF0dXMKCiAgICBVc2VyLT4-RkU6IENsaWNrIHJlZ2lvbiBtYXJrZXIKICAgIEZFLT4-RkU6IHNldFNlYXJjaFBhcmFtcyg_cmVnaW9uPXBsZXZlbikKICAgIE5vdGUgb3ZlciBGRTogQ2FjaGUtZmlyc3QgcGFpbnQ8YnIvPmZyb20gSHlkcm9Ud2luU3RhdHVzCgogICAgRkUtPj5BUEk6IFBPU1QgL2Fzc2VzcyB7IHJlZ2lvbl9pZCwgYmJveCB9CiAgICBBUEktPj5MOiBpbnZva2UKICAgIHBhcgogICAgICAgIEwtPj5TSDogTkRWSSArIE5EV0kgKDE0LWRheSkKICAgICAgICBMLT4-T006IHByZWNpcCArIHNvaWwgKyB0ZW1wCiAgICBlbmQKICAgIFNILS0-Pkw6IHN0YXRzCiAgICBPTS0tPj5MOiBzdGF0cwogICAgTC0-Pkw6IGxvYWQgbWV0ZW9yb2xvZ3lfcnVsZXMubWQKICAgIEwtPj5CUjogQmVkcm9jayBpbnZva2UKICAgIEJSLS0-Pkw6IHN0YXR1cywgY29uZmlkZW5jZSwgcmVhc29uaW5nCiAgICBMLT4-REI6IHNuYXBzaG90IHVwc2VydAogICAgTC0tPj5BUEk6IDIwMCBKU09OCiAgICBBUEktLT4-RkU6IGFzc2Vzc21lbnQKICAgIEZFLS0-PlVzZXI6IEFsZXJ0UGFuZWwgcmVuZGVycw==?theme=dark&bgColor=0f172a)

What the user sees: status badge (color-coded), confidence bar, 4 reasoning sections, precipitation chart, forecast outlook, synoptic chart, citizen reports for that region, subscribe CTA.

---

## 7. Subscribe Flow

![diagram](https://mermaid.ink/img/c2VxdWVuY2VEaWFncmFtCiAgICBhY3RvciBVc2VyCiAgICBwYXJ0aWNpcGFudCBGRSBhcyBGcm9udGVuZAogICAgcGFydGljaXBhbnQgTCBhcyDOuyAvc3Vic2NyaWJlCiAgICBwYXJ0aWNpcGFudCBEQiBhcyBIeWRyb1R3aW5TdWJzY3JpcHRpb25zCiAgICBwYXJ0aWNpcGFudCBTbmFwIGFzIEh5ZHJvVHdpblN0YXR1cwogICAgcGFydGljaXBhbnQgQnJldm8gYXMgQnJldm8KICAgIHBhcnRpY2lwYW50IERDIGFzIERpc2NvcmQKCiAgICBVc2VyLT4-RkU6IFN1Ym1pdCBlbWFpbCArIERpc2NvcmQgd2ViaG9vawogICAgRkUtPj5MOiBQT1NUIHsgZW1haWwsIHJlZ2lvbl9pZCwgZGlzY29yZF93ZWJob29rIH0KICAgIEwtPj5MOiB2YWxpZGF0ZSArIHJvbGwgdXAgbXVuaWNpcGFsaXR5CiAgICBMLT4-REI6IFB1dEl0ZW0gKGF0dHJpYnV0ZV9ub3RfZXhpc3RzKQogICAgYWx0IEFscmVhZHkgZXhpc3RzCiAgICAgICAgREItLT4-TDogQ29uZGl0aW9uYWxDaGVja0ZhaWxlZAogICAgICAgIEwtLT4-RkU6IDQwOSBhbHJlYWR5IHN1YnNjcmliZWQKICAgIGVsc2UgTmV3CiAgICAgICAgREItLT4-TDogc2F2ZWQKICAgICAgICBMLT4-U25hcDogR2V0SXRlbShyZWdpb25faWQpCiAgICAgICAgU25hcC0tPj5MOiBjdXJyZW50IHNuYXBzaG90CiAgICAgICAgcGFyIFdlbGNvbWUgZmFuLW91dAogICAgICAgICAgICBMLT4-QnJldm86IEhUTUwgZW1haWwgKyBITUFDIHVuc3ViIGxpbmsKICAgICAgICAgICAgTC0-PkRDOiBXZWJob29rIGVtYmVkCiAgICAgICAgZW5kCiAgICAgICAgTC0tPj5GRTogMjAxIGRlbGl2ZXJlZAogICAgZW5k?theme=dark&bgColor=0f172a)

---

## 8. Cron Transition Alerts (the autonomous brain)

This is the part that runs **while everyone sleeps** — and it's the differentiator vs. a static dashboard.

![diagram](https://mermaid.ink/img/Zmxvd2NoYXJ0IFRCCiAgICBTdGFydChbIkV2ZW50QnJpZGdlPGJyLz5yYXRlKDMwIG1pbnV0ZXMpIl0pCiAgICBMb29we3siRm9yIGVhY2ggb2YgMzIgcmVnaW9uczxici8-MyBvYmxhc3RzICsgMjkgbXVuaWNpcGFsaXRpZXMifX0KICAgIFByaW9yWyJSZWFkIHByaW9yIHN0YXR1czxici8-ZnJvbSBIeWRyb1R3aW5TdGF0dXMiXQogICAgQXNzZXNzWyJhc3Nlc3NfcmVnaW9uPGJyLz5TZW50aW5lbCArIE9wZW5NZXRlbyArIEJlZHJvY2siXQogICAgV3JpdGVbIldyaXRlIG5ldyBzbmFwc2hvdCJdCiAgICBEZWNpZGV7IlN0YXR1cyBjaGFuZ2VkPyJ9CiAgICBTa2lwWyJTaWxlbnQg4oCUIG5vIGZpcmUiXQogICAgQ2hhbm5lbFsiRmlyZSBzaGFyZWQgRGlzY29yZCBjaGFubmVsIl0KICAgIFN1YnNbIlNjYW4gc3Vic2NyaWJlcnMgV0hFUkUgcmVnaW9uX2lkIl0KICAgIEZhbnt7IkZvciBlYWNoIHN1YnNjcmliZXIifX0KICAgIEVtYWlsWyJQZXJzb25hbGl6ZWQgYWxlcnQgZW1haWwiXQogICAgUGVyVXNlclsiUGVyLXVzZXIgRGlzY29yZCB3ZWJob29rIl0KCiAgICBTdGFydCAtLT4gTG9vcAogICAgTG9vcCAtLT4gUHJpb3IKICAgIFByaW9yIC0tPiBBc3Nlc3MKICAgIEFzc2VzcyAtLT4gV3JpdGUKICAgIFdyaXRlIC0tPiBEZWNpZGUKICAgIERlY2lkZSAtLSAiU0FGRSB0byBTQUZFIiAtLT4gU2tpcAogICAgRGVjaWRlIC0tICJhbnkgdHJhbnNpdGlvbiIgLS0-IENoYW5uZWwKICAgIENoYW5uZWwgLS0-IFN1YnMKICAgIFN1YnMgLS0-IEZhbgogICAgRmFuIC0tPiBFbWFpbAogICAgRmFuIC0tPiBQZXJVc2Vy?theme=dark&bgColor=0f172a)

### Transition matrix — when do we fire?

| Prior | New | Action |
|---|---|---|
| none (first run) | `SAFE` | silent |
| none (first run) | non-SAFE | fire |
| `SAFE` | `SAFE` | silent |
| `SAFE` | any non-SAFE | fire (escalation) |
| non-SAFE | `SAFE` | fire (recovery) |
| non-SAFE | different non-SAFE | fire (re-grade) |

We only bill notifications + Bedrock on **state changes**, not every cron run. A subscriber for `pleven` gets exactly one email when conditions deteriorate, not 48 emails per day.

---

## 9. Unsubscribe Flow (HMAC-signed, one-click)

![diagram](https://mermaid.ink/img/c2VxdWVuY2VEaWFncmFtCiAgICBwYXJ0aWNpcGFudCBFbWFpbCBhcyBBbGVydCBlbWFpbAogICAgYWN0b3IgVXNlcgogICAgcGFydGljaXBhbnQgRkUgYXMgL3Vuc3Vic2NyaWJlIHBhZ2UKICAgIHBhcnRpY2lwYW50IEwgYXMgzrsgL3Vuc3Vic2NyaWJlCiAgICBwYXJ0aWNpcGFudCBEQiBhcyBIeWRyb1R3aW5TdWJzY3JpcHRpb25zCgogICAgTm90ZSBvdmVyIEVtYWlsOiBGb290ZXIgbGluazo8YnIvPj9lPXVzZXImcj1wbGV2ZW4mdD1obWFjX3Rva2VuCiAgICBVc2VyLT4-RW1haWw6IENsaWNrIFVuc3Vic2NyaWJlCiAgICBFbWFpbC0-PkZFOiBHRVQgL3Vuc3Vic2NyaWJlP2UmciZ0CiAgICBGRS0-Pkw6IFBPU1QgZSwgciwgdAogICAgTC0-Pkw6IHZlcmlmeSBITUFDLVNIQTI1Njxici8-Y29uc3RhbnQtdGltZSBjb21wYXJlCiAgICBhbHQgVG9rZW4gdmFsaWQKICAgICAgICBMLT4-REI6IERlbGV0ZUl0ZW0gKGlkZW1wb3RlbnQpCiAgICAgICAgTC0tPj5GRTogMjAwIHVuc3Vic2NyaWJlZAogICAgICAgIEZFLS0-PlVzZXI6IFlvdSdyZSB1bnN1YnNjcmliZWQKICAgIGVsc2UgQmFkIHRva2VuCiAgICAgICAgTC0tPj5GRTogNDAwIGludmFsaWQgdG9rZW4KICAgICAgICBGRS0tPj5Vc2VyOiBJbnZhbGlkIG9yIGV4cGlyZWQgbGluawogICAgZW5k?theme=dark&bgColor=0f172a)

- Token = `HMAC-SHA256(secret, "email|region_id")[:16]` — unguessable, unforgeable.
- `hmac.compare_digest()` = constant-time compare, no timing oracle.
- Delete is idempotent — clicking twice doesn't error.

---

## 10. Frontend Routes

![diagram](https://mermaid.ink/img/Zmxvd2NoYXJ0IExSCiAgICBMYXlvdXRbIkxheW91dCAoc2lkZWJhcikiXSAtLT4gUm9vdFsiLyBPdmVydmlldzxici8-TWFwYm94ICsgQWxlcnRQYW5lbCJdCiAgICBMYXlvdXQgLS0-IEluY1siL2luY2lkZW50czxici8-Q2l0aXplbiByZXBvcnQgdHJpYWdlIl0KICAgIExheW91dCAtLT4gU3JjWyIvc291cmNlczxici8-RGF0YSBhdHRyaWJ1dGlvbiJdCiAgICBMYXlvdXQgLS0-IERhbVsiL2RhbXM8YnIvPjMgQnVsZ2FyaWFuIGRhbXMiXQogICAgUHVibGljWyJObyBsYXlvdXQiXSAtLT4gU3ViWyIvc3VibWl0PGJyLz5QdWJsaWMgaW5jaWRlbnQgZm9ybSJdCiAgICBQdWJsaWMgLS0-IFVuc1siL3Vuc3Vic2NyaWJlPGJyLz5ITUFDIHRva2VuIGxhbmRpbmciXQogICAgUHVibGljIC0tPiBORlsiLyogTm90Rm91bmQiXQ==?theme=dark&bgColor=0f172a)

Deep links: `/?region=pleven` · `/?region=BGR.13.9_1` · `/unsubscribe?e=…&r=…&t=…`

---

## 11. Demo-Mode Fallbacks

> The pitch demo will **never** break, by design.

![diagram](https://mermaid.ink/img/Zmxvd2NoYXJ0IExSCiAgICBCMVsiQmVkcm9jayBmYWlscyJdIC0tPiBCMUZbIkhhcmRjb2RlZCBGTE9PRF9XQVRDSDxici8-KyBEZW1vIG1vZGUgdGFnIl0KICAgIEIyWyJTZW50aW5lbCBIdWIgY3JlZHMgbWlzc2luZyJdIC0tPiBCMkZbIk9wZW5NZXRlbyBvbmx5PGJyLz4rIG5vdGUgaW4gc291cmNlIl0KICAgIEIzWyJCcmV2byB1bnNldCJdIC0tPiBCM0ZbIkxvZyBkZW1vLW1vZGU8YnIvPnN0aWxsIHJldHVybiBzdWNjZXNzIl0KICAgIEI0WyJEeW5hbW9EQiBtaXNzaW5nIl0gLS0-IEI0RlsiL3N1YnNjcmliZSDihpIgMjAxPGJyLz4rIGRlbW9fbW9kZSBmbGFnIl0KICAgIEYxWyIvYXNzZXNzIHVucmVhY2hhYmxlIl0gLS0-IEYxRlsiYnVpbGREZW1vUmVzcG9uc2U8YnIvPisgeWVsbG93IGJhbm5lciJdCiAgICBGMlsiL3N0YXR1cyBlbXB0eSJdIC0tPiBGMkZbIk5ldXRyYWwgZ3JleSBwb2x5Z29ucyJdCgogICAgY2xhc3NEZWYgZmFpbCBmaWxsOiM3ZjFkMWQsc3Ryb2tlOiNmY2E1YTUsY29sb3I6I2ZmZgogICAgY2xhc3NEZWYgb2sgZmlsbDojMDY0ZTNiLHN0cm9rZTojNmVlN2I3LGNvbG9yOiNmZmYKICAgIGNsYXNzIEIxLEIyLEIzLEI0LEYxLEYyIGZhaWwKICAgIGNsYXNzIEIxRixCMkYsQjNGLEI0RixGMUYsRjJGIG9r?theme=dark&bgColor=0f172a)

---

## 12. Demo Walkthrough Cheat Sheet

| Step | Do | Say |
|---|---|---|
| 1 | Open the map | "3 oblasts + 29 municipalities, Mapbox satellite, click anywhere" |
| 2 | Click **Pleven Oblast** | "Cache-first paint, instant. Then in the background, /assess hits Sentinel + OpenMeteo + Bedrock" |
| 3 | Show AlertPanel | "4 plain-language sections. No NDVI jargon — what's happening, why it matters, context, next step" |
| 4 | Click a municipality (Nikopol) | "GADM GID_2 codes, 29 of them — same backend, smaller bbox" |
| 5 | Subscribe with email | "201 → welcome email lands → Discord embed fires" |
| 6 | Open `/dams` | "3 dams correlated with Sentinel NDWI: WATER_REGIME, STABLE, OPEN_GATES" |
| 7 | Open `/incidents` | "Citizens close the loop — POST /reports, triage feed for civil protection" |
| 8 | Mention cron | "30-min EventBridge → 32 regions → fires only on transitions → email + per-user Discord" |

---

## The 30-second pitch sentence

> _"Click any region in Bulgaria → in 3 seconds we pull live Sentinel-2 NDVI, NDWI, and OpenMeteo weather, feed Bulgaria-calibrated meteorological thresholds and the live numbers to **Claude on Bedrock**, and return a structured assessment a mayor can act on. Subscribe, and you'll get an email + Discord alert the moment your oblast transitions out of SAFE — and we run that check **every 30 minutes, automatically, for all 32 regions**."_

---

_HydroTwin · CASSINI Hackathon Bulgaria 2026 · Sofia · 25–27 April_
