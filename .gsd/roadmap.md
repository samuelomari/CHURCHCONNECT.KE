# GSD Roadmap: ChurchConnect Kenya

## Objective
Build **ChurchConnect Kenya**, a complete Church Management and Financial Accountability System tailored for local Seventh-day Adventist (SDA) churches in Kenya using **HTML, CSS, JavaScript, and Python**.

## Key Pillars
1. **SDA Church Financial Governance**:
   - Strict fund separation: Tithe & Conference Trust Funds (100% remitted to local Conference/Field) vs Local Church Budget & Designated Offerings.
   - Dual-authorization expenditure vouchers: Requisition by Department Leader -> Review by Treasurer -> Authorization by First Elder / Pastor -> Payout disbursement.
   - Immutable audit logging for every financial and administrative action.
2. **Kenyan Financial Context**:
   - Multi-channel receipts: Cash, Bank deposit slips, and Safaricom M-Pesa.
   - Daraja STK Push & C2B simulation endpoints for real-time mobile money recording.
3. **Clean Architecture**:
   - Backend: Python 3 with Flask, SQLite / MySQL compatibility, PyJWT, and bcrypt.
   - Frontend: Modern, responsive HTML5, CSS3, and JavaScript with responsive charts, interactive modals, and real-time status indicators.
   - Zero runtime friction: works out of the box with standard Python 3.
