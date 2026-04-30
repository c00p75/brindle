# Frontend — Brindle Platform

Next.js 14 (App Router), TypeScript, no client-state library (hooks + fetch).

## Run

```bash
npm install
npm run dev
```

Defaults to <http://localhost:3000>. Proxies `/api/*` to the backend at
`NEXT_PUBLIC_API_BASE` (default `http://localhost:8000`) — see
[next.config.js](next.config.js).

## Type-check

```bash
npm run typecheck
```

## Design notes

- Auth: JWT from backend stored in `localStorage`, attached to every fetch by
  `lib/api.ts`. 401 clears the session and redirects to `/login`.
- RBAC: role matrix in `lib/rbac.ts` mirrors the backend matrix; UI hides
  actions a role can't perform — backend still enforces.
- Config editor (`app/bots/[id]/config/page.tsx`) implements the full
  draft → validate → apply flow with a live diff vs the active version and
  a typed-confirmation gate for risky changes.
- No secret values ever render. `credential_ref` is the only broker secret
  field; it must be a `secret://…` reference.
