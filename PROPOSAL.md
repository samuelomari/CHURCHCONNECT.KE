# ChurchConnect Kenya
## A Church Management and Financial Accountability System
### Project Proposal for Church Elders and Church Leadership

**Prepared by:** Samuel Omari (`samuel.omari@student.moringaschool.com`)  
**Project Name:** ChurchConnect Kenya  
**Proposed Implementation:** Initially for one local Seventh-day Adventist Church  
**Proposed Technology:** React, Node.js, TypeScript, Express, MySQL (Prisma ORM), Tailwind CSS, Recharts  

---

## 1. Introduction
ChurchConnect Kenya is a digital platform designed to improve how our local church manages its administrative activities, financial records, departments, membership information, and church events.

As church activities grow, keeping records using notebooks, spreadsheets, and separate documents can become challenging. Important information may be difficult to retrieve, financial reports may take time to prepare, and tracking departmental activities and expenditure can become complicated.

ChurchConnect Kenya aims to provide one secure, centralized platform where authorized church leaders can manage these activities more efficiently.

The purpose is not to replace existing church leadership structures or financial policies. Instead, it is to give church leaders better tools to perform their responsibilities and strengthen accountability.

---

## 2. The Problem We Want to Address
Church administration involves many responsibilities, including:
- Recording tithes and offerings.
- Tracking church income and expenditure.
- Managing departmental budgets.
- Recording membership information.
- Monitoring departmental activities.
- Organizing church events and attendance.
- Preparing financial and administrative reports.

When these records are maintained across different books, spreadsheets, or individual devices, several challenges arise:
1. **Fragmented records:** Information is stored in different places, making it difficult to access.
2. **Time-consuming reporting:** Preparing financial and departmental reports requires considerable manual work.
3. **Limited financial visibility:** Church leadership may find it difficult to get an up-to-date overview of income, expenditure, and available budgets.
4. **Accountability challenges:** Tracking who recorded, approved, or updated a transaction can be difficult without a proper audit trail.
5. **Administrative workload:** Church clerks, treasurers, and department leaders spend unnecessary time organizing records.

ChurchConnect Kenya is intended to address these challenges through a centralized digital solution.

---

## 3. Proposed Solution
ChurchConnect Kenya will be developed as a secure, web-based church management system. The platform will provide authorized church leaders with access to relevant information based on their responsibilities.

The system will initially serve one local church, with the architectural possibility of expanding to support additional churches in the future.

### Main Feature Modules
#### A. Financial Management
- Record tithes and offerings (categorized per SDA policy).
- Support manual recording of cash and other approved payment methods.
- Provide a foundation for Safaricom M-Pesa Daraja API integration.
- Record church expenditures and departmental budget allocations.
- Track departmental budgets and spending against allocations.
- Generate daily, monthly, and annual financial statements and summaries.
- Maintain records of approvals and financial transactions.

#### B. Department Management
- Register church departments (e.g., Youth Ministries, Sabbath School, Women's Ministries, Men's Ministries, Children's Ministries, Personal Ministries, Stewardship, Communication, etc.).
- Assign department leaders.
- Record departmental activities, meetings, and calendar events.
- Monitor departmental budgets and track expenditures.

#### C. Membership Management
- Register church members with relevant demographic and contact details.
- Maintain baptismal/membership status, transfer status, and dates.
- Search, filter, and retrieve member profiles.
- Associate members with church departments and committees.

#### D. Events and Attendance
- Create church events, services, and special programmes.
- Record member and visitor attendance.
- Assign event coordinators and track logistical needs.
- Maintain event histories and attendance reporting.

#### E. Announcements and Documents
- Publish announcements targeted to leaders or congregation.
- Securely store relevant church documents, board meeting minutes, and administrative policies.

#### F. Reports and Executive Dashboard
- Unified executive dashboard with key KPIs:
  - Financial summaries (Tithes, Combined Budget Offerings, Trust Funds).
  - Departmental budget performance and burn-rate.
  - Upcoming events and Sabbath schedules.
  - Membership demographics and attendance statistics.

---

## 4. Financial Accountability and Transparency
Financial accountability is a primary cornerstone of ChurchConnect Kenya.
The system is designed to support responsible stewardship and respect the established financial policies of the Seventh-day Adventist Church.

The system will:
- Strictly separate **tithe**, **conference trust funds**, and **local church combined budget/offerings** as per SDA Church Manual guidelines.
- Maintain an immutable audit trail of every financial transaction (creator, timestamp, approver, reason, amounts).
- Enforce dual-control / role-based approval workflows for expenditure requests.
- Provide automated reconciliation tools for cash receipts and digital M-Pesa transactions.
- Generate standard financial reporting packages for church business meetings and audit committees.

---

## 5. User Roles and Role-Based Access Control (RBAC)
Access is strictly partitioned according to ecclesiastical responsibilities:
- **Church Administrator:** System configuration, user account provisioning, role management.
- **Pastor:** Oversight of membership spiritual care, events, high-level dashboards, general announcements.
- **Church Treasurer & Assistant Treasurer:** Tithe & offering entry, banking slips, budget management, expenditure vouchers, financial reporting.
- **Church Clerk:** Membership records, transfer letters, board minutes, church registers, attendance stats.
- **Department Leaders:** Departmental planning, activity logs, budget requisition requests, member roster within department.
- **Auditor / Church Board:** Read-only access to audit logs, ledger reports, and verification dashboards.

---

## 6. Proposed Technology Stack
| Layer | Technology |
|---|---|
| **Frontend** | React 18+, TypeScript, Tailwind CSS, Lucide Icons |
| **Data Visualization** | Recharts |
| **Backend API** | Node.js, Express, TypeScript |
| **Database** | MySQL (with SQLite option for zero-dependency local prototyping) |
| **ORM** | Prisma ORM |
| **Authentication** | JWT, bcrypt password hashing, RBAC middleware |
| **Payment Integration** | Safaricom M-Pesa Daraja API (C2B / STK Push) |

---

## 7. Implementation Roadmap
- **Phase 1: Planning & Architecture Definition** (Schema design, RBAC matrix, proposal acceptance).
- **Phase 2: Core Foundation & Scaffold** (Express backend, React frontend, database migrations, authentication).
- **Phase 3: Membership & Department Modules** (Clerk register, Department roster, activity tracking).
- **Phase 4: Financial Management & SDA Fund Accounting** (Tithe/Offering entry, voucher approval workflow, budget tracking).
- **Phase 5: Events, Reports, M-Pesa & Security Audit** (Daraja integration sandbox, PDF/Excel export, audit trail).
