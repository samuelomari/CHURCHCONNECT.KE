import uuid
import datetime
from database import get_db_connection, init_db, generate_verification_code
from auth import hash_password

def seed_database():
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()

    tables = [
        'audit_logs', 'payment_transactions', 'resolutions', 'meetings',
        'church_assets', 'approval_decisions', 'approval_rules',
        'approval_committee_members', 'approval_committees', 'financial_reversals',
        'attendance', 'announcements', 'media_library', 'events', 'envelope_items',
        'tithe_offering_envelopes', 'expenditure_vouchers',
        'pastoral_followups', 'visitor_registrations', 'prayer_requests',
        'members', 'departments', 'fund_categories', 'users'
    ]
    for table in tables:
        cursor.execute(f"DELETE FROM {table}")

    print("Seeding ChurchConnect Kenya (SDA Local Church Security Edition v1.1)...")

    # 1. Users
    pw = hash_password("password123")
    
    users = [
        {"id": "usr-pastor", "email": "pastor@churchconnect.ke", "name": "Pr. David Ochieng", "phone": "254711000002", "role": "PASTOR", "tfa": 1},
        {"id": "usr-elder", "email": "elder.samuel@churchconnect.ke", "name": "Elder Samuel Omari", "phone": "254722000003", "role": "FIRST_ELDER", "tfa": 1},
        {"id": "usr-elder-ro", "email": "elder.joshua@churchconnect.ke", "name": "Elder Joshua Mwiti", "phone": "254722000099", "role": "AUTHORIZED_ELDER_READONLY", "tfa": 0},
        {"id": "usr-treasurer", "email": "treasurer@churchconnect.ke", "name": "Grace Wanjiku", "phone": "254733000004", "role": "HEAD_TREASURER", "tfa": 1},
        {"id": "usr-asst-treasurer", "email": "asst.treasurer@churchconnect.ke", "name": "Brian Kiprop", "phone": "254744000005", "role": "ASSISTANT_TREASURER", "tfa": 0},
        {"id": "usr-clerk", "email": "clerk@churchconnect.ke", "name": "Ruth Chebet", "phone": "254755000006", "role": "CHURCH_CLERK", "tfa": 0},
        {"id": "usr-youth-lead", "email": "youth.leader@churchconnect.ke", "name": "Kevin Mwangi", "phone": "254766000007", "role": "DEPARTMENT_LEADER", "tfa": 0},
        {"id": "usr-auditor", "email": "auditor@churchconnect.ke", "name": "Silas Mutua", "phone": "254777000008", "role": "AUDITOR", "tfa": 1},
    ]

    for u in users:
        cursor.execute('''
            INSERT INTO users (id, email, password_hash, full_name, phone, role, two_factor_enabled, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        ''', (u["id"], u["email"], pw, u["name"], u["phone"], u["role"], u["tfa"]))

    # 2. Departments
    departments = [
        {"id": "dept-ay", "name": "Adventist Youth (AY)", "code": "AY", "desc": "Youth ministries, camporees and outreach", "leader_id": "usr-youth-lead", "budget": 120000.0, "spent": 45000.0},
        {"id": "dept-ss", "name": "Sabbath School & Personal Ministries", "code": "SSPM", "desc": "Lesson study and community soul winning", "leader_id": None, "budget": 90000.0, "spent": 30000.0},
        {"id": "dept-wm", "name": "Women's Ministries", "code": "WM", "desc": "Dorcas society and women nurture", "leader_id": None, "budget": 80000.0, "spent": 15000.0},
        {"id": "dept-amo", "name": "Adventist Men's Organization", "code": "AMO", "desc": "Men fellowship and mentorship", "leader_id": None, "budget": 75000.0, "spent": 12000.0},
        {"id": "dept-chm", "name": "Children's Ministries", "code": "CHM", "desc": "VBS, branch sabbath schools, children nurture", "leader_id": None, "budget": 60000.0, "spent": 18000.0},
        {"id": "dept-stew", "name": "Stewardship & Development", "code": "STEW", "desc": "Tithe education and church development", "leader_id": None, "budget": 50000.0, "spent": 5000.0},
        {"id": "dept-music", "name": "Music & Choir", "code": "MUSIC", "desc": "Sanctuary choir and praise teams", "leader_id": None, "budget": 70000.0, "spent": 22000.0},
        {"id": "dept-welfare", "name": "Deaconry & Welfare", "code": "WELFARE", "desc": "Sanctuary upkeep and benevolent fund", "leader_id": None, "budget": 110000.0, "spent": 38000.0},
    ]

    for d in departments:
        cursor.execute('''
            INSERT INTO departments (id, name, code, description, leader_id, budget_allocation, budget_spent)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (d["id"], d["name"], d["code"], d["desc"], d["leader_id"], d["budget"], d["spent"]))


    cursor.execute("UPDATE users SET department_id = 'dept-ay' WHERE id = 'usr-youth-lead'")

    # 3. Fund Categories (SDA Sacred Trust Partitioning)
    fund_categories = [
        {"id": "fund-tithe", "name": "Tithe", "code": "TITHE", "type": "CONFERENCE_TRUST", "remit": 1, "desc": "Holy Tithe (10% holy unto God - 100% remitted to Central Kenya Conference)"},
        {"id": "fund-camp", "name": "Camp Meeting Offering", "code": "CAMP_MEETING", "type": "CONFERENCE_TRUST", "remit": 1, "desc": "Annual camp meeting thanksgiving offering for the Conference"},
        {"id": "fund-world", "name": "World Mission Budget", "code": "WORLD_MISSION", "type": "CONFERENCE_TRUST", "remit": 1, "desc": "General Conference world evangelism offerings"},
        {"id": "fund-budget", "name": "Combined Church Budget", "code": "CHURCH_BUDGET", "type": "LOCAL_CHURCH", "remit": 0, "desc": "Local church utilities, janitorial, pastoral support and maintenance"},
        {"id": "fund-building", "name": "Sanctuary Building Fund", "code": "BUILDING_FUND", "type": "LOCAL_CHURCH", "remit": 0, "desc": "Local church sanctuary expansion and capital development"},
        {"id": "fund-youth", "name": "Adventist Youth Allocation", "code": "AY_FUND", "type": "LOCAL_CHURCH", "remit": 0, "desc": "Youth retreats, pathfinder uniforms, and mission projects"},
        {"id": "fund-welfare", "name": "Welfare / Needy Assistance", "code": "WELFARE_FUND", "type": "LOCAL_CHURCH", "remit": 0, "desc": "Emergency aid for bereaved or hospital-bound church members"},
        {"id": "fund-evangelism", "name": "Evangelism & Media", "code": "EVANGELISM", "type": "LOCAL_CHURCH", "remit": 0, "desc": "Live broadcast equipment, public gospel crusades, tracts"},
        {"id": "fund-music", "name": "Music & Choir Fund", "code": "MUSIC_FUND", "type": "LOCAL_CHURCH", "remit": 0, "desc": "Music instruments and choir uniforms"},
    ]

    for f in fund_categories:
        cursor.execute('''
            INSERT INTO fund_categories (id, name, code, fund_type, is_remitted_to_conference, description, active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        ''', (f["id"], f["name"], f["code"], f["type"], f["remit"], f["desc"]))

    # 4. Church Members
    members = [
        {"id": "mem-001", "num": "SDA-2023-001", "fn": "John", "ln": "Kariuki", "phone": "254710111222", "email": "john.k@gmail.com", "gender": "MALE", "bap_date": "2015-08-22", "church": "Nairobi Central SDA", "status": "ACTIVE", "dept": "dept-ay"},
        {"id": "mem-002", "num": "SDA-2023-002", "fn": "Esther", "ln": "Akinyi", "phone": "254720222333", "email": "esther.akinyi@yahoo.com", "gender": "FEMALE", "bap_date": "2018-04-14", "church": "Newlife SDA Church", "status": "ACTIVE", "dept": "dept-wm"},
        {"id": "mem-003", "num": "SDA-2023-003", "fn": "Peter", "ln": "Kiprono", "phone": "254730333444", "email": "kiprono.p@gmail.com", "gender": "MALE", "bap_date": "2012-11-03", "church": "Eldoret Central SDA", "status": "ACTIVE", "dept": "dept-amo"},
        {"id": "mem-004", "num": "SDA-2023-004", "fn": "Mercy", "ln": "Wambui", "phone": "254740444555", "email": "mercy.wambui@outlook.com", "gender": "FEMALE", "bap_date": "2020-09-19", "church": "Nairobi Central SDA", "status": "ACTIVE", "dept": "dept-music"},
        {"id": "mem-005", "num": "SDA-2023-005", "fn": "Daniel", "ln": "Mogaka", "phone": "254750555666", "email": "dmogaka@gmail.com", "gender": "MALE", "bap_date": "2016-03-26", "church": "Kisii Central SDA", "status": "ACTIVE", "dept": "dept-stew"},
        {"id": "mem-006", "num": "SDA-2023-006", "fn": "Sarah", "ln": "Mutiso", "phone": "254760666777", "email": "sarah.m@gmail.com", "gender": "FEMALE", "bap_date": "2021-12-11", "church": "Machakos Town SDA", "status": "ACTIVE", "dept": "dept-chm"},
        {"id": "mem-007", "num": "SDA-2023-007", "fn": "Paul", "ln": "Otieno", "phone": "254770777888", "email": "paul.otieno@gmail.com", "gender": "MALE", "bap_date": "2019-07-06", "church": "Kendu Bay SDA", "status": "ACTIVE", "dept": "dept-ss"},
        {"id": "mem-008", "num": "SDA-2023-008", "fn": "Faith", "ln": "Cherono", "phone": "254780888999", "email": "faith.cherono@gmail.com", "gender": "FEMALE", "bap_date": "2022-02-19", "church": "Kericho SDA", "status": "ACTIVE", "dept": "dept-ay"},
    ]

    for m in members:
        cursor.execute('''
            INSERT INTO members (id, member_number, first_name, last_name, phone, email, gender, baptism_date, baptism_church, status, department_id, residence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Nairobi')
        ''', (m["id"], m["num"], m["fn"], m["ln"], m["phone"], m["email"], m["gender"], m["bap_date"], m["church"], m["status"], m["dept"]))

    # John Kariuki registered member user
    cursor.execute('''
        INSERT INTO users (id, email, password_hash, full_name, phone, role, member_id, active)
        VALUES ('usr-member-john', 'john.k@gmail.com', ?, 'John Kariuki', '254710111222', 'MEMBER', 'mem-001', 1)
    ''', (pw,))

    # 5. Tithe & Offering Envelopes with Verification Codes
    envelopes = [
        {
            "id": "env-001", "rec": "CCK-2026-00001", "mem": "mem-001", "name": "John Kariuki", "phone": "254710111222",
            "method": "MPESA", "p_status": "VERIFIED_PROVIDER", "mpesa": "QA78912345", "date": "2026-10-24 11:30:00", "total": 15000.0,
            "items": [("fund-tithe", 10000.0), ("fund-budget", 3000.0), ("fund-building", 2000.0)]
        },
        {
            "id": "env-002", "rec": "CCK-2026-00002", "mem": "mem-002", "name": "Esther Akinyi", "phone": "254720222333",
            "method": "MPESA", "p_status": "VERIFIED_PROVIDER", "mpesa": "QA89234567", "date": "2026-10-24 11:45:00", "total": 8500.0,
            "items": [("fund-tithe", 5000.0), ("fund-budget", 2000.0), ("fund-welfare", 1500.0)]
        },
        {
            "id": "env-003", "rec": "CCK-2026-00003", "mem": "mem-003", "name": "Peter Kiprono", "phone": "254730333444",
            "method": "CASH", "p_status": "RECORDED", "mpesa": None, "date": "2026-10-31 10:15:00", "total": 25000.0,
            "items": [("fund-tithe", 18000.0), ("fund-budget", 4000.0), ("fund-camp", 3000.0)]
        },
        {
            "id": "env-004", "rec": "CCK-2026-00004", "mem": "mem-004", "name": "Mercy Wambui", "phone": "254740444555",
            "method": "BANK_TRANSFER", "p_status": "RECORDED", "mpesa": "KCB-TX-998811", "date": "2026-10-31 12:00:00", "total": 12000.0,
            "items": [("fund-tithe", 8000.0), ("fund-music", 4000.0)]
        },
        {
            "id": "env-005", "rec": "CCK-2026-00005", "mem": None, "name": "Anonymous Visitor", "phone": "254700000999",
            "method": "CASH", "p_status": "RECORDED", "mpesa": None, "date": "2026-10-31 12:30:00", "total": 3500.0,
            "items": [("fund-budget", 2500.0), ("fund-world", 1000.0)]
        },
    ]

    for env in envelopes:
        v_code = generate_verification_code(env["rec"], env["total"], env["date"])
        cursor.execute('''
            INSERT INTO tithe_offering_envelopes (
                id, receipt_number, verification_code, member_id, donor_name, donor_phone,
                payment_method, payment_status, mpesa_receipt_number, transaction_date, total_amount, status, recorded_by_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'CONFIRMED', 'usr-treasurer')
        ''', (env["id"], env["rec"], v_code, env["mem"], env["name"], env["phone"], env["method"], env["p_status"], env["mpesa"], env["date"], env["total"]))

        for cat_id, amt in env["items"]:
            cursor.execute('''
                INSERT INTO envelope_items (id, envelope_id, fund_category_id, amount)
                VALUES (?, ?, ?, ?)
            ''', (str(uuid.uuid4()), env["id"], cat_id, amt))

    # 6. Configurable Approval Committees & Rules
    cursor.execute('''
        INSERT INTO approval_committees (id, name, description, min_quorum, active)
        VALUES ('com-board', 'Church Board Financial Approval Committee', 'Authorizes major expenditures and capital outlays over KES 10,000', 2, 1)
    ''')

    committee_members = [
        ("usr-pastor", "CHAIR"),
        ("usr-elder", "SECRETARY"),
        ("usr-auditor", "MEMBER"),
    ]
    for uid, r in committee_members:
        cursor.execute('''
            INSERT INTO approval_committee_members (id, committee_id, user_id, role_in_committee)
            VALUES (?, 'com-board', ?, ?)
        ''', (str(uuid.uuid4()), uid, r))

    cursor.execute('''
        INSERT INTO approval_rules (id, name, min_amount, max_amount, committee_id, requires_elder_quorum)
        VALUES ('rule-01', 'Major Church Expenditure (> KES 10,000)', 10000.0, NULL, 'com-board', 1)
    ''')

    # 7. Expenditure Vouchers
    vouchers = [
        {
            "id": "vou-001", "num": "VOU-2026-0001", "title": "Sound System Hire for Youth Rally",
            "desc": "High quality PA microphones and speakers hired for the joint Eastern Youth Rally at Central grounds",
            "dept": "dept-ay", "req_by": "usr-youth-lead", "amt": 25000.0, "payee": "Nairobi Sound & Events Ltd", "payee_phone": "254712000999",
            "status": "PAID", "t_rev": "usr-treasurer", "t_notes": "Budget confirmed within AY allocation.",
            "e_app": "usr-elder", "e_notes": "Approved by Church Board action minute 44/2026.", "method": "MPESA", "ref": "MP-B2C-554433", "paid_at": "2026-10-15 14:00:00"
        },
        {
            "id": "vou-002", "num": "VOU-2026-0002", "title": "Purchase of Adult & Children Bible Lesson Quarterlies",
            "desc": "Quarter 4 Adult Sabbath School and Kindergarten teacher guides from Africa Herald Publishing House",
            "dept": "dept-ss", "req_by": "usr-pastor", "amt": 30000.0, "payee": "Africa Herald Publishing House", "payee_phone": "254722555666",
            "status": "PAID", "t_rev": "usr-treasurer", "t_notes": "Invoice verified against delivery note.",
            "e_app": "usr-pastor", "e_notes": "Crucial spiritual material approved.", "method": "BANK_TRANSFER", "ref": "EFT-883344", "paid_at": "2026-10-18 10:30:00"
        },
        {
            "id": "vou-003", "num": "VOU-2026-0003", "title": "Emergency Medical Benevolent Assistance",
            "desc": "Hospital bill clearance support for senior member admitted at Kenyatta National Hospital",
            "dept": "dept-welfare", "req_by": "usr-pastor", "amt": 20000.0, "payee": "Kenyatta National Hospital", "payee_phone": "254722000000",
            "status": "TREASURER_REVIEWED", "t_rev": "usr-treasurer", "t_notes": "Sufficient welfare reserve available.",
            "e_app": None, "e_notes": None, "method": "MPESA", "ref": None, "paid_at": None
        },
        {
            "id": "vou-004", "num": "VOU-2026-0004", "title": "Youth Mission Evangelism Camp Logistics",
            "desc": "Tents hire, clean drinking water, and outreach Bibles for Machakos rural mission",
            "dept": "dept-ay", "req_by": "usr-youth-lead", "amt": 20000.0, "payee": "Machakos Camp Supplies", "payee_phone": "254733444555",
            "status": "SUBMITTED", "t_rev": None, "t_notes": None,
            "e_app": None, "e_notes": None, "method": "MPESA", "ref": None, "paid_at": None
        },
    ]

    for v in vouchers:
        cursor.execute('''
            INSERT INTO expenditure_vouchers (
                id, voucher_number, title, description, department_id, requested_by_id, amount,
                payee_name, payee_phone, status, treasurer_reviewed_by_id, treasurer_reviewed_at,
                treasurer_notes, elder_approved_by_id, elder_approved_at, elder_notes,
                payment_method, payment_reference, paid_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            v["id"], v["num"], v["title"], v["desc"], v["dept"], v["req_by"], v["amt"],
            v["payee"], v["payee_phone"], v["status"], v["t_rev"],
            "2026-10-14 10:00:00" if v["t_rev"] else None, v["t_notes"],
            v["e_app"], "2026-10-14 16:00:00" if v["e_app"] else None, v["e_notes"],
            v["method"], v["ref"], v["paid_at"]
        ))


    # Committee votes for voucher 001
    cursor.execute('''
        INSERT INTO approval_decisions (id, voucher_id, user_id, decision, notes)
        VALUES (?, 'vou-001', 'usr-elder', 'APPROVE', 'Authorized on behalf of church board.')
    ''', (str(uuid.uuid4()),))
    cursor.execute('''
        INSERT INTO approval_decisions (id, voucher_id, user_id, decision, notes)
        VALUES (?, 'vou-001', 'usr-pastor', 'APPROVE', 'Pastoral consent granted.')
    ''', (str(uuid.uuid4()),))

    # 8. Church Property & Asset Inventory
    assets = [
        {"tag": "AST-2024-001", "name": "Soundcraft 24-Channel Audio Mixer", "cat": "SOUND_EQUIPMENT", "qty": 1, "loc": "PA Booth", "cond": "EXCELLENT", "cust": "usr-youth-lead", "cost": 145000.0},
        {"tag": "AST-2024-002", "name": "Shure Wireless Vocal Microphones (Set of 4)", "cat": "SOUND_EQUIPMENT", "qty": 4, "loc": "PA Booth", "cond": "GOOD", "cust": "usr-youth-lead", "cost": 72000.0},
        {"tag": "AST-2023-010", "name": "Yamaha Clavinova Digital Stage Piano", "cat": "INSTRUMENT", "qty": 1, "loc": "Sanctuary Podium", "cond": "EXCELLENT", "cust": "usr-pastor", "cost": 180000.0},
        {"tag": "AST-2023-015", "name": "Epson 4000 Lumens Full HD Projector", "cat": "SANCTUARY", "qty": 2, "loc": "Main Sanctuary", "cond": "GOOD", "cust": "usr-elder", "cost": 115000.0},
        {"tag": "AST-2022-040", "name": "Hardwood Church Sanctuary Pews", "cat": "FURNITURE", "qty": 65, "loc": "Main Sanctuary", "cond": "GOOD", "cust": "usr-elder", "cost": 650000.0},
    ]

    for a in assets:
        cursor.execute('''
            INSERT INTO church_assets (id, asset_tag, name, category, quantity, location, condition, custodian_id, purchase_cost)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (str(uuid.uuid4()), a["tag"], a["name"], a["cat"], a["qty"], a["loc"], a["cond"], a["cust"], a["cost"]))

    # 9. Elders & Board Meeting Minutes & Resolutions
    meeting_id = 'mtg-2026-q4'
    cursor.execute('''
        INSERT INTO meetings (id, title, meeting_type, date, chairperson_id, secretary_id, minutes_text)
        VALUES (?, 'Q4 Church Board & Finance Council', 'CHURCH_BOARD', '2026-10-10', 'usr-pastor', 'usr-clerk',
        'Meeting opened with prayer by Elder Samuel Omari. Financial report was received from Head Treasurer Grace Wanjiku. Agreed to maintain 100% sacred trust remittance to the Central Kenya Conference and approved youth rally requisitions.')
    ''', (meeting_id,))

    resolutions = [
        {"num": "RES-2026-044", "title": "Youth Rally Sound Logistics Approval", "desc": "Authorize expenditure of up to KES 25,000 from AY department budget for sound hire.", "officer": "usr-youth-lead", "status": "COMPLETED"},
        {"num": "RES-2026-045", "title": "Quarterly Trust Remittance Audit", "desc": "Auditor Silas Mutua to verify Q4 Tithe remittance receipt against Conference bank slip.", "officer": "usr-auditor", "status": "IN_PROGRESS"},
        {"num": "RES-2026-046", "title": "Sanctuary Roof Water Harvesting", "desc": "Deaconry to solicit 3 quotations for gutter repair and water tanks before the November rains.", "officer": "usr-elder", "status": "PENDING"},
    ]

    for r in resolutions:
        cursor.execute('''
            INSERT INTO resolutions (id, meeting_id, resolution_number, title, description, assigned_officer_id, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (str(uuid.uuid4()), meeting_id, r["num"], r["title"], r["desc"], r["officer"], r["status"]))

    # 10. Announcements
    announcements = [
        {"id": "ann-01", "title": "Quarterly Fellowship Sabbath & Communion Ordinance", "content": "All church members, visitors, and families are warmly invited to our Holy Communion service and fellowship lunch this coming Sabbath. Sabbath School begins promptly at 9:00 AM, followed by Divine Service at 10:45 AM.", "category": "SABBATH_SERVICE", "audience": "ALL", "pinned": 1, "author": "usr-pastor"},
        {"id": "ann-02", "title": "Adventist Youth (AY) Camporee Registration Open", "content": "Registration for the Central Kenya Conference Annual Youth Camporee in Narok is now officially open! Cost is KES 2,500 per youth covering transport, lodging, and materials. Contact Kevin Mwangi (AY Leader).", "category": "YOUTH", "audience": "ALL", "pinned": 1, "author": "usr-youth-lead"},
        {"id": "ann-03", "title": "Community Dorcas Welfare Food Drive", "content": "The Women's Ministries and Deaconry departments are collecting dry food items (rice, flour, cooking oil) and warm clothes for needy families in our neighbourhood. Drop donations with the Head Deacon.", "category": "GENERAL", "audience": "ALL", "pinned": 0, "author": "usr-elder"},
        {"id": "ann-04", "title": "Weekly Wednesday Prayer & Bible Study", "content": "Join us every Wednesday from 5:30 PM to 7:00 PM in the church sanctuary and online on Zoom for prayer, intercession, and practical study of the book of Daniel.", "category": "PRAYER_REQUEST", "audience": "ALL", "pinned": 0, "author": "usr-pastor"}
    ]

    for a in announcements:
        cursor.execute('''
            INSERT INTO announcements (id, title, content, category, target_audience, author_id, is_pinned)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (a["id"], a["title"], a["content"], a["category"], a["audience"], a["author"], a["pinned"]))

    # 11. Events
    events = [
        {"id": "evt-01", "title": "Joint Sabbath School & Divine Communion Service", "desc": "Quarterly Holy Communion & Ordinance of Humility. Sabbath School starts at 9:00 AM.", "loc": "Main Sanctuary", "start": "2026-11-07 09:00:00", "end": "2026-11-07 13:00:00"},
        {"id": "evt-02", "title": "Adventist Youth Music & Praise Concert", "desc": "Praise and worship festival featuring local choirs, quartets, and youth bands.", "loc": "Church Amphitheatre", "start": "2026-11-14 14:00:00", "end": "2026-11-14 18:00:00"},
        {"id": "evt-03", "title": "Annual Church Business & Stewardship Meeting", "desc": "Review of financial year 2026 reports, church development plans, and nominating committee updates.", "loc": "Multipurpose Hall", "start": "2026-11-21 15:00:00", "end": "2026-11-21 18:00:00"},
    ]

    for e in events:
        cursor.execute('''
            INSERT INTO events (id, title, description, location, start_date, end_date, is_public, coordinator_id)
            VALUES (?, ?, ?, ?, ?, ?, 1, 'usr-pastor')
        ''', (e["id"], e["title"], e["desc"], e["loc"], e["start"], e["end"]))

    # 12. Attendance
    attendances = [
        {"type": "DIVINE_SERVICE", "date": "2026-10-17", "a": 340, "c": 110, "v": 35, "tot": 485},
        {"type": "DIVINE_SERVICE", "date": "2026-10-24", "a": 355, "c": 125, "v": 42, "tot": 522},
        {"type": "DIVINE_SERVICE", "date": "2026-10-31", "a": 380, "c": 130, "v": 50, "tot": 560},
    ]

    for att in attendances:
        cursor.execute('''
            INSERT INTO attendance (id, service_type, date, adult_count, children_count, visitors_count, total_count, recorded_by_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'usr-clerk')
        ''', (str(uuid.uuid4()), att["type"], att["date"], att["a"], att["c"], att["v"], att["tot"]))

    # 13. Audit Logs
    audit_entries = [
        ("usr-pastor", "LOGIN", "User", "usr-pastor", '{"action": "2FA Authenticated Login"}', "127.0.0.1"),
        ("usr-treasurer", "RECORD_OFFERING", "TitheOfferingEnvelope", "env-003", '{"amount": 25000, "receipt": "CCK-2026-00003"}', "127.0.0.1"),
        ("usr-elder", "COMMITTEE_VOTE", "ExpenditureVoucher", "vou-001", '{"decision": "APPROVE", "role": "CHURCH_BOARD"}', "127.0.0.1"),
        ("usr-treasurer", "DISBURSE_PAYMENT", "ExpenditureVoucher", "vou-001", '{"reference": "MP-B2C-554433"}', "127.0.0.1"),
    ]

    for uid, act, ent, ent_id, det, ip in audit_entries:
        cursor.execute('''
            INSERT INTO audit_logs (id, user_id, action, entity, entity_id, details, ip_address)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (str(uuid.uuid4()), uid, act, ent, ent_id, det, ip))

    conn.commit()
    conn.close()
    print("Database seeding completed successfully! Test users created with password: 'password123'")

if __name__ == '__main__':
    seed_database()
