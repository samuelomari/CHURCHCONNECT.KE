# ChurchConnect Kenya
### Church Management & Financial Accountability System
**Author:** Samuel Omari (`samuel.omari@student.moringaschool.com`)
**Target:** Seventh-day Adventist Local Church — East Kenya Union Conference / Central Kenya Conference
**Stack:** Python 3 · Flask · SQLite · Vanilla JS (ES6+) · HTML5/CSS3 · Safaricom M-Pesa Daraja API · Chart.js

---

## Table of Contents
1. [Project Overview](#1-project-overview)
2. [Feature Inventory](#2-feature-inventory)
3. [Security Architecture](#3-security-architecture)
4. [Role Hierarchy & Access Control](#4-role-hierarchy--access-control)
5. [Quick Start](#5-quick-start)
6. [Running the Database in Beekeeper Studio](#6-running-the-database-in-beekeeper-studio)
7. [Pre-Seeded Demo Accounts](#7-pre-seeded-demo-accounts)
8. [API Reference](#8-api-reference)
9. [Database Schema](#9-database-schema)
10. [Project File Structure](#10-project-file-structure)
11. [Environment Configuration](#11-environment-configuration)
12. [Running Tests](#12-running-tests)
13. [Deployment](#13-deployment)

---

## 1. Project Overview

ChurchConnect Kenya is a full-stack web application built to solve two core problems in SDA local church administration:

**Financial Accountability** — Every shilling of tithe and offering is tracked from the moment it is received, through a mandatory dual-authorization expenditure workflow, to final disbursement. The system enforces SDA policy that Holy Tithe and Conference Trust Funds are held separately and remitted 100% to the Conference Field.

**Church Administration** — Membership rolls, board minutes, resolutions, asset inventory, departmental budgets, event scheduling, and attendance records are all managed in one place with full audit trail.

The system serves two distinct user classes with completely separate interfaces: a **Member Portal** for regular congregation members (personal giving receipts, announcements, events) and an **Officer Executive Portal** for church leadership (full financial engine, governance tools, accountability centre).

---

## 2. Feature Inventory

### Authentication & Security
- Mandatory login wall — no page is accessible without a valid JWT session
- Bcrypt password hashing with salt rounds
- Password complexity enforcement (min 8 chars, uppercase, lowercase, digit)
- Strict email regex validation on both frontend and backend
- Brute-force lockout — 5 failed attempts locks account for 15 minutes
- JWT tokens stored in `localStorage`, verified on every API call
- Auto-generated `SDA-YYYY-NNNN` member number on first login if none exists
- Distinct sign-out that clears session and returns to login screen

### Member Portal (role: `MEMBER`)
- Personal dashboard with scripture banner, giving KPIs, announcements preview, upcoming events
- Full announcements board (filtered to `ALL` and `MEMBERS_ONLY` audience)
- Church calendar & events
- **My Giving Receipts** — personal tithe & offering history with fund breakdown, completely private from other members
- **Give via M-Pesa** — STK Push simulation via Safaricom Daraja Paybill `174379` with instant digital receipt
- Member directory (non-confidential: name, member number, department, status only)
- Church ministries / department directory

### Officer Executive Portal
#### Treasury & Giving
- Tithe & Offering Envelope Register — record cash, M-Pesa, cheque, bank transfer
- Auto-generated receipt numbers (`REC-YYYY-NNNNN`) with cryptographic verification codes
- Fund category allocation per envelope (Tithe, Church Budget, Building Fund, AY Fund, Welfare, Camp Meeting, World Budget)
- Financial reversal system — transactions are never deleted, only reversed with mandatory audit reason
- M-Pesa Daraja simulation hub with automatic envelope reconciliation

#### Expenditure Voucher Workflow (4-step dual authorization)
1. **Submission** — Department Leader submits requisition within department budget
2. **Treasury Review** — Head/Assistant Treasurer verifies funds and invoices
3. **Elder/Pastor Authorization** — First Elder or Pastor grants final approval
4. **Disbursement** — Treasurer executes payment and budget is automatically deducted
- Committee vote system for expenditures ≥ KES 10,000 (quorum = 2 approvals)
- Self-approval strictly blocked (requesters cannot approve their own vouchers)
- Budget overspend blocked at submission time

#### Member Management
- Full membership roll with baptism records, phone, email, department, residence
- Officer view includes a **Contribution Summary** button per member — shows per-fund totals and full receipt history (Treasurer/Pastor/Elder/Auditor only)
- Member search by name, member number, or phone
- Add new members (Church Clerk, Pastor, First Elder)

#### Church Assets & Inventory
- Asset registry with tag number, category, quantity, location, condition, custodian, purchase cost, notes
- Condition badges: Excellent (blue), Good (green), Fair (yellow), Needs Repair (red)
- Custodian assigned from active officers list
- Categories: Sound Equipment, Musical Instrument, Furniture, Electronics/Projector, Computer & IT, Vehicle

#### Board Minutes & Resolutions
- Record full meeting minutes with meeting type, date, chairperson, secretary
- Attach action resolutions per meeting — resolution number, title, description, assigned officer, due date, status
- Meeting types: Church Board, Elders Council, Business Meeting, Departmental
- Resolution statuses: Pending, In Progress, Completed

#### Departments & Budgets
- 8 departments with budget allocation, budget spent, remaining balance
- Visual progress bar with colour thresholds (>65% = amber, >85% = red)
- Leader contact info, member count, voucher count

#### Events & Attendance
- Church calendar with programme title, location, start/end time, coordinator
- Sabbath attendance register — adults, children, visitors, total per service type

#### Accountability Centre (Officers)
- Transaction entry attribution by recording officer
- Department budget utilization warnings (>80% threshold)
- Financial reversals & corrections history
- Committee approval vote log

#### SDA Monthly Financial Statement
- Part A: Conference Trust Funds — total tithe, conference offerings, net remittance due
- Part B: Local Church — total local offerings, authorized disbursements, net operating balance
- Full fund category breakdown table
- Print-ready layout

#### Governance & Audit
- Immutable audit trail — every financial and administrative action is logged with timestamp, user, role, entity, and details
- Role management (Pastor only) — assign any of 8 officer roles to registered members
- Database backup export (JSON) for disaster recovery

---

## 3. Security Architecture

### Authentication Flow
```
Login → bcrypt verify → reset failed_attempts → auto-create member record if missing
     → generate JWT (24h expiry) → store in localStorage → all API calls send Bearer token
```

### Password Policy
| Rule | Requirement |
|---|---|
| Minimum length | 8 characters |
| Uppercase | At least 1 |
| Lowercase | At least 1 |
| Digit | At least 1 |
| Lockout | 5 failed attempts → 15 min lock |

### JWT Token Payload
```json
{
  "id": "usr-xxxxxxxx",
  "email": "user@domain.ke",
  "role": "HEAD_TREASURER",
  "member_id": "mem-xxxxxxxx",
  "department_id": "dept-xxxxxxxx"
}
```

### Separation of Duties
- Requesters **cannot** approve their own expenditure vouchers (enforced at API level)
- Disbursement requires Elder/Pastor authorization first
- Committee quorum (2 votes) required for expenditures ≥ KES 10,000
- Financial reversals require a written justification and are permanently logged

---

## 4. Role Hierarchy & Access Control

| Role | Portal | Key Permissions |
|---|---|---|
| `PASTOR` | Officer | Full access + role assignment + backup |
| `FIRST_ELDER` | Officer | Full access + elder authorization |
| `HEAD_TREASURER` | Officer | Treasury, envelopes, voucher review & disbursement, member contributions |
| `ASSISTANT_TREASURER` | Officer | Treasury, envelopes, voucher review & disbursement |
| `CHURCH_CLERK` | Officer | Members, events, attendance, announcements, assets, meetings |
| `DEPARTMENT_LEADER` | Officer | Own department vouchers, events, announcements |
| `AUDITOR` | Officer | Read-only financial + accountability + audit logs |
| `AUTHORIZED_ELDER_READONLY` | Officer | Read-only financial + accountability |
| `MEMBER` | Member | Personal giving, announcements, events, directory |

---

## 5. Quick Start

### Prerequisites
- Python 3.10+
- pip

### Installation
```bash
# Clone the repository
git clone <repo-url>
cd CHURCHCONNECT.KE

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment config
cp .env.example .env
# Edit .env and set a strong SECRET_KEY

# Seed the database with sample SDA church data
python3 seed.py

# Start the application
python3 app.py
```

Open your browser at:
```
http://localhost:5000
```

---

## 6. Running the Database in Beekeeper Studio

The database is a standard **SQLite** file located at:
```
CHURCHCONNECT.KE/churchconnect.db
```

### Steps to connect in Beekeeper Studio

1. Download and install [Beekeeper Studio Community Edition](https://www.beekeeperstudio.io/) (free, open source)
2. Open Beekeeper Studio
3. Click **New Connection**
4. Select **SQLite** as the connection type
5. Under **Database File Path**, click Browse and navigate to:
   ```
   /home/samuel-omari/CHURCHCONNECT.KE/churchconnect.db
   ```
6. Click **Test** → you should see "Connection successful"
7. Click **Connect**

### What you can do in Beekeeper Studio
- Browse all 21 tables in the left sidebar
- Run raw SQL queries — e.g.:
  ```sql
  -- View all confirmed giving envelopes with member names
  SELECT e.receipt_number, m.first_name || ' ' || m.last_name AS member,
         e.total_amount, e.payment_method, e.transaction_date
  FROM tithe_offering_envelopes e
  LEFT JOIN members m ON e.member_id = m.id
  WHERE e.status = 'CONFIRMED'
  ORDER BY e.transaction_date DESC;

  -- View pending vouchers
  SELECT v.voucher_number, v.title, v.amount, v.status, d.name AS department
  FROM expenditure_vouchers v
  JOIN departments d ON v.department_id = d.id
  WHERE v.status != 'PAID';

  -- Full audit trail
  SELECT a.created_at, u.full_name, u.role, a.action, a.entity, a.details
  FROM audit_logs a
  LEFT JOIN users u ON a.user_id = u.id
  ORDER BY a.created_at DESC;
  ```
- Export any table to CSV
- Edit records directly (useful for testing)
- View foreign key relationships

> **Note:** The `.gitignore` excludes `*.db` files from version control to protect member data. The database file is only on your local machine. Run `python3 seed.py` at any time to wipe and re-seed a clean copy.

---

## 7. Pre-Seeded Demo Accounts

All accounts use password: `password123`

| Name | Role | Email |
|---|---|---|
| Pr. David Ochieng | `PASTOR` | `pastor@churchconnect.ke` |
| Elder Samuel Omari | `FIRST_ELDER` | `elder.samuel@churchconnect.ke` |
| Grace Wanjiku | `HEAD_TREASURER` | `treasurer@churchconnect.ke` |
| Ruth Chebet | `CHURCH_CLERK` | `clerk@churchconnect.ke` |
| Kevin Mwangi | `DEPARTMENT_LEADER` | `youth.leader@churchconnect.ke` |
| John Kariuki | `MEMBER` | `john.k@gmail.com` |

### Seeded Data Summary
| Entity | Count |
|---|---|
| Users (officers + member) | 9 |
| Members (church roll) | 10 |
| Departments | 8 |
| Fund Categories | 9 |
| Tithe/Offering Envelopes | 6 |
| Expenditure Vouchers | 4 |
| Church Assets | 5 |
| Board Meetings | 1 |
| Resolutions | 3 |
| Announcements | 4 |
| Events | 3 |
| Attendance Records | 3 |

---

## 8. API Reference

### Authentication
| Method | Endpoint | Access | Description |
|---|---|---|---|
| `POST` | `/api/auth/register` | Public | Register new member account |
| `POST` | `/api/auth/login` | Public | Login, returns JWT token |
| `GET` | `/api/auth/me` | Any | Get current user profile |

### Dashboard
| Method | Endpoint | Access | Description |
|---|---|---|---|
| `GET` | `/api/dashboard/overview` | Any | Officer KPIs or Member giving summary |

### Treasury & Finance
| Method | Endpoint | Access | Description |
|---|---|---|---|
| `GET` | `/api/finance/fund-categories` | Any | List all fund categories |
| `GET` | `/api/finance/envelopes` | Officers | All tithe/offering envelopes |
| `POST` | `/api/finance/envelopes` | Treasurer, Pastor, Elder | Record new envelope |
| `POST` | `/api/finance/envelopes/<id>/reverse` | Treasurer, Pastor, Elder | Reverse a posted transaction |
| `GET` | `/api/finance/my-giving` | Any | Current user's personal giving history |
| `GET` | `/api/finance/members/<id>/contributions` | Treasurer+ | Member contribution summary |
| `GET` | `/api/finance/reports/sda-monthly` | Officers | SDA monthly treasury statement |

### Vouchers & Approvals
| Method | Endpoint | Access | Description |
|---|---|---|---|
| `GET` | `/api/finance/vouchers` | Officers | List all vouchers |
| `POST` | `/api/finance/vouchers` | Dept Leader, Treasurer, Pastor, Elder | Submit requisition |
| `POST` | `/api/finance/vouchers/<id>/treasurer-review` | Treasurer | Step 1 review |
| `POST` | `/api/finance/vouchers/<id>/elder-approve` | Pastor, Elder | Step 2 authorization |
| `POST` | `/api/finance/vouchers/<id>/committee-vote` | Pastor, Elder, Treasurer, Auditor | Committee vote |
| `POST` | `/api/finance/vouchers/<id>/disburse` | Treasurer | Final disbursement |
| `GET` | `/api/finance/approval-committees` | Any | List approval committees |

### Members & Departments
| Method | Endpoint | Access | Description |
|---|---|---|---|
| `GET` | `/api/members` | Any | Member directory (officers get full data) |
| `POST` | `/api/members` | Clerk, Pastor, Elder | Add new member |
| `GET` | `/api/departments` | Any | Departments (officers get budget data) |
| `GET` | `/api/officers` | Any | List all non-member active users |

### Assets, Meetings & Events
| Method | Endpoint | Access | Description |
|---|---|---|---|
| `GET` | `/api/assets` | Any | Church asset inventory |
| `POST` | `/api/assets` | Clerk, Treasurer, Pastor, Elder | Register new asset |
| `GET` | `/api/meetings` | Officers | Board minutes & resolutions |
| `POST` | `/api/meetings` | Pastor, Elder, Clerk | Record new meeting minutes |
| `GET` | `/api/events` | Any | Church calendar |
| `POST` | `/api/events` | Pastor, Elder, Clerk, Dept Leader | Schedule event |
| `GET` | `/api/attendance` | Any | Attendance records |
| `POST` | `/api/attendance` | Clerk, Pastor, Elder | Record attendance |

### Announcements
| Method | Endpoint | Access | Description |
|---|---|---|---|
| `GET` | `/api/announcements` | Any | Announcements (members get filtered view) |
| `POST` | `/api/announcements` | Officers | Post announcement |

### Accountability & Admin
| Method | Endpoint | Access | Description |
|---|---|---|---|
| `GET` | `/api/accountability/summary` | Officers | Accountability centre data |
| `GET` | `/api/audit-logs` | Officers | Immutable audit trail |
| `GET` | `/api/users` | Pastor | All users for role management |
| `PATCH` | `/api/users/<id>/role` | Pastor | Assign role to user |
| `GET` | `/api/admin/backup` | Pastor, Elder | Full database JSON backup |
| `POST` | `/api/mpesa/simulate` | Any | Simulate M-Pesa payment |
| `GET` | `/verify-receipt/<ref>` | Public | Verify digital receipt by receipt # or code |
| `GET` | `/health` | Public | Health check |

---

## 9. Database Schema

### 21 Tables

| Table | Purpose |
|---|---|
| `users` | Login accounts with role, bcrypt hash, lockout fields |
| `members` | Church membership roll with baptism, contact, department |
| `departments` | 8 church departments with budget allocation and spend tracking |
| `fund_categories` | 9 giving fund types (Tithe, Church Budget, Building Fund, etc.) |
| `tithe_offering_envelopes` | Every giving transaction with receipt number and verification code |
| `envelope_items` | Per-fund allocation lines within each envelope |
| `financial_reversals` | Immutable reversal records (transactions are never deleted) |
| `expenditure_vouchers` | Requisitions through the 4-step approval workflow |
| `approval_committees` | Named approval committees |
| `approval_committee_members` | Committee membership |
| `approval_rules` | Configurable approval thresholds |
| `approval_decisions` | Individual committee votes per voucher |
| `church_assets` | Property inventory with custodian, condition, cost |
| `meetings` | Board meeting records with minutes text |
| `resolutions` | Action resolutions attached to meetings |
| `announcements` | Church bulletin with audience targeting |
| `events` | Church calendar entries |
| `attendance` | Sabbath service headcounts |
| `audit_logs` | Immutable log of every system action |
| `payment_transactions` | M-Pesa and payment provider transaction records |
| `mpesa_transactions` | Safaricom Daraja callback records |

---

## 10. Project File Structure

```
CHURCHCONNECT.KE/
├── app.py                  # Flask application — all API routes
├── auth.py                 # JWT generation/verification, bcrypt helpers, audit log creator
├── database.py             # SQLite connection, schema init (CREATE TABLE IF NOT EXISTS)
├── seed.py                 # Wipe & re-seed database with full SDA demo data
├── requirements.txt        # Python dependencies
├── runtime.txt             # Python version pin (for Heroku/Render)
├── Procfile                # Gunicorn entry point for deployment
├── .env.example            # Environment variable template
├── .gitignore              # Excludes *.db, .env, __pycache__, dist/, node_modules/
├── README.md               # This file
├── DEPLOYMENT.md           # Cloud deployment guide
├── PROPOSAL.md             # Original project proposal
├── TASK.md                 # Development task tracker
├── templates/
│   └── index.html          # Single-page application shell (all sections + modals)
├── static/
│   ├── css/
│   │   └── style.css       # Full custom CSS (SDA blue/gold theme, responsive)
│   ├── js/
│   │   └── app.js          # Entire frontend engine (auth, routing, all section loaders)
│   └── img/
│       └── sda-logo.svg    # SDA flame logo
└── tests/
    └── test_*.py           # Unit & security tests (8 tests)
```

---

## 11. Environment Configuration

Copy `.env.example` to `.env` and configure:

```env
SECRET_KEY=your_long_random_secret_key_here
JWT_SECRET=your_long_random_jwt_secret_here
DATABASE_FILE=churchconnect.db
PORT=5000
FLASK_DEBUG=false
```

> Never commit `.env` to version control. It is excluded by `.gitignore`.

---

## 12. Running Tests

```bash
python3 -m unittest discover tests
```

The test suite covers:
- User registration with valid and invalid inputs
- Login success and failure
- Brute-force lockout after 5 attempts
- JWT token validation
- Role-based access control (403 on unauthorized endpoints)
- Member-only data isolation (members cannot see treasury totals)
- Separation of duties (self-approval blocked)
- Receipt verification endpoint

All 8 tests pass on a freshly seeded database.

---

## 13. Deployment

See [`DEPLOYMENT.md`](DEPLOYMENT.md) for full cloud deployment instructions (Render, Railway, Heroku).

Quick deploy to Render:
```bash
# Ensure Procfile exists:
# web: gunicorn app:app --bind 0.0.0.0:$PORT

# Set environment variables in Render dashboard:
# SECRET_KEY, DATABASE_FILE, FLASK_DEBUG=false
```

> SQLite is suitable for a single local church deployment. For multi-church or high-concurrency use, migrate to PostgreSQL by replacing `get_db_connection()` in `database.py` with a `psycopg2` connection pool.
