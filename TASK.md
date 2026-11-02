# ChurchConnect Kenya - Project Tracking & Milestones

## Stack: HTML5, CSS3, Modern JavaScript & Python (Flask + SQLite)
- **Target Organization:** Local Seventh-day Adventist (SDA) Church in Kenya
- **Author:** Samuel Omari (`samuel.omari@student.moringaschool.com`)
- **Architecture:** Python Flask API + Dynamic Web Interface (HTML, CSS, JavaScript)

---

## Phase Checklist

- [x] **Phase 1: Discuss & Scope Definition**
  - [x] Ingest and document project proposal (`PROPOSAL.md`).
  - [x] Switch technology stack to: **HTML, CSS, JS, and Python**.
  - [x] Implement mandatory Login Wall & Member Self-Service access.
  - [x] Add announcements module and non-confidential member views.

- [x] **Phase 2: Database & Security Engine**
  - [x] Database Schema with `announcements` and `users.member_id` foreign keys (`database.py`).
  - [x] Brute-force account lockout protection (5 failed attempts locks account for 15 minutes).
  - [x] Input validation with email regex and strong password complexity checking.
  - [x] Password hashing with `bcrypt` and session tokens with `PyJWT`.
  - [x] Comprehensive `.gitignore` to hide development and build artifacts from public repositories.

- [x] **Phase 3: Core API Endpoints & Role Partitioning**
  - [x] Member self-service registration (`POST /api/auth/register`).
  - [x] Secure authentication with failed attempt tracking (`POST /api/auth/login`).
  - [x] Church announcements feed (`GET /api/announcements`, `POST /api/announcements`).
  - [x] Personal giving envelope history (`GET /api/finance/my-giving`).
  - [x] Role-restricted Treasury, Vouchers, Audit, and Monthly statements (strictly blocking members with 403 Forbidden).

- [x] **Phase 4: Frontend Implementation (HTML, CSS, JS)**
  - [x] Mandatory Login Wall screen with Sign In & Member Registration tabs (`templates/index.html`).
  - [x] Distinct, dedicated **Member Portal** (Announcements, Sabbath worship schedule, My Giving Receipts, M-Pesa giving).
  - [x] Dedicated **Officer Executive Portal** (Confidential Treasury totals, Vouchers, Requisitions, Audits, Monthly statements).
  - [x] Quick Demo Persona buttons on the login screen for testing both Church Leaders and Regular Church Members.
  - [x] Active Logout button to clear tokens and return to the login wall.

- [x] **Phase 5: Verification, Automated Testing & Documentation**
  - [x] Automated test suite verifying registration validation, brute force lockout, member security guards, and voucher approvals (`tests/test_app.py` - **8/8 Passing**).
  - [x] Comprehensive documentation in `README.md`.
