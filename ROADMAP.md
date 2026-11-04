# ChurchConnect Kenya Product Roadmap

## Vision
ChurchConnect Kenya is a secure church operations platform designed to support stewardship, administration, pastoral care, member engagement, and accountability. The system should help churches manage people, finance, decisions, and ministry activities in a way that is trusted, secure, and scalable.

## Guiding principles
- Keep the first release focused and practical.
- Prioritize trust, accountability, and security.
- Design for modular feature growth.
- Respect role-based access controls and privacy boundaries.
- Add automation and AI only after governance controls are in place.

---

## Official roadmap direction
The following feature groups were selected as the long-term strategic direction for ChurchConnect:

- Advanced finance and accounting
- Pastoral care and prayer requests
- Member engagement and Bible study
- Leadership, meetings and committees
- Assets, suppliers and inventory
- AI assistant and analytics
- Communication and media library
- Include all of these in the long-term vision

This means the product should expand beyond membership records into a practical church operations platform without losing focus on the first working release.

---

## Phase 1: Core operational foundation
This should remain the primary release focus.

### 1. Advanced finance and accounting
- Financial forecasting
- Budget planning and variance tracking
- Bank statement reconciliation
- Purchase order management
- Supplier management
- Invoice and payment tracking
- Project-based financial tracking
- Unusual transaction alerts
- Financial document archive

### 2. Membership and church administration
- Membership lifecycle management
- Church organizational structure
- Department leadership and reporting
- Role-based access control
- Member records and privacy boundaries
- Committee involvement tracking

### 3. Approval and accountability
- Multi-step financial approval workflows
- Decision tracking and evidence capture
- Financial period locking
- Audit logs and accountability history
- Two-person financial control for sensitive actions
- Digital approval signatures

### 4. Receipts, giving and stewardship
- Tithe and offering records
- Personal giving history
- Receipts and verification
- Secure financial dashboards
- Financial document linkage

---

## Phase 2: Pastoral care and community support
These features improve church health and pastoral responsiveness.

### 5. Pastoral care and follow-up
- Visit scheduling
- Follow-up assignment
- Care tracking and escalation
- Private pastoral notes with restricted access

### 6. Prayer and member support
- Prayer request centre
- Privacy controls for sensitive requests
- Prayer team assignment and follow-up
- Support for pastoral response tracking

### 7. Visitor management
- First-time visitor registration
- Follow-up assignment
- Contact preferences and welcome teams
- Newcomer tracking and response

### 8. Volunteer management
- Volunteer availability
- Scheduling and duty assignment
- Replacement planning
- Ministry coordination support

---

## Phase 3: Leadership, communication and ministry
This phase broadens ChurchConnect into a fuller ministry platform.

### 9. Leadership and meetings
- Committee action tracker
- Meeting decisions and assigned tasks
- Ownership and deadline tracking
- Status and completion evidence

### 10. Communication and announcements
- Church announcements
- Department updates
- Multi-language messaging for key communications
- Member-facing information channels

### 11. Sermon and media library
- Sermon recordings
- Study resources and materials
- Searchable categories and archiving
- Approved media sharing

### 12. Bible study and small group management
- Small group organization
- Prayer groups and study groups
- Attendance tracking
- Group leader assignment

### 13. Annual church programme planning
- Annual ministry calendar
- Event coordination
- Department schedules
- Program planning and oversight

---

## Phase 4: Governance, security and long-term intelligence
These should be introduced only after core trust controls are mature.

### 14. Security and governance
- Emergency access control
- Data export approval
- Login device management
- Active session visibility and revocation
- Data retention management
- Backup and disaster recovery procedures
- Privacy access history
- Security incident reporting

### 15. AI and analytics
- AI church report assistant
- Natural-language search for leadership reporting
- Trend analysis for attendance, giving, and ministry activity
- Leadership summary generation
- Multi-language support in reporting and communication

### 16. Asset and inventory management
- Church property tracking
- Equipment assignment
- Maintenance records
- Supplier and asset lifecycle management

### 17. Safeguarding and sensitive case management
- Incident recording
- Escalation pathways
- Restricted access to sensitive records
- Confidential pastoral and safeguarding workflows

---

## Top 12 recommended feature additions
These are the highest-priority additions to consider for long-term product value:

1. Financial forecasting
2. Purchase orders
3. Bank reconciliation
4. Supplier management
5. Committee action tracker
6. Pastoral follow-up
7. Visitor management
8. Prayer request centre
9. Sermon and media library
10. Asset management
11. Offline attendance
12. AI report assistant

These features deliver strong operational value while supporting long-term church growth and accountability.

---

## Recommended release strategy

### First release (v1): focused and deployable
The first version should focus on:
- finance and receipts
- approvals and accountability
- membership management
- department leadership and structure
- secure role-based access
- audit trails and financial controls

### Next release: pastoral care and communication
- visitor follow-up
- prayer requests
- pastoral care tracking
- volunteer scheduling
- announcements and ministry communication

### Later release: intelligence and expansion
- AI reporting
- forecasting and analytics
- asset management
- inventory and supply tracking
- multi-language features and more advanced automation

---

## Important architectural decision
Since the project is using React, TypeScript, Node.js, Express, Prisma and MySQL, the platform should be built as a modular application with clear feature boundaries.

```text
churchconnect-kenya/
│
├── client/
│   └── src/
│       └── features/
│           ├── authentication/
│           ├── finance/
│           ├── members/
│           ├── departments/
│           ├── approvals/
│           ├── receipts/
│           ├── events/
│           ├── pastoral-care/
│           ├── inventory/
│           ├── communication/
│           └── analytics/
│
├── server/
│   └── src/
│       └── modules/
│           ├── auth/
│           ├── users/
│           ├── finance/
│           ├── members/
│           ├── departments/
│           ├── approvals/
│           ├── receipts/
│           ├── events/
│           ├── pastoral-care/
│           ├── inventory/
│           ├── communication/
│           └── analytics/
│
└── prisma/
    └── schema.prisma
```

This structure keeps features independent enough to evolve without rewriting the entire platform.

---

## Final strategic summary
The strongest long-term direction is to keep the first version focused on finance, approvals, membership, departments, and auditability. Once that foundation is reliable, the church can expand into pastoral care, communication, media, volunteer management, and AI-driven insights.

This ensures ChurchConnect remains useful, trusted, and practical for church leadership while still leaving room for meaningful growth.
