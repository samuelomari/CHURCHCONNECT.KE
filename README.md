# ChurchConnect Kenya
### A Church Management and Financial Accountability System
**Prepared by:** Samuel Omari (`samuel.omari@student.moringaschool.com`)  
**Target Organization:** Seventh-day Adventist (SDA) Local Church (East Kenya Union Conference / Central Kenya Conference)  
**Technology Stack:** Python 3 (Flask), HTML5, CSS3, Modern JavaScript (ES6+), SQLite, Safaricom M-Pesa Daraja API, Chart.js

---

## 1. Security Architecture & Login Protection

### A. Mandatory Authentication Wall
- The entire system is protected by a login wall. No unauthorized user can access the dashboard, statistics, or administrative tools without valid credentials.
- Automatic session verification via JWT tokens stored securely on the client.
- Distinct sign-out functionality that clears the user session and returns to the login screen.

### B. Robust Security & Password Protection
- **Bcrypt Password Hashing**: Passwords are cryptographically salted and hashed before database storage.
- **Strict Email Validation**: All registrations enforce a valid email pattern (`^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$`).
- **Password Complexity**: Requires a minimum of 8 characters containing uppercase letters, lowercase letters, and digits.
- **Brute-Force Account Lockout**: After 5 consecutive failed login attempts, the account is temporarily locked for 15 minutes.

### C. Public & Git Privacy Protection
- A comprehensive [`.gitignore`](file:///home/samuel-omari/CHURCHCONNECT.KE/.gitignore) is configured to prevent development and build artifacts (database files `*.db`, secrets `.env`, cache `__pycache__/`, `dist/`, `node_modules/`, etc.) from being exposed in public version control.

---

## 2. Member Portal vs. Officer Executive Portal

The system provides separate experiences based on church responsibility:

### 1. Registered Church Member Portal (`role: 'MEMBER'`)
Church members can register online and access **non-confidential** church life:
- **My Home**: Welcome message, scripture verse of the week, announcements summary, upcoming Sabbath worship schedule.
- **Announcements**: Full church bulletin, worship schedules, department notices, and prayer requests.
- **Church Calendar & Events**: Divine Service, Youth concerts, Camp Meeting schedules, and fellowship lunches.
- **My Giving History**: View and verify **only their own** tithe and offering receipts (keeps personal giving completely private without exposing other members' envelopes).
- **Give via M-Pesa**: Direct mobile money giving via Paybill `174379` with instant church receipt generation.
- **Church Ministries**: General department directory and leader contacts.
- **Confidential Information Blocked**: Members are strictly blocked with `403 Forbidden` from viewing church treasury totals, expenditure vouchers, other members' personal records, and audit logs.

### 2. Church Officers & Board Portal (`PASTOR`, `FIRST_ELDER`, `HEAD_TREASURER`, `CHURCH_CLERK`, `AUDITOR`)
Authorized church leadership accesses the full financial accountability engine:
- Sacred trust partitioning: Holy Tithe (100% Conference remittance) vs. Local Church Budget.
- Multi-step expenditure voucher approval (Requisition -> Treasurer Review -> Elder Authorization -> Payout).
- Full membership roll, baptism records, attendance logs, and immutable audit logs.
- Official SDA Monthly Treasury Statement generator.

---

## 3. Quick Start & Execution

```bash
# 1. Initialize and seed database with sample SDA church data
python3 seed.py

# 2. Start the web application
python3 app.py
```
Open your web browser and navigate to:
```
http://localhost:5000
```

### Pre-Seeded Accounts for Testing

On the login page, you can use the **Quick Demo Sign-In** buttons to test both Officer and Member roles:

| Persona | Church Role | Email | Password |
|---|---|---|---|
| **Pr. David Ochieng** | Pastor | `pastor@churchconnect.ke` | `password123` |
| **Elder Samuel Omari** | First Elder | `elder.samuel@churchconnect.ke` | `password123` |
| **Grace Wanjiku** | Head Treasurer | `treasurer@churchconnect.ke` | `password123` |
| **Ruth Chebet** | Church Clerk | `clerk@churchconnect.ke` | `password123` |
| **Kevin Mwangi** | Youth Leader | `youth.leader@churchconnect.ke` | `password123` |
| **John Kariuki** | Registered Member | `john.k@gmail.com` | `password123` |

You can also click the **"Register as Member"** tab to register any new member with a valid email address!

### Run Automated Tests
```bash
python3 -m unittest discover tests
```
*All 8 unit & security tests pass automatically.*
