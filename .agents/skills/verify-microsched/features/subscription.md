# Subscription management route

Current source at the [indexed baseline](README.md): `frontend/src/SubscriptionScreen.tsx:694`, `frontend/src/AppNavigation.tsx:55`, `frontend/src/TrackerScreen.tsx:653`.

## Sub-features

List, create/edit, renewal/cancellation and price/expiry settings.

## How to get to it (user POV)

Synthetic login → **Ứng dụng** → `app-subscriptions-link`, or **Theo dõi** → **Báo cáo** → `subscription-entry`. Direct `/subscription?highlight=OWN_ID` highlights a visible matching row. **Quay lại** uses in-app replace when appropriate to avoid Back loops.

Real prerequisites: Known subscription dates, prices, auto-renew/private state; separate approved writes and frozen date clock.

## Driving it in a current synthetic candidate

Use `subscription-screen`, `subscription-card[data-subscription-id]`, `subscription-dialog`, `subscription-renew-dialog` and `subscription-renew-summary`. Settings use `settings-list-price-toggle` and `settings-expiry-lead-days`. Freeze Tracker reads as well as `/api/subscriptions` and `/api/settings`. Use `frontend/e2e/subscription.spec.ts` for the existing browser oracle.

Oracle: Frozen dates/clock determine status, renewal preview and expiry. In permitted writes verify the affected subscription and renewal Entry. Read-only navigation checks highlight and Back without writing.

## Gotchas

No purchase or external commitment. Browser permission/price settings must not be changed just to reach a smoke.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
