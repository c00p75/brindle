# FRONTEND_PRODUCT_REQUIREMENTS.md

## Overview

This document defines the requirements for building a **full-stack trading bot application** with a high-quality frontend, authentication, and complete no-code control for non-developer users.

The system must NOT be backend-only. It must provide a **secure, intuitive, and powerful UI** that allows users to operate the trading platform without writing code.

---

## Core Principle

> The application must be fully controllable from the frontend by a non-developer user.

---

## 1. Frontend as a First-Class Product

The frontend is not just a dashboard. It is the **primary interface** for:

- creating bots
- configuring strategies
- managing risk
- connecting brokers
- monitoring performance
- handling incidents
- auditing actions

---

## 2. Authentication (Mandatory)

### Required Features

- Email/password login
- Secure session handling
- Logout
- Password reset

### Recommended

- Google OAuth
- Email verification
- Multi-factor authentication (MFA)

### Security Rules

- All sensitive routes must be protected
- No secrets exposed to frontend
- Sessions must be securely stored

---

## 3. Authorization (RBAC)

### Roles

- **Admin**
  - Full access
  - Manage users, bots, credentials

- **Operator**
  - Start/stop bots
  - Respond to alerts

- **Reviewer**
  - Approve/reject config changes

- **Viewer/Auditor**
  - Read-only access

---

## 4. Bot Management UI

Users must be able to:

- Create bot
- Duplicate bot
- Edit configuration
- Validate configuration
- Apply configuration
- Rollback configuration
- Start / Pause / Stop bot
- Archive bot

### Bot States

- draft
- validated
- ready
- running
- paused
- halted
- error
- archived

---

## 5. Strategy Configuration

- Select strategy
- Edit parameters via forms
- Parameter validation
- Presets/templates
- Inline explanations

---

## 6. Risk Configuration

Users must configure:

- Position size limits
- Exposure limits
- Drawdown limits
- Daily loss limits

UI must:
- Validate inputs
- Show warnings for risky values

---

## 7. Broker / Adapter Configuration

Users must be able to:

- Select adapter (paper, oanda, deriv, etc.)
- Select environment (demo/live)
- Input credentials
- Test connection

### Security

- Credentials must be masked
- Stored securely on backend
- Never returned to frontend

---

## 8. Config Workflow (Critical)

All configuration changes must follow:

1. Draft
2. Validate
3. Review (optional)
4. Apply
5. Audit

### UI Requirements

- Show diff between versions
- Require confirmation for risky changes
- Prevent invalid configs from being applied

---

## 9. Dashboard & Monitoring

### Required Views

- Portfolio overview
- Bot list
- Bot details
- Positions
- Orders / fills
- Equity curve
- Drawdown chart
- Alerts/incidents
- Metrics

---

## 10. Alerts & Incidents

Users must see:

- Active alerts
- Incident history
- Severity levels

Actions:
- Acknowledge
- Pause bot
- Investigate logs

---

## 11. Audit Trail

- Every action must be logged
- Show:
  - who did it
  - what changed
  - when

---

## 12. UX Requirements

- Clean, modern UI
- Responsive design
- Clear status indicators
- Strong validation messages
- Confirmation dialogs
- Guided workflows
- Tooltips and help text

---

## 13. Non-Developer Usability

The UI must:

- Hide complexity
- Provide defaults
- Prevent unsafe actions
- Guide users step-by-step

---

## 14. Secret Management

- Input via UI
- Stored securely in backend
- Masked in UI
- Never logged
- Support rotation/revocation

---

## 15. Required Pages

- Login / Signup
- Dashboard
- Bots
- Bot Details
- Config Editor
- Strategies
- Risk Settings
- Broker Connections
- Runs / Metrics
- Alerts / Incidents
- Audit Logs
- User Settings

---

## Final Requirement

> The system must be a complete, secure, and user-friendly trading platform where a non-developer can fully operate, configure, and monitor trading bots from the frontend without touching backend code.
