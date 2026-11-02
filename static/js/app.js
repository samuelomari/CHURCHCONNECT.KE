/**
 * ChurchConnect Kenya - Frontend Application Engine
 * Pure Vanilla JavaScript (Modern ES6+) with Strict Authentication Wall & Role Separation
 */

// App State
const state = {
  token: localStorage.getItem('cc_token') || null,
  currentUser: null,
  activeSection: 'dashboard',
  fundCategories: [],
  members: [],
  departments: [],
  chartInstance: null
};

// Kenyan Shilling Formatter
const formatKES = (val) => {
  const num = Number(val) || 0;
  return 'KES ' + num.toLocaleString('en-KE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

// Toast Notifications
const showToast = (message, type = 'info') => {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerText = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
};

// API Fetch Helper
const api = async (endpoint, options = {}) => {
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {})
  };
  if (state.token) {
    headers['Authorization'] = `Bearer ${state.token}`;
  }

  try {
    const res = await fetch(endpoint, { ...options, headers });
    const data = await res.json();
    if (!res.ok) {
      if (res.status === 401 && !endpoint.includes('/api/auth/login')) {
        handleLogout('Session expired. Please sign in again.');
      }
      throw new Error(data.error || 'Server error occurred');
    }
    return data;
  } catch (err) {
    console.error(`API Error on ${endpoint}:`, err);
    showToast(err.message, 'error');
    throw err;
  }
};

// ==========================================
// 1. AUTHENTICATION & LOGIN WALL
// ==========================================
const showAuthView = () => {
  document.getElementById('auth-view').style.display = 'flex';
  document.getElementById('app-container').style.display = 'none';
};

const showAppView = () => {
  document.getElementById('auth-view').style.display = 'none';
  document.getElementById('app-container').style.display = 'flex';
};

const toggleAuthTab = (tab) => {
  document.querySelectorAll('.auth-tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.auth-form').forEach(f => f.classList.remove('active'));

  if (tab === 'login') {
    document.getElementById('tab-btn-login').classList.add('active');
    document.getElementById('form-login').classList.add('active');
  } else {
    document.getElementById('tab-btn-register').classList.add('active');
    document.getElementById('form-register').classList.add('active');
  }
};

const quickFillLogin = async (email, password) => {
  document.getElementById('login-email').value = email;
  document.getElementById('login-password').value = password;
  toggleAuthTab('login');
  await executeLogin(email, password);
};

const handleLoginSubmit = async (e) => {
  e.preventDefault();
  const email = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value;
  await executeLogin(email, password);
};

const executeLogin = async (email, password) => {
  try {
    const res = await api('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password })
    });

    state.token = res.token;
    state.currentUser = res.user;
    localStorage.setItem('cc_token', res.token);

    showToast(`Welcome back, ${res.user.full_name}!`, 'success');
    setupUserSession(res.user);
  } catch (err) {
    // Error notification handled by api()
  }
};

const handleRegisterSubmit = async (e) => {
  e.preventDefault();
  const email = document.getElementById('reg-email').value.trim().toLowerCase();
  const password = document.getElementById('reg-password').value;
  const name = document.getElementById('reg-name').value.trim();
  const phone = document.getElementById('reg-phone').value.trim();
  const memNum = document.getElementById('reg-mem-num').value.trim();
  const deptId = document.getElementById('reg-dept').value || null;

  // Frontend email format check
  const emailPattern = /^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$/;
  if (!emailPattern.test(email)) {
    showToast('Please provide a valid email address (e.g., name@domain.ke)', 'error');
    return;
  }

  // Password complexity check
  if (password.length < 8) {
    showToast('Password must be at least 8 characters long', 'error');
    return;
  }
  if (!/[A-Z]/.test(password) || !/[a-z]/.test(password) || !/[0-9]/.test(password)) {
    showToast('Password must contain uppercase, lowercase and a digit', 'error');
    return;
  }

  try {
    const res = await api('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({
        email,
        password,
        full_name: name,
        phone,
        member_number: memNum,
        department_id: deptId
      })
    });

    state.token = res.token;
    state.currentUser = res.user;
    localStorage.setItem('cc_token', res.token);

    showToast(res.message || 'Registration successful! Welcome.', 'success');
    setupUserSession(res.user);
  } catch (err) {}
};

const handleLogout = (msg = 'Signed out successfully') => {
  localStorage.removeItem('cc_token');
  state.token = null;
  state.currentUser = null;
  showAuthView();
  showToast(msg, 'info');
};

const setupUserSession = async (user) => {
  document.getElementById('user-display-name').innerText = user.full_name;
  document.getElementById('user-display-role').innerText = user.role.replace('_', ' ');

  // Render Role-Based Navigation
  renderNavigation(user.role);

  showAppView();
  await loadCommonData();

  // Navigate to appropriate default view
  if (user.role === 'MEMBER') {
    navigate('member-dashboard');
  } else {
    navigate('dashboard');
  }
};

// ==========================================
// 2. ROLE-BASED NAVIGATION ENGINE
// ==========================================
const renderNavigation = (role) => {
  const navContainer = document.getElementById('sidebar-nav-container');
  if (!navContainer) return;

  const isOfficer = ['CHURCH_ADMIN', 'PASTOR', 'FIRST_ELDER', 'HEAD_TREASURER', 'ASSISTANT_TREASURER', 'CHURCH_CLERK', 'DEPARTMENT_LEADER', 'AUDITOR'].includes(role);

  if (!isOfficer) {
    // ----------------------------------------
    // REGULAR CHURCH MEMBER MENU
    // ----------------------------------------
    navContainer.innerHTML = `
      <div class="nav-section-title">Member Portal</div>
      <a class="nav-link active" onclick="navigate('member-dashboard')">
        <span class="nav-icon"></span>
        <span>My Home</span>
      </a>
      <a class="nav-link" onclick="navigate('announcements')">
        <span class="nav-icon"></span>
        <span>Announcements</span>
      </a>
      <a class="nav-link" onclick="navigate('events')">
        <span class="nav-icon"></span>
        <span>Church Calendar</span>
      </a>

      <div class="nav-section-title">Stewardship & Giving</div>
      <a class="nav-link" onclick="navigate('my-giving')">
        <span class="nav-icon"></span>
        <span>My Giving Receipts</span>
      </a>
      <a class="nav-link" onclick="navigate('mpesa')">
        <span class="nav-icon"></span>
        <span>Give via M-Pesa</span>
      </a>

      <div class="nav-section-title">Fellowship</div>
      <a class="nav-link" onclick="navigate('departments')">
        <span class="nav-icon"></span>
        <span>Church Ministries</span>
      </a>
      <a class="nav-link" onclick="navigate('members')">
        <span class="nav-icon"></span>
        <span>Member Directory</span>
      </a>
    `;

    // Adjust sub-elements
    const postAnnBtn = document.getElementById('btn-post-announcement');
    if (postAnnBtn) postAnnBtn.style.display = 'none';

    const addMemberBtn = document.getElementById('btn-add-member');
    if (addMemberBtn) addMemberBtn.style.display = 'none';

    const addEvtBtn = document.getElementById('btn-add-event');
    if (addEvtBtn) addEvtBtn.style.display = 'none';

    const recAttBtn = document.getElementById('btn-record-attendance');
    if (recAttBtn) recAttBtn.style.display = 'none';

    const attCard = document.getElementById('card-attendance-wrapper');
    if (attCard) attCard.style.display = 'none';

  } else {
    // ----------------------------------------
    // CHURCH OFFICER & LEADERSHIP MENU
    // ----------------------------------------
    navContainer.innerHTML = `
      <div class="nav-section-title">Core Management</div>
      <a class="nav-link active" onclick="navigate('dashboard')">
        <span class="nav-icon"></span>
        <span>Executive Dashboard</span>
      </a>
      <a class="nav-link" onclick="navigate('treasury')">
        <span class="nav-icon"></span>
        <span>Treasury & Giving</span>
      </a>
      <a class="nav-link" onclick="navigate('vouchers')">
        <span class="nav-icon"></span>
        <span>Vouchers & Requisitions</span>
        <span class="nav-badge" id="badge-pending-vouchers" style="display: none;">0</span>
      </a>
      <a class="nav-link" onclick="navigate('mpesa')">
        <span class="nav-icon"></span>
        <span>M-Pesa Daraja Hub</span>
      </a>

      <div class="nav-section-title">Administration</div>
      <a class="nav-link" onclick="navigate('announcements')">
        <span class="nav-icon"></span>
        <span>Announcements</span>
      </a>
      <a class="nav-link" onclick="navigate('members')">
        <span class="nav-icon"></span>
        <span>Member Directory</span>
      </a>
      <a class="nav-link" onclick="navigate('departments')">
        <span class="nav-icon"></span>
        <span>Departments & Budgets</span>
      </a>
      <a class="nav-link" onclick="navigate('assets')">
        <span class="nav-icon"></span>
        <span>Assets & Inventory</span>
      </a>
      <a class="nav-link" onclick="navigate('meetings')">
        <span class="nav-icon"></span>
        <span>Board Minutes & Resol.</span>
      </a>
      <a class="nav-link" onclick="navigate('events')">
        <span class="nav-icon"></span>
        <span>Events & Attendance</span>
      </a>

      <div class="nav-section-title">Accountability & Governance</div>
      <a class="nav-link" onclick="navigate('accountability')">
        <span class="nav-icon"></span>
        <span>Accountability Centre</span>
      </a>
      <a class="nav-link" onclick="navigate('reports')">
        <span class="nav-icon"></span>
        <span>SDA Monthly Statement</span>
      </a>
      <a class="nav-link" onclick="navigate('audit')">
        <span class="nav-icon"></span>
        <span>Audit Trail</span>
      </a>
      ${['CHURCH_ADMIN', 'PASTOR', 'FIRST_ELDER'].includes(role) ? `
      <a class="nav-link" onclick="downloadDisasterRecoveryBackup()">
        <span class="nav-icon"></span>
        <span>Download DB Backup</span>
      </a>` : ''}
      ${role === 'PASTOR' ? `
      <a class="nav-link" onclick="navigate('roles')">
        <span class="nav-icon"></span>
        <span>Manage Member Roles</span>
      </a>` : ''}
    `;

    // Show officer action buttons
    const postAnnBtn = document.getElementById('btn-post-announcement');
    if (postAnnBtn) postAnnBtn.style.display = 'inline-flex';

    const addMemberBtn = document.getElementById('btn-add-member');
    if (addMemberBtn) addMemberBtn.style.display = ['CHURCH_CLERK', 'PASTOR', 'FIRST_ELDER', 'CHURCH_ADMIN'].includes(role) ? 'inline-flex' : 'none';

    const addEvtBtn = document.getElementById('btn-add-event');
    if (addEvtBtn) addEvtBtn.style.display = 'inline-flex';

    const recAttBtn = document.getElementById('btn-record-attendance');
    if (recAttBtn) recAttBtn.style.display = ['CHURCH_CLERK', 'PASTOR', 'FIRST_ELDER', 'CHURCH_ADMIN'].includes(role) ? 'inline-flex' : 'none';

    const attCard = document.getElementById('card-attendance-wrapper');
    if (attCard) attCard.style.display = 'block';
  }
};

// ==========================================
// 3. SECTION ROUTING
// ==========================================
const navigate = (sectionId) => {
  state.activeSection = sectionId;

  // Update nav links active class
  document.querySelectorAll('.sidebar-nav .nav-link').forEach(link => {
    link.classList.remove('active');
  });
  const activeLink = Array.from(document.querySelectorAll('.sidebar-nav .nav-link')).find(link => 
    link.getAttribute('onclick') && link.getAttribute('onclick').includes(sectionId)
  );
  if (activeLink) activeLink.classList.add('active');

  // Update visible section
  document.querySelectorAll('.app-section').forEach(sec => sec.classList.remove('active'));
  const targetSec = document.getElementById(`section-${sectionId}`);
  if (targetSec) targetSec.classList.add('active');

  // Topbar titles
  const titleMap = {
    'member-dashboard': { title: 'Member Portal', sub: 'Seventh-day Adventist Church community updates & personal stewardship' },
    'dashboard': { title: 'Executive Dashboard', sub: 'Overview of Seventh-day Adventist local church stewardship and operations' },
    'announcements': { title: 'Church Announcements', sub: 'Weekly bulletin, worship programs, and ministry notices' },
    'my-giving': { title: 'My Giving History', sub: 'Your personal tithe & offering receipts and mobile money contributions' },
    'treasury': { title: 'Treasury & Giving', sub: 'Tithe, offerings, and fund category receipts register' },
    'vouchers': { title: 'Vouchers & Requisitions', sub: 'Dual-approval expenditure authorization workflow' },
    'mpesa': { title: 'Safaricom M-Pesa Daraja Hub', sub: 'Mobile money real-time giving and paybill reconciliation' },
    'members': { title: 'Member Directory', sub: 'Church clerk membership registry, baptism, and departmental records' },
    'departments': { title: 'Departments & Ministries', sub: 'Church ministries, leaders, and activity information' },
    'assets': { title: 'Church Assets & Property Inventory', sub: 'Church equipment, custodial accountability, and asset management' },
    'meetings': { title: 'Church Board Meetings & Resolutions', sub: 'Official board minutes, agendas, and adopted action resolutions' },
    'events': { title: 'Events & Attendance', sub: 'Church calendar, programmes, and Sabbath attendance logs' },
    'accountability': { title: 'Church Accountability Centre', sub: 'Financial governance oversight, recording attribution, and threshold alerts' },
    'reports': { title: 'SDA Monthly Financial Statement', sub: 'Conference trust remittance calculation and local church balance sheet' },
    'roles': { title: 'Manage Member Roles', sub: 'Assign church officer roles to registered members' },
    'audit': { title: 'Audit Trail', sub: 'Immutable log of administrative and financial activities' }
  };

  const meta = titleMap[sectionId] || { title: 'ChurchConnect Kenya', sub: '' };
  document.getElementById('topbar-title').innerText = meta.title;
  document.getElementById('topbar-sub').innerText = meta.sub;

  // Load section data
  loadSectionData(sectionId);
};

const loadSectionData = async (sectionId) => {
  if (sectionId === 'member-dashboard') loadMemberDashboard();
  else if (sectionId === 'dashboard') loadDashboard();
  else if (sectionId === 'announcements') loadAnnouncements();
  else if (sectionId === 'my-giving') loadMyGiving();
  else if (sectionId === 'treasury') loadTreasury();
  else if (sectionId === 'vouchers') loadVouchers();
  else if (sectionId === 'members') loadMembers();
  else if (sectionId === 'departments') loadDepartments();
  else if (sectionId === 'assets') loadAssets();
  else if (sectionId === 'meetings') loadMeetings();
  else if (sectionId === 'events') loadEvents();
  else if (sectionId === 'accountability') loadAccountabilityCenter();
  else if (sectionId === 'reports') loadSdaMonthlyReport();
  else if (sectionId === 'roles') loadRoleManagement();
  else if (sectionId === 'audit') loadAuditLogs();
};

// Common Data Loader
const loadCommonData = async () => {
  try {
    const [cats, mems, depts] = await Promise.all([
      api('/api/finance/fund-categories'),
      api('/api/members'),
      api('/api/departments')
    ]);
    state.fundCategories = cats;
    state.members = mems;
    state.departments = depts;

    populateModalDropdowns();
  } catch (err) {
    console.error('Error loading common data:', err);
  }
};

const populateModalDropdowns = () => {
  const vchSelect = document.getElementById('vch-dept');
  if (vchSelect) {
    vchSelect.innerHTML = '<option value="">-- Select Department --</option>' +
      state.departments.map(d => `<option value="${d.id}">${d.name} (${d.code})</option>`).join('');
  }

  const memSelect = document.getElementById('mem-dept');
  if (memSelect) {
    memSelect.innerHTML = '<option value="">-- None / General --</option>' +
      state.departments.map(d => `<option value="${d.id}">${d.name}</option>`).join('');
  }

  const regDeptSelect = document.getElementById('reg-dept');
  if (regDeptSelect) {
    regDeptSelect.innerHTML = '<option value="">-- General Congregation --</option>' +
      state.departments.map(d => `<option value="${d.id}">${d.name}</option>`).join('');
  }

  const envMemSelect = document.getElementById('env-member-id');
  if (envMemSelect) {
    envMemSelect.innerHTML = '<option value="">-- Non-Member / Visitor --</option>' +
      state.members.map(m => `<option value="${m.id}">${m.member_number} - ${m.first_name} ${m.last_name}</option>`).join('');
  }

  const evtDeptSelect = document.getElementById('evt-dept');
  if (evtDeptSelect) {
    evtDeptSelect.innerHTML = '<option value="">-- General Church Programme --</option>' +
      state.departments.map(d => `<option value="${d.id}">${d.name}</option>`).join('');
  }
};

// ==========================================
// 4. MEMBER DASHBOARD (NON-CONFIDENTIAL)
// ==========================================
const loadMemberDashboard = async () => {
  try {
    const data = await api('/api/dashboard/overview');
    const s = data.summary;

    document.getElementById('member-welcome-text').innerText = `Welcome back, ${state.currentUser?.full_name || 'Church Member'}!`;
    document.getElementById('member-kpi-tithe').innerText = formatKES(s.my_total_tithe || 0);
    document.getElementById('member-kpi-total').innerText = formatKES(s.my_total_giving || 0);
    document.getElementById('member-kpi-congregation').innerText = s.total_members;

    // Render announcements preview
    const annContainer = document.getElementById('member-dash-announcements');
    if (data.announcements && data.announcements.length > 0) {
      annContainer.innerHTML = data.announcements.map(a => `
        <div class="announcement-card ${a.is_pinned ? 'pinned' : ''}">
          <div class="announcement-header">
            <span class="announcement-title">${a.title}</span>
            <span class="badge badge-info">${a.category.replace('_', ' ')}</span>
          </div>
          <div class="announcement-meta">Posted by ${a.author_name} | ${a.created_at.split(' ')[0]}</div>
          <p class="announcement-text">${a.content}</p>
        </div>
      `).join('');
    } else {
      annContainer.innerHTML = '<p style="color: var(--text-muted); font-size: 13px;">No announcements posted at this time.</p>';
    }

    // Render events preview
    const evtContainer = document.getElementById('member-dash-events');
    if (data.upcoming_events && data.upcoming_events.length > 0) {
      evtContainer.innerHTML = data.upcoming_events.map(ev => `
        <div style="border-bottom: 1px solid var(--border); padding: 10px 0; font-size: 13px;">
          <div style="font-weight: 600; color: var(--sda-blue-dark);">${ev.title}</div>
          <div style="font-size: 11.5px; color: var(--text-muted); margin-top: 3px;">
             ${ev.location} |  ${ev.start_date.split(' ')[0]}
          </div>
        </div>
      `).join('');
    } else {
      evtContainer.innerHTML = '<p style="color: var(--text-muted); font-size: 13px;">No upcoming events scheduled.</p>';
    }
  } catch (err) {
    console.error('Failed to load member dashboard:', err);
  }
};

// ==========================================
// 5. ANNOUNCEMENTS BOARD
// ==========================================
const loadAnnouncements = async () => {
  try {
    const list = await api('/api/announcements');
    const container = document.getElementById('announcements-container');
    if (!container) return;

    if (list.length === 0) {
      container.innerHTML = '<p style="color: var(--text-muted); padding: 20px; text-align: center;">No announcements available.</p>';
      return;
    }

    container.innerHTML = list.map(a => `
      <div class="announcement-card ${a.is_pinned ? 'pinned' : ''}">
        <div class="announcement-header">
          <span class="announcement-title">
            ${a.is_pinned ? ' ' : ''}${a.title}
          </span>
          <span class="badge ${a.category === 'SABBATH_SERVICE' ? 'badge-success' : 'badge-info'}">
            ${a.category.replace('_', ' ')}
          </span>
        </div>
        <div class="announcement-meta">
          Published by <strong>${a.author_name} (${a.author_role.replace('_', ' ')})</strong> on ${a.created_at}
        </div>
        <p class="announcement-text">${a.content}</p>
      </div>
    `).join('');
  } catch (err) {}
};

const openNewAnnouncementModal = () => openModal('modal-announcement');

const submitAnnouncement = async (e) => {
  e.preventDefault();
  const payload = {
    title: document.getElementById('ann-title').value.trim(),
    category: document.getElementById('ann-category').value,
    target_audience: document.getElementById('ann-audience').value,
    content: document.getElementById('ann-content').value.trim(),
    is_pinned: document.getElementById('ann-pinned').checked
  };

  try {
    await api('/api/announcements', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
    showToast('Announcement published successfully!', 'success');
    closeModal('modal-announcement');
    loadAnnouncements();
  } catch (err) {}
};

// ==========================================
// 6. MY GIVING HISTORY (MEMBER RECEIPTS)
// ==========================================
const loadMyGiving = async () => {
  try {
    const data = await api('/api/finance/my-giving');
    const tbody = document.getElementById('table-my-giving-body');
    if (!tbody) return;

    if (!data.envelopes || data.envelopes.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 24px;">No giving receipts recorded yet for your account.</td></tr>';
      return;
    }

    tbody.innerHTML = data.envelopes.map(e => {
      const breakdown = (e.items || []).map(it => `${it.fund_name}: ${formatKES(it.amount)}`).join('<br>');
      return `
        <tr>
          <td><strong>${e.receipt_number}</strong></td>
          <td>${e.transaction_date.split(' ')[0]}</td>
          <td><span class="badge ${e.payment_method === 'MPESA' ? 'badge-success' : 'badge-secondary'}">${e.payment_method}</span></td>
          <td>${e.mpesa_receipt_number || '-'}</td>
          <td style="font-size: 11.5px; color: var(--text-muted);">${breakdown || '-'}</td>
          <td><strong style="color: var(--sda-blue);">${formatKES(e.total_amount)}</strong></td>
          <td>
            <button class="btn btn-outline btn-sm" onclick="openReceiptModal('${e.receipt_number}')"> View Receipt</button>
          </td>
        </tr>
      `;
    }).join('');
  } catch (err) {}
};

// ==========================================
// 7. OFFICER EXECUTIVE DASHBOARD
// ==========================================
const loadDashboard = async () => {
  try {
    const data = await api('/api/dashboard/overview');
    if (data.is_member_view) {
      navigate('member-dashboard');
      return;
    }
    const s = data.summary;

    document.getElementById('kpi-tithe').innerText = formatKES(s.total_tithe);
    document.getElementById('kpi-local-budget').innerText = formatKES(s.total_local_church);
    document.getElementById('kpi-expenses').innerText = formatKES(s.total_expenditure);
    document.getElementById('kpi-net-reserve').innerText = formatKES(s.net_local_reserve);
    document.getElementById('kpi-members').innerText = s.total_members;
    document.getElementById('kpi-depts').innerText = `Across ${s.total_departments} Departments`;

    const pendingTotal = (s.pending_treasurer || 0) + (s.pending_elder || 0);
    const navBadge = document.getElementById('badge-pending-vouchers');
    if (navBadge) {
      navBadge.style.display = pendingTotal > 0 ? 'inline-block' : 'none';
      navBadge.innerText = pendingTotal;
    }
    const dashPendingBadge = document.getElementById('dash-pending-badge');
    if (dashPendingBadge) {
      dashPendingBadge.innerText = `${pendingTotal} Pending`;
    }

    const pendingContainer = document.getElementById('dash-pending-vouchers-list');
    if (pendingTotal === 0) {
      pendingContainer.innerHTML = '<p style="color: var(--text-muted); font-size: 13px;">No vouchers currently awaiting approval.</p>';
    } else {
      pendingContainer.innerHTML = `
        <div style="display: flex; flex-direction: column; gap: 10px;">
          ${s.pending_treasurer > 0 ? `
            <div style="background-color: #fef3c7; border-left: 4px solid var(--warning); padding: 10px 12px; border-radius: 4px; font-size: 13px;">
              <strong>${s.pending_treasurer} Requisition(s)</strong> waiting for Treasury verification.
              <button class="btn btn-outline btn-sm" style="margin-left: 10px;" onclick="navigate('vouchers')">Review</button>
            </div>
          ` : ''}
          ${s.pending_elder > 0 ? `
            <div style="background-color: #eff6ff; border-left: 4px solid var(--sda-blue); padding: 10px 12px; border-radius: 4px; font-size: 13px;">
              <strong>${s.pending_elder} Requisition(s)</strong> verified by Treasury, awaiting First Elder / Pastor authorization.
              <button class="btn btn-gold btn-sm" style="margin-left: 10px;" onclick="navigate('vouchers')">Authorize</button>
            </div>
          ` : ''}
        </div>
      `;
    }

    const envBody = document.getElementById('dash-recent-envelopes');
    if (data.recent_envelopes && data.recent_envelopes.length > 0) {
      envBody.innerHTML = data.recent_envelopes.map(e => `
        <tr>
          <td><strong>${e.receipt_number}</strong></td>
          <td>${e.donor}</td>
          <td><span class="badge badge-info">${e.payment_method}</span></td>
          <td><strong>${formatKES(e.total_amount)}</strong></td>
        </tr>
      `).join('');
    } else {
      envBody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No recent receipts</td></tr>';
    }

    const evtContainer = document.getElementById('dash-upcoming-events');
    if (data.upcoming_events && data.upcoming_events.length > 0) {
      evtContainer.innerHTML = data.upcoming_events.map(ev => `
        <div style="border-bottom: 1px solid var(--border); padding: 10px 0; font-size: 13px;">
          <div style="font-weight: 600; color: var(--sda-blue-dark);">${ev.title}</div>
          <div style="font-size: 11.5px; color: var(--text-muted);"> ${ev.location} |  ${ev.start_date.split(' ')[0]}</div>
        </div>
      `).join('');
    } else {
      evtContainer.innerHTML = '<p style="color: var(--text-muted); font-size: 13px;">No upcoming events scheduled.</p>';
    }

    renderFundChart(data.fund_distribution);
  } catch (err) {}
};

const renderFundChart = (funds) => {
  const canvas = document.getElementById('chart-fund-distribution');
  if (!canvas || !funds) return;

  if (state.chartInstance) {
    state.chartInstance.destroy();
  }

  const labels = funds.map(f => f.name);
  const amounts = funds.map(f => f.total);
  const colors = ['#cda851', '#1b365d', '#059669', '#0284c7', '#9333ea', '#ea580c', '#e11d48'];

  state.chartInstance = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: amounts,
        backgroundColor: colors.slice(0, labels.length),
        borderWidth: 2,
        borderColor: '#ffffff'
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'right', labels: { font: { family: 'Inter', size: 11 }, boxWidth: 12 } },
        tooltip: {
          callbacks: {
            label: function(context) {
              return ' ' + context.label + ': ' + formatKES(context.raw);
            }
          }
        }
      }
    }
  });
};

// ==========================================
// 8. TREASURY (OFFICER CONFIDENTIAL)
// ==========================================
const loadTreasury = async () => {
  try {
    const envelopes = await api('/api/finance/envelopes');
    const tbody = document.getElementById('table-envelopes-body');
    if (!tbody) return;

    if (envelopes.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 24px;">No giving envelopes recorded yet.</td></tr>';
      return;
    }

    const canReverse = ['HEAD_TREASURER', 'CHURCH_ADMIN', 'PASTOR', 'FIRST_ELDER'].includes(state.currentUser?.role);

    tbody.innerHTML = envelopes.map(e => {
      const donor = e.first_name ? `${e.first_name} ${e.last_name} (${e.member_number})` : (e.donor_name || 'Guest Contributor');
      const breakdown = (e.items || []).map(it => `${it.fund_name}: ${formatKES(it.amount)}`).join('<br>');
      const ref = e.mpesa_receipt_number ? `<br><small style="color: #059669;">M-Pesa: ${e.mpesa_receipt_number}</small>` : '';

      const isReversed = e.status === 'REVERSED';
      const statusBadge = isReversed
        ? '<span class="badge badge-danger">REVERSED</span>'
        : '<span class="badge badge-success">CONFIRMED</span>';

      let actionHtml = `<button class="btn btn-outline btn-sm" onclick="openReceiptModal('${e.receipt_number}')" style="margin-right: 4px;">Receipt</button>`;
      if (canReverse && !isReversed) {
        actionHtml += `<button class="btn btn-danger btn-sm" onclick="openReverseModal('${e.id}', '${e.receipt_number}', ${e.total_amount})">Reverse</button>`;
      }

      return `
        <tr style="${isReversed ? 'opacity: 0.65; background-color: #fff1f2;' : ''}">
          <td><strong>${e.receipt_number}</strong></td>
          <td>${e.transaction_date.split(' ')[0]}</td>
          <td>${donor}</td>
          <td>
            <span class="badge ${e.payment_method === 'MPESA' ? 'badge-success' : 'badge-secondary'}">
              ${e.payment_method}
            </span>
            ${ref}
          </td>
          <td>${statusBadge}</td>
          <td style="font-size: 11.5px; color: var(--text-muted);">${breakdown || '-'}</td>
          <td><strong style="color: ${isReversed ? 'var(--danger)' : 'var(--sda-blue)'};">${isReversed ? '<del>' : ''}${formatKES(e.total_amount)}${isReversed ? '</del>' : ''}</strong></td>
          <td>${actionHtml}</td>
        </tr>
      `;
    }).join('');
  } catch (err) {}
};

const openNewEnvelopeModal = () => {
  const container = document.getElementById('envelope-items-container');
  if (container && state.fundCategories) {
    container.innerHTML = state.fundCategories.map(cat => `
      <div style="display: grid; grid-template-columns: 2fr 1.2fr; gap: 12px; align-items: center;">
        <span style="font-size: 12.5px;">
          ${cat.name} 
          <small style="color: ${cat.fund_type === 'CONFERENCE_TRUST' ? 'var(--sda-gold-hover)' : 'var(--text-muted)'};">
            (${cat.fund_type === 'CONFERENCE_TRUST' ? 'Conference' : 'Local'})
          </small>
        </span>
        <input type="number" class="form-control env-fund-input" data-cat-id="${cat.id}" min="0" step="any" placeholder="0.00" oninput="calculateEnvelopeTotal()">
      </div>
    `).join('');
  }
  calculateEnvelopeTotal();
  openModal('modal-envelope');
};

const calculateEnvelopeTotal = () => {
  let total = 0;
  document.querySelectorAll('.env-fund-input').forEach(inp => {
    total += parseFloat(inp.value) || 0;
  });
  document.getElementById('env-calculated-total').innerText = formatKES(total);
};

const autoFillMemberDetails = () => {
  const memId = document.getElementById('env-member-id').value;
  const member = state.members.find(m => m.id === memId);
  if (member) {
    document.getElementById('env-donor-name').value = `${member.first_name} ${member.last_name}`;
    document.getElementById('env-donor-phone').value = member.phone || '';
  } else {
    document.getElementById('env-donor-name').value = '';
    document.getElementById('env-donor-phone').value = '';
  }
};

const submitEnvelope = async (e) => {
  e.preventDefault();
  const items = [];
  document.querySelectorAll('.env-fund-input').forEach(inp => {
    const amt = parseFloat(inp.value) || 0;
    if (amt > 0) {
      items.push({
        fund_category_id: inp.getAttribute('data-cat-id'),
        amount: amt
      });
    }
  });

  if (items.length === 0) {
    showToast('Please enter an amount in at least one fund category', 'warning');
    return;
  }

  const payload = {
    member_id: document.getElementById('env-member-id').value || null,
    donor_name: document.getElementById('env-donor-name').value || null,
    donor_phone: document.getElementById('env-donor-phone').value || null,
    payment_method: document.getElementById('env-payment-method').value,
    mpesa_receipt_number: document.getElementById('env-ref').value || null,
    items
  };

  try {
    const res = await api('/api/finance/envelopes', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
    showToast(`Envelope recorded! Receipt: ${res.receipt_number}`, 'success');
    closeModal('modal-envelope');
    loadTreasury();
  } catch (err) {}
};

// ==========================================
// 9. VOUCHERS & REQUISITIONS (DUAL APPROVAL)
// ==========================================
const loadVouchers = async () => {
  try {
    const vouchers = await api('/api/finance/vouchers');
    const tbody = document.getElementById('table-vouchers-body');
    if (!tbody) return;

    if (vouchers.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 24px;">No requisitions or vouchers recorded.</td></tr>';
      return;
    }

    const role = state.currentUser ? state.currentUser.role : '';

    tbody.innerHTML = vouchers.map(v => {
      let badgeClass = 'badge-secondary';
      if (v.status === 'PAID') badgeClass = 'badge-success';
      else if (v.status === 'TREASURER_REVIEWED') badgeClass = 'badge-info';
      else if (v.status === 'ELDER_APPROVED') badgeClass = 'badge-warning';
      else if (v.status === 'REJECTED') badgeClass = 'badge-danger';

      let actionBtn = '<span style="color: var(--text-muted); font-size: 12px;">Completed</span>';
      const isRequester = state.currentUser && (v.requested_by_id === state.currentUser.id);
      const isCommitteeMember = ['PASTOR', 'FIRST_ELDER', 'HEAD_TREASURER', 'AUDITOR'].includes(role);

      if (isRequester && ['SUBMITTED', 'TREASURER_REVIEWED', 'IN_COMMITTEE_REVIEW'].includes(v.status)) {
        actionBtn = '<span class="badge badge-warning" title="Separation of Duties: Requester cannot approve their own voucher">Self-Approval Prohibited</span>';
      } else if (v.status === 'SUBMITTED') {
        if (['HEAD_TREASURER', 'ASSISTANT_TREASURER', 'CHURCH_ADMIN'].includes(role)) {
          actionBtn = `<button class="btn btn-primary btn-sm" onclick="openReviewModal('${v.id}', '${v.voucher_number}', '${v.title}', ${v.amount}, '${v.department_name}')">Review</button>`;
        } else {
          actionBtn = '<span style="color: var(--warning); font-size: 11.5px;">Pending Treasury</span>';
        }
      } else if (v.status === 'TREASURER_REVIEWED' || v.status === 'IN_COMMITTEE_REVIEW') {
        let btns = '';
        if (['PASTOR', 'FIRST_ELDER', 'CHURCH_ADMIN'].includes(role)) {
          btns += `<button class="btn btn-gold btn-sm" onclick="openElderModal('${v.id}', '${v.voucher_number}', '${v.title}', ${v.amount}, '${v.department_name}')">Authorize</button> `;
        }
        if (isCommitteeMember && v.amount >= 10000) {
          btns += `<button class="btn btn-primary btn-sm" onclick="openCommitteeVoteModal('${v.id}', '${v.voucher_number}', '${v.title}', ${v.amount})">Vote</button>`;
        }
        actionBtn = btns || '<span style="color: var(--sda-blue); font-size: 11.5px;">Pending Authorization</span>';
      } else if (v.status === 'ELDER_APPROVED') {
        if (['HEAD_TREASURER', 'ASSISTANT_TREASURER', 'CHURCH_ADMIN'].includes(role)) {
          actionBtn = `<button class="btn btn-success btn-sm" onclick="openDisburseModal('${v.id}', '${v.voucher_number}', '${v.title}', ${v.amount}, '${v.payee_name}')">Disburse</button>`;
        } else {
          actionBtn = '<span style="color: #059669; font-size: 11.5px;">Approved - Awaiting Payout</span>';
        }
      } else if (v.status === 'PAID') {
        actionBtn = `<span style="font-size: 11px; color: #059669;">Paid (${v.payment_reference || 'Ref Verified'})</span>`;
      } else if (v.status === 'REJECTED') {
        actionBtn = `<span style="font-size: 11px; color: var(--danger);">${v.rejection_reason || 'Rejected'}</span>`;
      }

      return `
        <tr>
          <td><strong>${v.voucher_number}</strong></td>
          <td>${v.department_name}</td>
          <td>
            <strong>${v.title}</strong>
            <div style="font-size: 11px; color: var(--text-muted);">${v.description}</div>
          </td>
          <td>${v.payee_name}</td>
          <td><strong>${formatKES(v.amount)}</strong></td>
          <td><span class="badge ${badgeClass}">${v.status.replace('_', ' ')}</span></td>
          <td style="font-size: 11.5px;">
            ${v.treasurer_name ? ` Tre: ${v.treasurer_name}<br>` : ''}
            ${v.elder_name ? ` Eld: ${v.elder_name}` : ''}
            ${!v.treasurer_name && !v.elder_name ? 'Initial Submission' : ''}
          </td>
          <td>${actionBtn}</td>
        </tr>
      `;
    }).join('');
  } catch (err) {}
};

const openNewVoucherModal = () => {
  openModal('modal-voucher');
  updateDeptBudgetPreview();
};

const updateDeptBudgetPreview = () => {
  const deptId = document.getElementById('vch-dept').value;
  const dept = state.departments.find(d => d.id === deptId);
  const note = document.getElementById('vch-budget-note');
  if (dept && dept.budget_allocation !== undefined) {
    note.innerText = `Department Budget: ${formatKES(dept.budget_allocation)} | Spent: ${formatKES(dept.budget_spent)} | Remaining: ${formatKES(dept.budget_remaining)}`;
    note.style.color = dept.budget_remaining <= 0 ? 'var(--danger)' : 'var(--text-muted)';
  } else {
    note.innerText = '';
  }
};

const submitVoucher = async (e) => {
  e.preventDefault();
  const payload = {
    department_id: document.getElementById('vch-dept').value,
    title: document.getElementById('vch-title').value,
    description: document.getElementById('vch-desc').value,
    amount: parseFloat(document.getElementById('vch-amount').value),
    payee_name: document.getElementById('vch-payee').value,
    payee_phone: document.getElementById('vch-phone').value || null,
    payment_method: document.getElementById('vch-method').value
  };

  try {
    const res = await api('/api/finance/vouchers', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
    showToast(`Requisition ${res.voucher_number} submitted!`, 'success');
    closeModal('modal-voucher');
    loadVouchers();
    loadDashboard();
  } catch (err) {}
};

const openReviewModal = (id, num, title, amt, dept) => {
  document.getElementById('rev-voucher-id').value = id;
  document.getElementById('rev-voucher-summary').innerHTML = `
    <strong>${num}</strong>: ${title}<br>
    Department: <strong>${dept}</strong> | Amount: <strong style="color: var(--sda-blue);">${formatKES(amt)}</strong>
  `;
  openModal('modal-review-voucher');
};

const executeVoucherReview = async (action) => {
  const id = document.getElementById('rev-voucher-id').value;
  const notes = document.getElementById('rev-notes').value;

  try {
    await api(`/api/finance/vouchers/${id}/treasurer-review`, {
      method: 'POST',
      body: JSON.stringify({ action, notes })
    });
    showToast(`Voucher ${action === 'APPROVE' ? 'verified and sent to Elder' : 'rejected'}`, 'success');
    closeModal('modal-review-voucher');
    loadVouchers();
    loadDashboard();
  } catch (err) {}
};

const openElderModal = (id, num, title, amt, dept) => {
  document.getElementById('eld-voucher-id').value = id;
  document.getElementById('eld-voucher-summary').innerHTML = `
    <strong>${num}</strong>: ${title}<br>
    Department: <strong>${dept}</strong> | Amount: <strong style="color: var(--sda-blue);">${formatKES(amt)}</strong>
  `;
  openModal('modal-elder-voucher');
};

const executeElderApproval = async (action) => {
  const id = document.getElementById('eld-voucher-id').value;
  const notes = document.getElementById('eld-notes').value;

  try {
    await api(`/api/finance/vouchers/${id}/elder-approve`, {
      method: 'POST',
      body: JSON.stringify({ action, notes })
    });
    showToast(`Voucher ${action === 'APPROVE' ? 'authorized by Church Leadership' : 'rejected'}`, 'success');
    closeModal('modal-elder-voucher');
    loadVouchers();
    loadDashboard();
  } catch (err) {}
};

const openDisburseModal = (id, num, title, amt, payee) => {
  document.getElementById('disb-voucher-id').value = id;
  document.getElementById('disb-voucher-summary').innerHTML = `
    <strong>${num}</strong>: ${title}<br>
    Payee: <strong>${payee}</strong> | Payout Amount: <strong style="color: #059669;">${formatKES(amt)}</strong>
  `;
  document.getElementById('disb-ref').value = `MP-B2C-${Math.floor(100000 + Math.random() * 900000)}`;
  openModal('modal-disburse-voucher');
};

const executeDisbursement = async () => {
  const id = document.getElementById('disb-voucher-id').value;
  const method = document.getElementById('disb-method').value;
  const ref = document.getElementById('disb-ref').value;

  try {
    await api(`/api/finance/vouchers/${id}/disburse`, {
      method: 'POST',
      body: JSON.stringify({ payment_method: method, payment_reference: ref })
    });
    showToast('Payment disbursed! Department budget updated.', 'success');
    closeModal('modal-disburse-voucher');
    loadVouchers();
    loadDashboard();
  } catch (err) {}
};

// ==========================================
// 10. SAFARICOM M-PESA DARAJA SIMULATOR
// ==========================================
const handleMpesaSimulation = async (e) => {
  e.preventDefault();
  const phone = document.getElementById('sim-phone').value;
  const amount = parseFloat(document.getElementById('sim-amount').value);
  const accountRef = document.getElementById('sim-ref').value;
  const donorName = document.getElementById('sim-donor').value;
  const fundCode = document.getElementById('sim-fund').value;

  try {
    const res = await api('/api/mpesa/simulate', {
      method: 'POST',
      body: JSON.stringify({
        phone,
        amount,
        account_reference: accountRef,
        donor_name: donorName,
        fund_code: fundCode
      })
    });

    const resultBox = document.getElementById('mpesa-sim-result');
    const resultText = document.getElementById('mpesa-sim-result-text');
    resultBox.style.display = 'block';
    resultText.innerHTML = `
      M-Pesa Receipt: <strong>${res.mpesa_receipt}</strong><br>
      Church Receipt: <strong>${res.church_receipt}</strong><br>
      Amount: <strong>${formatKES(res.amount)}</strong> from <strong>${res.donor}</strong><br>
      Reconciled to Treasury ledger automatically.
    `;

    showToast('M-Pesa payment captured & envelope receipt issued!', 'success');
    if (state.currentUser?.role === 'MEMBER') {
      loadMyGiving();
      loadMemberDashboard();
    } else {
      loadDashboard();
    }
  } catch (err) {}
};

// ==========================================
// 11. MEMBERS DIRECTORY
// ==========================================
const loadMembers = async () => {
  try {
    const members = await api('/api/members');
    state.members = members;
    renderMembersTable(members);
  } catch (err) {
    console.error('Failed to load members:', err);
  }
};

const renderMembersTable = (members) => {
  const tbody = document.getElementById('table-members-body');
  const headerRow = document.getElementById('table-members-header-row');
  if (!tbody || !headerRow) return;

  const isOfficer = ['CHURCH_ADMIN', 'PASTOR', 'FIRST_ELDER', 'CHURCH_CLERK', 'HEAD_TREASURER', 'ASSISTANT_TREASURER'].includes(state.currentUser?.role);

  if (isOfficer) {
    headerRow.innerHTML = `
      <th>Member #</th>
      <th>Full Name</th>
      <th>Phone</th>
      <th>Email</th>
      <th>Gender</th>
      <th>Baptism Details</th>
      <th>Department</th>
      <th>Status</th>
    `;
    tbody.innerHTML = members.map(m => `
      <tr>
        <td><strong>${m.member_number}</strong></td>
        <td>${m.first_name} ${m.last_name}</td>
        <td>${m.phone || '-'}</td>
        <td>${m.email || '-'}</td>
        <td><span class="badge ${m.gender === 'MALE' ? 'badge-info' : 'badge-secondary'}">${m.gender}</span></td>
        <td style="font-size: 11.5px;">
          ${m.baptism_date ? `Baptized: ${m.baptism_date.split(' ')[0]}<br><small style="color: var(--text-muted);">${m.baptism_church || ''}</small>` : '<span style="color: var(--text-muted);">Unbaptized</span>'}
        </td>
        <td>${m.department_name || 'General'}</td>
        <td><span class="badge badge-success">${m.status}</span></td>
      </tr>
    `).join('');
  } else {
    // Non-confidential directory for members
    headerRow.innerHTML = `
      <th>Member #</th>
      <th>Full Name</th>
      <th>Gender</th>
      <th>Department</th>
      <th>Status</th>
    `;
    tbody.innerHTML = members.map(m => `
      <tr>
        <td><strong>${m.member_number}</strong></td>
        <td>${m.first_name} ${m.last_name}</td>
        <td><span class="badge ${m.gender === 'MALE' ? 'badge-info' : 'badge-secondary'}">${m.gender}</span></td>
        <td>${m.department_name || 'General'}</td>
        <td><span class="badge badge-success">${m.status}</span></td>
      </tr>
    `).join('');
  }
};

const filterMembers = () => {
  const q = document.getElementById('member-search-input').value.toLowerCase();
  const filtered = state.members.filter(m => 
    m.first_name.toLowerCase().includes(q) ||
    m.last_name.toLowerCase().includes(q) ||
    m.member_number.toLowerCase().includes(q) ||
    (m.phone && m.phone.includes(q))
  );
  renderMembersTable(filtered);
};

const openNewMemberModal = () => openModal('modal-member');

const submitMember = async (e) => {
  e.preventDefault();
  const payload = {
    member_number: document.getElementById('mem-num').value,
    first_name: document.getElementById('mem-fn').value,
    last_name: document.getElementById('mem-ln').value,
    phone: document.getElementById('mem-phone').value || null,
    email: document.getElementById('mem-email').value || null,
    gender: document.getElementById('mem-gender').value,
    baptism_date: document.getElementById('mem-bap-date').value || null,
    baptism_church: document.getElementById('mem-bap-church').value || null,
    department_id: document.getElementById('mem-dept').value || null,
    residence: document.getElementById('mem-residence').value || null
  };

  try {
    await api('/api/members', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
    showToast('Member successfully registered in church roll!', 'success');
    closeModal('modal-member');
    loadMembers();
    loadDashboard();
  } catch (err) {}
};

// ==========================================
// 12. DEPARTMENTS & MINISTRIES
// ==========================================
const loadDepartments = async () => {
  try {
    const depts = await api('/api/departments');
    state.departments = depts;
    const grid = document.getElementById('departments-grid');
    if (!grid) return;

    const isOfficer = ['CHURCH_ADMIN', 'PASTOR', 'FIRST_ELDER', 'HEAD_TREASURER', 'ASSISTANT_TREASURER', 'DEPARTMENT_LEADER', 'AUDITOR'].includes(state.currentUser?.role);

    grid.innerHTML = depts.map(d => {
      let budgetHtml = '';
      if (isOfficer && d.budget_allocation !== undefined) {
        const pct = d.budget_allocation > 0 ? Math.min(100, (d.budget_spent / d.budget_allocation) * 100) : 0;
        let barClass = '';
        if (pct > 85) barClass = 'danger';
        else if (pct > 65) barClass = 'warning';

        budgetHtml = `
          <div class="progress-bar-container">
            <div class="progress-bar ${barClass}" style="width: ${pct}%;"></div>
          </div>
          <div style="display: flex; justify-content: space-between; font-size: 11.5px; margin-top: 4px;">
            <span>Spent: <strong>${formatKES(d.budget_spent)}</strong></span>
            <span>Alloc: <strong>${formatKES(d.budget_allocation)}</strong></span>
          </div>
          <div style="font-size: 11px; color: var(--text-muted); margin-top: 8px;">
            Remaining: <strong style="color: ${d.budget_remaining <= 0 ? 'var(--danger)' : '#059669'};">${formatKES(d.budget_remaining)}</strong>
          </div>
        `;
      }

      return `
        <div class="stat-card">
          <div class="stat-card-title">
            <span>${d.name} (${d.code})</span>
            <span></span>
          </div>
          <div style="font-size: 11.5px; color: var(--text-muted); margin-bottom: 8px;">
            Leader: <strong>${d.leader_name || 'Unassigned'}</strong>
          </div>
          <p style="font-size: 12.5px; color: #475569; margin-bottom: 10px;">${d.description || 'Active ministry in the local church.'}</p>
          ${budgetHtml}
          <div style="margin-top: 10px; font-size: 11.5px; color: var(--text-muted);">
            Members: <strong>${d.member_count}</strong> ${isOfficer ? `| Vouchers: <strong>${d.voucher_count}</strong>` : ''}
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {}
};

// ==========================================
// 13. EVENTS & ATTENDANCE
// ==========================================
const loadEvents = async () => {
  try {
    const isOfficer = ['CHURCH_ADMIN', 'PASTOR', 'FIRST_ELDER', 'CHURCH_CLERK', 'HEAD_TREASURER', 'ASSISTANT_TREASURER', 'DEPARTMENT_LEADER', 'AUDITOR'].includes(state.currentUser?.role);

    const [events, attendance] = await Promise.all([
      api('/api/events'),
      isOfficer ? api('/api/attendance') : Promise.resolve([])
    ]);

    const evtBody = document.getElementById('table-events-body');
    if (evtBody) {
      evtBody.innerHTML = events.map(ev => `
        <tr>
          <td>
            <strong>${ev.title}</strong>
            <div style="font-size: 11px; color: var(--text-muted);">${ev.description || ''}</div>
          </td>
          <td>${ev.location}</td>
          <td>${ev.start_date}</td>
          <td>${ev.coordinator_name || 'Church Board'}</td>
        </tr>
      `).join('');
    }

    const attBody = document.getElementById('table-attendance-body');
    if (attBody && isOfficer) {
      attBody.innerHTML = attendance.map(a => `
        <tr>
          <td><strong>${a.date}</strong></td>
          <td><span class="badge badge-info">${a.service_type.replace('_', ' ')}</span></td>
          <td>${a.adult_count}</td>
          <td>${a.children_count}</td>
          <td>${a.visitors_count}</td>
          <td><strong style="color: var(--sda-blue);">${a.total_count}</strong></td>
        </tr>
      `).join('');
    }
  } catch (err) {}
};

const openNewEventModal = () => openModal('modal-event');
const submitEvent = async (e) => {
  e.preventDefault();
  const payload = {
    title: document.getElementById('evt-title').value,
    location: document.getElementById('evt-loc').value,
    start_date: document.getElementById('evt-start').value.replace('T', ' ') + ':00',
    end_date: document.getElementById('evt-end').value.replace('T', ' ') + ':00',
    department_id: document.getElementById('evt-dept').value || null
  };
  try {
    await api('/api/events', { method: 'POST', body: JSON.stringify(payload) });
    showToast('Event successfully added to church calendar', 'success');
    closeModal('modal-event');
    loadEvents();
  } catch (err) {}
};

const openAttendanceModal = () => {
  document.getElementById('att-date').value = new Date().toISOString().split('T')[0];
  openModal('modal-attendance');
};

const calculateAttTotal = () => {
  const a = parseInt(document.getElementById('att-adults').value) || 0;
  const c = parseInt(document.getElementById('att-children').value) || 0;
  const v = parseInt(document.getElementById('att-visitors').value) || 0;
  document.getElementById('att-total-display').innerText = a + c + v;
};

const submitAttendance = async (e) => {
  e.preventDefault();
  const a = parseInt(document.getElementById('att-adults').value) || 0;
  const c = parseInt(document.getElementById('att-children').value) || 0;
  const v = parseInt(document.getElementById('att-visitors').value) || 0;

  const payload = {
    service_type: document.getElementById('att-service').value,
    date: document.getElementById('att-date').value,
    adult_count: a,
    children_count: c,
    visitors_count: v
  };

  try {
    await api('/api/attendance', { method: 'POST', body: JSON.stringify(payload) });
    showToast('Attendance recorded!', 'success');
    closeModal('modal-attendance');
    loadEvents();
  } catch (err) {}
};

// ==========================================
// 14. SDA MONTHLY FINANCIAL STATEMENT (OFFICERS)
// ==========================================
const loadSdaMonthlyReport = async () => {
  try {
    const report = await api('/api/finance/reports/sda-monthly');
    const container = document.getElementById('statement-content');
    if (!container) return;

    const conf = report.conference_trust;
    const local = report.local_church;

    container.innerHTML = `
      <div style="border: 2px solid var(--sda-blue); padding: 20px; border-radius: 8px; background-color: #fff;">
        <div style="text-align: center; margin-bottom: 20px;">
          <h2 style="color: var(--sda-blue-dark); font-size: 18px;">SEVENTH-DAY ADVENTIST CHURCH (KENYA)</h2>
          <h3 style="font-size: 15px; color: var(--sda-gold-hover);">LOCAL CHURCH FINANCIAL ACCOUNTABILITY STATEMENT</h3>
          <p style="font-size: 12px; color: var(--text-muted);">East Kenya Union Conference / Central Kenya Conference Field</p>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 20px;">
          <div style="border: 1px solid var(--border); border-radius: 6px; padding: 14px;">
            <h4 style="color: var(--sda-gold-hover); font-size: 13.5px; border-bottom: 1px solid var(--border); padding-bottom: 6px; margin-bottom: 10px;">
              PART A: CONFERENCE TRUST FUNDS (100% Remittance Obligation)
            </h4>
            <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
              <span>Total Holy Tithe Collected:</span>
              <strong>${formatKES(conf.total_tithe)}</strong>
            </div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
              <span>Total Conference Offerings (Camp Meeting, World):</span>
              <strong>${formatKES(conf.total_trust_funds - conf.total_tithe)}</strong>
            </div>
            <hr style="margin: 8px 0; border: none; border-top: 1px dashed var(--border);">
            <div style="display: flex; justify-content: space-between; font-size: 14px; color: var(--sda-blue-dark);">
              <strong>Net Payable to Conference:</strong>
              <strong style="color: #92400e;">${formatKES(conf.remittance_due_to_conference)}</strong>
            </div>
            <div style="margin-top: 6px; font-size: 11px; color: var(--text-muted);">
              Status: <span class="badge badge-warning">Held in Trust for Conference Remittance</span>
            </div>
          </div>

          <div style="border: 1px solid var(--border); border-radius: 6px; padding: 14px;">
            <h4 style="color: var(--sda-blue); font-size: 13.5px; border-bottom: 1px solid var(--border); padding-bottom: 6px; margin-bottom: 10px;">
              PART B: LOCAL CHURCH FUNDS & EXPENDITURES
            </h4>
            <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
              <span>Total Local Offerings Received:</span>
              <strong>${formatKES(local.total_local_funds_collected)}</strong>
            </div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
              <span>Authorized Vouchers Disbursed:</span>
              <strong style="color: var(--danger);">- ${formatKES(local.total_expenditure_paid)}</strong>
            </div>
            <hr style="margin: 8px 0; border: none; border-top: 1px dashed var(--border);">
            <div style="display: flex; justify-content: space-between; font-size: 14px;">
              <strong>Net Local Operating Balance:</strong>
              <strong style="color: ${local.net_operating_surplus >= 0 ? '#059669' : 'var(--danger)'};">
                ${formatKES(local.net_operating_surplus)}
              </strong>
            </div>
            <div style="margin-top: 6px; font-size: 11px; color: var(--text-muted);">
              Reserve Health: <span class="badge ${local.net_operating_surplus >= 0 ? 'badge-success' : 'badge-danger'}">
                ${local.net_operating_surplus >= 0 ? 'Surplus Reserve' : 'Deficit'}
              </span>
            </div>
          </div>
        </div>

        <h4 style="font-size: 13px; margin-bottom: 8px;">Breakdown by Fund Category</h4>
        <table class="data-table" style="margin-bottom: 20px;">
          <thead>
            <tr>
              <th>Fund Category</th>
              <th>Classification</th>
              <th>Remittance Policy</th>
              <th>Amount Collected</th>
            </tr>
          </thead>
          <tbody>
            ${report.breakdown.map(b => `
              <tr>
                <td><strong>${b.name}</strong></td>
                <td><span class="badge ${b.type === 'CONFERENCE_TRUST' ? 'badge-warning' : 'badge-info'}">${b.type.replace('_', ' ')}</span></td>
                <td>${b.remitted ? '100% to Conference' : 'Retained by Local Church'}</td>
                <td><strong>${formatKES(b.total)}</strong></td>
              </tr>
            `).join('')}
          </tbody>
        </table>

        <div style="display: flex; justify-content: space-between; padding-top: 20px; border-top: 1px solid var(--border); font-size: 12px; color: var(--text-muted);">
          <div>Prepared By: <strong>Grace Wanjiku (Head Treasurer)</strong></div>
          <div>Reviewed By: <strong>Silas Mutua (Auditor)</strong></div>
          <div>Approved By: <strong>Elder Samuel Omari (First Elder)</strong></div>
        </div>
      </div>
    `;
  } catch (err) {}
};

// ==========================================
// 15. AUDIT TRAIL
// ==========================================
const loadAuditLogs = async () => {
  try {
    const logs = await api('/api/audit-logs');
    const tbody = document.getElementById('table-audit-body');
    if (!tbody) return;

    tbody.innerHTML = logs.map(l => `
      <tr>
        <td style="font-size: 11.5px;">${l.created_at}</td>
        <td><strong>${l.user_name || 'System / M-Pesa'}</strong></td>
        <td><span class="badge badge-secondary">${l.user_role ? l.user_role.replace('_', ' ') : 'EXTERNAL'}</span></td>
        <td><strong style="color: var(--sda-blue);">${l.action}</strong></td>
        <td>${l.entity}</td>
        <td style="font-size: 11.5px; color: var(--text-muted); max-width: 250px; word-break: break-all;">${l.details || '-'}</td>
      </tr>
    `).join('');
  } catch (err) {}
};

// ==========================================
// ROLE MANAGEMENT (PASTOR ONLY)
// ==========================================
const loadRoleManagement = async () => {
  try {
    const users = await api('/api/users');
    const tbody = document.getElementById('table-roles-body');
    if (!tbody) return;

    if (users.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--text-muted);padding:24px;">No registered users found.</td></tr>';
      return;
    }

    tbody.innerHTML = users.map(u => `
      <tr>
        <td><strong>${u.full_name}</strong></td>
        <td>${u.email}</td>
        <td><span class="badge badge-info">${u.role.replace(/_/g, ' ')}</span></td>
        <td>
          <button class="btn btn-outline btn-sm" onclick="openAssignRoleModal('${u.id}', '${u.full_name}', '${u.role}')">
            Change Role
          </button>
        </td>
      </tr>
    `).join('');
  } catch (err) {}
};

const openAssignRoleModal = (userId, name, currentRole) => {
  document.getElementById('role-user-id').value = userId;
  document.getElementById('role-user-summary').innerHTML = `Assigning role for: <strong>${name}</strong><br>Current role: <span class="badge badge-info">${currentRole.replace(/_/g, ' ')}</span>`;
  document.getElementById('role-select').value = currentRole;
  openModal('modal-assign-role');
};

const executeRoleAssignment = async () => {
  const userId = document.getElementById('role-user-id').value;
  const role = document.getElementById('role-select').value;
  try {
    const res = await api(`/api/users/${userId}/role`, {
      method: 'PATCH',
      body: JSON.stringify({ role })
    });
    showToast(res.message, 'success');
    closeModal('modal-assign-role');
    loadRoleManagement();
  } catch (err) {}
};

// ==========================================
// 16. MODAL UTILITIES
// ==========================================
const openModal = (id) => {
  const m = document.getElementById(id);
  if (m) m.classList.add('active');
};

const closeModal = (id) => {
  const m = document.getElementById(id);
  if (m) m.classList.remove('active');
};

// ==========================================
// 17. INITIALIZATION (MANDATORY LOGIN WALL)
// ==========================================
const initApp = async () => {
  const token = localStorage.getItem('cc_token');
  if (!token) {
    showAuthView();
    return;
  }

  state.token = token;
  try {
    const user = await api('/api/auth/me');
    state.currentUser = user;
    setupUserSession(user);
  } catch (err) {
    // If token is invalid or expired
    handleLogout();
  }
};

document.addEventListener('DOMContentLoaded', initApp);
