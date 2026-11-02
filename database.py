import sqlite3
import os
import hashlib
from datetime import datetime

DB_FILE = os.environ.get('DATABASE_FILE', os.path.join(os.path.dirname(__file__), 'churchconnect.db'))

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.executescript('''
    -- Users & Roles
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        phone TEXT,
        role TEXT NOT NULL DEFAULT 'MEMBER', -- CHURCH_ADMIN, PASTOR, FIRST_ELDER, AUTHORIZED_ELDER_READONLY, HEAD_TREASURER, ASSISTANT_TREASURER, CHURCH_CLERK, DEPARTMENT_LEADER, AUDITOR, MEMBER
        department_id TEXT,
        member_id TEXT,
        two_factor_enabled INTEGER NOT NULL DEFAULT 0,
        two_factor_secret TEXT,
        failed_attempts INTEGER NOT NULL DEFAULT 0,
        locked_until TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    -- Departments
    CREATE TABLE IF NOT EXISTS departments (
        id TEXT PRIMARY KEY,
        name TEXT UNIQUE NOT NULL,
        code TEXT UNIQUE NOT NULL,
        description TEXT,
        leader_id TEXT,
        budget_allocation REAL NOT NULL DEFAULT 0.0,
        budget_spent REAL NOT NULL DEFAULT 0.0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (leader_id) REFERENCES users(id) ON DELETE SET NULL
    );

    -- Members (Church Clerk Roll)
    CREATE TABLE IF NOT EXISTS members (
        id TEXT PRIMARY KEY,
        member_number TEXT UNIQUE NOT NULL,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        phone TEXT,
        email TEXT,
        gender TEXT NOT NULL,
        date_of_birth TEXT,
        baptism_date TEXT,
        baptism_church TEXT,
        status TEXT NOT NULL DEFAULT 'ACTIVE', -- ACTIVE, TRANSFERRED, INACTIVE, DECEASED
        emergency_contact_name TEXT,
        emergency_contact_phone TEXT,
        residence TEXT,
        department_id TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL
    );

    -- Fund Categories (SDA Sacred Trust Partitioning)
    CREATE TABLE IF NOT EXISTS fund_categories (
        id TEXT PRIMARY KEY,
        name TEXT UNIQUE NOT NULL,
        code TEXT UNIQUE NOT NULL,
        fund_type TEXT NOT NULL, -- CONFERENCE_TRUST, LOCAL_CHURCH
        is_remitted_to_conference INTEGER NOT NULL DEFAULT 0,
        description TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    -- Tithe & Offering Envelopes (Immutable Financial Records)
    CREATE TABLE IF NOT EXISTS tithe_offering_envelopes (
        id TEXT PRIMARY KEY,
        receipt_number TEXT UNIQUE NOT NULL,
        verification_code TEXT UNIQUE NOT NULL,
        member_id TEXT,
        donor_name TEXT,
        donor_phone TEXT,
        payment_method TEXT NOT NULL DEFAULT 'CASH', -- CASH, MPESA, BANK_TRANSFER, CHEQUE
        payment_status TEXT NOT NULL DEFAULT 'RECORDED', -- RECORDED, VERIFIED_PROVIDER, REVERSED
        mpesa_receipt_number TEXT,
        transaction_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        total_amount REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'CONFIRMED', -- CONFIRMED, REVERSED, VOID
        notes TEXT,
        recorded_by_id TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE SET NULL,
        FOREIGN KEY (recorded_by_id) REFERENCES users(id)
    );

    -- Envelope Line Items
    CREATE TABLE IF NOT EXISTS envelope_items (
        id TEXT PRIMARY KEY,
        envelope_id TEXT NOT NULL,
        fund_category_id TEXT NOT NULL,
        amount REAL NOT NULL,
        FOREIGN KEY (envelope_id) REFERENCES tithe_offering_envelopes(id) ON DELETE CASCADE,
        FOREIGN KEY (fund_category_id) REFERENCES fund_categories(id)
    );

    -- Financial Reversals (Integrity: Never delete posted transactions)
    CREATE TABLE IF NOT EXISTS financial_reversals (
        id TEXT PRIMARY KEY,
        envelope_id TEXT NOT NULL,
        reversal_reason TEXT NOT NULL,
        reversed_by_id TEXT NOT NULL,
        original_amount REAL NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (envelope_id) REFERENCES tithe_offering_envelopes(id),
        FOREIGN KEY (reversed_by_id) REFERENCES users(id)
    );

    -- Configurable Approval Committees
    CREATE TABLE IF NOT EXISTS approval_committees (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        min_quorum INTEGER NOT NULL DEFAULT 2,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    -- Approval Committee Members
    CREATE TABLE IF NOT EXISTS approval_committee_members (
        id TEXT PRIMARY KEY,
        committee_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        role_in_committee TEXT DEFAULT 'MEMBER', -- CHAIR, SECRETARY, MEMBER
        FOREIGN KEY (committee_id) REFERENCES approval_committees(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    -- Approval Rules & Thresholds
    CREATE TABLE IF NOT EXISTS approval_rules (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        min_amount REAL NOT NULL DEFAULT 0.0,
        max_amount REAL, -- NULL means unbounded
        committee_id TEXT,
        requires_elder_quorum INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (committee_id) REFERENCES approval_committees(id)
    );

    -- Expenditure Requisition Vouchers
    CREATE TABLE IF NOT EXISTS expenditure_vouchers (
        id TEXT PRIMARY KEY,
        voucher_number TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        department_id TEXT NOT NULL,
        requested_by_id TEXT NOT NULL,
        amount REAL NOT NULL,
        payee_name TEXT NOT NULL,
        payee_phone TEXT,
        status TEXT NOT NULL DEFAULT 'SUBMITTED', -- DRAFT, SUBMITTED, TREASURER_REVIEWED, IN_COMMITTEE_REVIEW, ELDER_APPROVED, REJECTED, PAID
        treasurer_reviewed_by_id TEXT,
        treasurer_reviewed_at TEXT,
        treasurer_notes TEXT,
        elder_approved_by_id TEXT,
        elder_approved_at TEXT,
        elder_notes TEXT,
        rejection_reason TEXT,
        payment_method TEXT DEFAULT 'MPESA',
        payment_reference TEXT,
        paid_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (department_id) REFERENCES departments(id),
        FOREIGN KEY (requested_by_id) REFERENCES users(id),
        FOREIGN KEY (treasurer_reviewed_by_id) REFERENCES users(id),
        FOREIGN KEY (elder_approved_by_id) REFERENCES users(id)
    );

    -- Committee Decisions & Voting Records (Separation of duties & accountability)
    CREATE TABLE IF NOT EXISTS approval_decisions (
        id TEXT PRIMARY KEY,
        voucher_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        decision TEXT NOT NULL, -- APPROVE, REJECT, REQUEST_REVISION
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (voucher_id) REFERENCES expenditure_vouchers(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(id),
        UNIQUE(voucher_id, user_id)
    );

    -- Events & Calendar
    CREATE TABLE IF NOT EXISTS events (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        description TEXT,
        department_id TEXT,
        coordinator_id TEXT,
        location TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        is_public INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL,
        FOREIGN KEY (coordinator_id) REFERENCES users(id) ON DELETE SET NULL
    );

    -- Attendance
    CREATE TABLE IF NOT EXISTS attendance (
        id TEXT PRIMARY KEY,
        service_type TEXT NOT NULL,
        date TEXT NOT NULL,
        adult_count INTEGER NOT NULL DEFAULT 0,
        children_count INTEGER NOT NULL DEFAULT 0,
        visitors_count INTEGER NOT NULL DEFAULT 0,
        total_count INTEGER NOT NULL DEFAULT 0,
        notes TEXT,
        recorded_by_id TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (recorded_by_id) REFERENCES users(id)
    );

    -- Announcements
    CREATE TABLE IF NOT EXISTS announcements (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'GENERAL',
        target_audience TEXT NOT NULL DEFAULT 'ALL',
        author_id TEXT NOT NULL,
        is_pinned INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (author_id) REFERENCES users(id)
    );

    -- Church Assets & Inventory
    CREATE TABLE IF NOT EXISTS church_assets (
        id TEXT PRIMARY KEY,
        asset_tag TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        category TEXT NOT NULL, -- SOUND_EQUIPMENT, FURNITURE, INSTRUMENT, COMPUTER, VEHICLE, SANCTUARY
        quantity INTEGER NOT NULL DEFAULT 1,
        location TEXT NOT NULL,
        condition TEXT NOT NULL DEFAULT 'GOOD', -- EXCELLENT, GOOD, FAIR, NEEDS_REPAIR
        custodian_id TEXT,
        purchase_date TEXT,
        purchase_cost REAL DEFAULT 0.0,
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (custodian_id) REFERENCES users(id) ON DELETE SET NULL
    );

    -- Meeting Minutes & Resolutions
    CREATE TABLE IF NOT EXISTS meetings (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        meeting_type TEXT NOT NULL, -- ELDERS_COUNCIL, CHURCH_BOARD, BUSINESS_MEETING, DEPARTMENTAL
        date TEXT NOT NULL,
        chairperson_id TEXT,
        secretary_id TEXT,
        minutes_text TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (chairperson_id) REFERENCES users(id),
        FOREIGN KEY (secretary_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS resolutions (
        id TEXT PRIMARY KEY,
        meeting_id TEXT NOT NULL,
        resolution_number TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        assigned_officer_id TEXT,
        status TEXT NOT NULL DEFAULT 'IN_PROGRESS', -- PENDING, IN_PROGRESS, COMPLETED
        due_date TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE,
        FOREIGN KEY (assigned_officer_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS meeting_access_grants (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        granted_by_id TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (granted_by_id) REFERENCES users(id),
        UNIQUE(user_id)
    );

    -- Payment Transactions (M-Pesa, Bank, Cheque tracking)
    CREATE TABLE IF NOT EXISTS payment_transactions (
        id TEXT PRIMARY KEY,
        provider TEXT NOT NULL DEFAULT 'MPESA', -- MPESA, BANK_TRANSFER, CHEQUE
        reference TEXT UNIQUE NOT NULL,
        amount REAL NOT NULL,
        account_ref TEXT,
        phone TEXT,
        status TEXT NOT NULL DEFAULT 'CONFIRMED', -- PENDING, CONFIRMED, RECONCILED, DUPLICATE_FLAGGED
        reconciled_with_envelope_id TEXT,
        raw_payload TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    -- Immutable Audit Logs
    CREATE TABLE IF NOT EXISTS audit_logs (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        action TEXT NOT NULL,
        entity TEXT NOT NULL,
        entity_id TEXT,
        details TEXT,
        ip_address TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS church_documents (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'GENERAL',
        description TEXT,
        file_content TEXT,
        file_type TEXT DEFAULT 'TEXT',
        audience TEXT NOT NULL DEFAULT 'OFFICERS',
        uploaded_by_id TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (uploaded_by_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS departmental_activities (
        id TEXT PRIMARY KEY,
        department_id TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        activity_date TEXT NOT NULL,
        participants_count INTEGER DEFAULT 0,
        outcome TEXT,
        recorded_by_id TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (department_id) REFERENCES departments(id),
        FOREIGN KEY (recorded_by_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS member_status_history (
        id TEXT PRIMARY KEY,
        member_id TEXT NOT NULL,
        old_status TEXT,
        new_status TEXT NOT NULL,
        reason TEXT,
        changed_by_id TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE,
        FOREIGN KEY (changed_by_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS notifications (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        type TEXT NOT NULL DEFAULT 'INFO',
        is_read INTEGER NOT NULL DEFAULT 0,
        related_entity TEXT,
        related_entity_id TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    ''')

    # Safe column migrations if database already existed
    columns_to_add = [
        ("users", "member_id", "TEXT"),
        ("users", "two_factor_enabled", "INTEGER NOT NULL DEFAULT 0"),
        ("users", "two_factor_secret", "TEXT"),
        ("users", "failed_attempts", "INTEGER NOT NULL DEFAULT 0"),
        ("users", "locked_until", "TEXT"),
        ("tithe_offering_envelopes", "verification_code", "TEXT"),
        ("tithe_offering_envelopes", "payment_status", "TEXT NOT NULL DEFAULT 'RECORDED'")
    ]
    for table, col, col_type in columns_to_add:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type};")
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()

def generate_verification_code(receipt_num, total_amt, timestamp_str):
    salt = "CCK_SECURE_VERIFY_SALT_2026"
    raw = f"{receipt_num}-{total_amt}-{timestamp_str}-{salt}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16].upper()

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully at", DB_FILE)
