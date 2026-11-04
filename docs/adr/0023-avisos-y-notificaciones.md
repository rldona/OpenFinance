# ADR-0023: Deterministic alerts, Web Push notifications and weekly summary

- Status: Accepted
- Date: 2026-11-03

## Context

With scheduled payments, forecast and budgets (ADR-0021, ADR-0022) there is data to warn about what matters: a duplicate charge, a fee, a bill that goes up, a payment that has not arrived, a balance about to go negative. Today you have to open the app to find out. The household is two people and the installation is self-hosted (HTTPS with its own domain).

## Decision

### Alerts (OF-1301)

- An **alert** is a pure function of today's data. **It is not stored**: it is recomputed on every query, like payment matching. The only thing stored is that a person **dismissed** it, by its key (`alert_dismissals`, per person, not per household).
- Detectors, each with its explicit threshold and no learning:
  - `duplicate`: same expense (account, merchant, amount) within ≤ 2 days; only the last 14 days.
  - `fee`: expense whose description or bank type says "comisión"/"fee" (fee), last 30 days.
  - `price_rise`: recurring charge whose last change was this month or the previous one and rose by ≥ 5%.
  - `late_payment`: overdue occurrence of a scheduled payment.
  - `low_balance`: a cash account goes negative in the next 30 days according to the forecast.
  - `budget_over`: budget exceeded this month.
- Each alert's **key** is stable and names what causes it (`duplicate:<transaction>`, `price_rise:<merchant>:<month>`…): a new price change alerts again; dismissing one does not silence the next.
- **Privacy (ADR-0013)**: each detector only sees the accounts visible to the person querying. An alert from a personal account is only seen by its owner, cannot be dismissed from another account (404) and does not appear in any other person's notification. Budget and recurring-charge alerts use only the joint account, like the rest of the household reports.
- Dismissing only accepts keys of alerts that exist today for that person: an invented or foreign key returns 404.

### Notifications (OF-1302): Web Push

- Single channel in this phase: **Web Push** (W3C standard with VAPID keys). The app is already a PWA and the installation uses HTTPS, so there is no extra server or app, and the content travels end-to-end encrypted to the device. ntfy is ruled out for now (another service to maintain and, on the public server, a third party sees the text); sending goes behind a port (`PushSender`), so ntfy can be a second adapter later without touching the engine.
- Each person subscribes from their phone (one subscription per browser) and chooses which alert types they want. An expired subscription (HTTP 404/410 from the push service) is deleted automatically.
- **The server only sends to known push services** (`fcm.googleapis.com`, `push.services.mozilla.com`, `push.apple.com`, `notify.windows.com`, https only and no port or credentials): the endpoint is supplied by the client and, without that list, anyone with a session could make the server request any URL (SSRF).
- **Nothing runs inside the server**: like backups, sending is launched by `openfinance alerts notify` from cron. It is idempotent: `alert_deliveries` stores (person, key) of what has already been sent, so running it every hour repeats nothing.
- The text of a notification **carries no amounts or merchant names**: only the alert type and how many there are ("Tienes 2 avisos nuevos en OpenFinance" ("You have 2 new alerts in OpenFinance")); the detail is seen inside, once signed in. Push services (Google, Apple, Mozilla) see metadata but never the financial content.
- Without VAPID keys configured (`OPENFINANCE_VAPID_PRIVATE_KEY`, `OPENFINANCE_VAPID_SUBJECT`), the feature is off and the web app says so; alerts can still be seen in the app.
- It only works over HTTPS; in `direct` mode (HTTP) it is not offered. On iPhone it requires iOS 16.4+ and the PWA added to the home screen.

### Weekly summary (OF-1303)

- A computed view, not a stored report: spending in the last complete week versus the one before it, the three heaviest categories, payments in the next 7 days and open alerts. It is computed over the joint account and the accounts visible to the requester.
- It is sent as one more notification (only the notice that it is ready; the content is opened in the app), once per ISO week and person: the first time `alerts notify` runs each week, so if cron fails on a Monday it arrives the next day. The summarized week is the last complete one (Monday to Sunday). Each person can turn it off.

## Consequences

- The detectors are pure functions and are tested one by one; any threshold change is a visible constant.
- `alert_dismissals`, `push_subscriptions`, `notification_preferences` and `alert_deliveries` are added. None touches the ledger or enters the change log (they are interface state, not accounting data).
- New dependency: `pywebpush` (MPL-2.0 license, already allowed by `make licenses`).
- Still to be tested on a real phone; in CI it is only tested with a simulated push service.
