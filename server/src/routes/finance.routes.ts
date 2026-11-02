import { Router, Response } from 'express';
import { z } from 'zod';
import { prisma } from '../prisma/client';
import { authenticate, authorize, AuthRequest, createAuditLog } from '../middleware/auth';

const router = Router();

// ==========================================
// 1. FUND CATEGORIES
// ==========================================

router.get('/fund-categories', authenticate, async (_req, res, next) => {
  try {
    const categories = await prisma.fundCategory.findMany({
      where: { active: true },
      orderBy: [{ fundType: 'asc' }, { name: 'asc' }],
    });
    res.json(categories);
  } catch (err) {
    next(err);
  }
});

const createCategorySchema = z.object({
  name: z.string().min(2),
  code: z.string().min(2).max(10),
  fundType: z.enum(['CONFERENCE_TRUST', 'LOCAL_CHURCH']),
  isRemittedToConference: z.boolean().default(false),
  description: z.string().optional(),
});

router.post('/fund-categories', authenticate, authorize(['CHURCH_ADMIN', 'HEAD_TREASURER', 'PASTOR']), async (req: AuthRequest, res: Response, next) => {
  try {
    const data = createCategorySchema.parse(req.body);
    const category = await prisma.fundCategory.create({
      data: {
        ...data,
        code: data.code.toUpperCase(),
      },
    });

    await createAuditLog(req.user!.id, 'CREATE_FUND_CATEGORY', 'FundCategory', category.id, { name: category.name }, req.ip);

    res.status(201).json(category);
  } catch (err) {
    next(err);
  }
});

// ==========================================
// 2. TITHE & OFFERING ENVELOPES / RECEIPTS
// ==========================================

const createEnvelopeSchema = z.object({
  memberId: z.string().optional().nullable(),
  donorName: z.string().optional().nullable(),
  donorPhone: z.string().optional().nullable(),
  paymentMethod: z.enum(['CASH', 'MPESA', 'BANK_TRANSFER', 'CHEQUE']).default('CASH'),
  mpesaReceiptNumber: z.string().optional().nullable(),
  transactionDate: z.string().optional(),
  notes: z.string().optional().nullable(),
  items: z.array(
    z.object({
      fundCategoryId: z.string(),
      amount: z.number().positive('Amount must be greater than zero'),
    })
  ).min(1, 'At least one fund item is required'),
});

router.get('/envelopes', authenticate, async (req: AuthRequest, res: Response, next) => {
  try {
    const { startDate, endDate, paymentMethod, status } = req.query;

    const where: any = {};
    if (paymentMethod && typeof paymentMethod === 'string') {
      where.paymentMethod = paymentMethod;
    }
    if (status && typeof status === 'string') {
      where.status = status;
    }
    if (startDate || endDate) {
      where.transactionDate = {};
      if (startDate) where.transactionDate.gte = new Date(startDate as string);
      if (endDate) where.transactionDate.lte = new Date(endDate as string);
    }

    const envelopes = await prisma.TitheOfferingEnvelope.findMany({
      where,
      include: {
        member: { select: { id: true, memberNumber: true, firstName: true, lastName: true, phone: true } },
        recordedBy: { select: { id: true, fullName: true } },
        items: {
          include: { fundCategory: true },
        },
      },
      orderBy: { transactionDate: 'desc' },
      take: 100,
    });

    res.json(envelopes);
  } catch (err) {
    next(err);
  }
});

router.post('/envelopes', authenticate, authorize(['CHURCH_ADMIN', 'HEAD_TREASURER', 'ASSISTANT_TREASURER', 'PASTOR']), async (req: AuthRequest, res: Response, next) => {
  try {
    const data = createEnvelopeSchema.parse(req.body);

    const totalAmount = data.items.reduce((sum, item) => sum + item.amount, 0);

    const currentYear = new Date().getFullYear();
    const count = await prisma.TitheOfferingEnvelope.count();
    const receiptNumber = `REC-${currentYear}-${String(count + 1).padStart(5, '0')}`;

    const envelope = await prisma.TitheOfferingEnvelope.create({
      data: {
        receiptNumber,
        memberId: data.memberId || null,
        donorName: data.donorName || null,
        donorPhone: data.donorPhone || null,
        paymentMethod: data.paymentMethod,
        mpesaReceiptNumber: data.mpesaReceiptNumber || null,
        transactionDate: data.transactionDate ? new Date(data.transactionDate) : new Date(),
        totalAmount,
        notes: data.notes || null,
        recordedById: req.user!.id,
        items: {
          create: data.items.map((item) => ({
            fundCategoryId: item.fundCategoryId,
            amount: item.amount,
          })),
        },
      },
      include: {
        items: { include: { fundCategory: true } },
        member: true,
      },
    });

    await createAuditLog(
      req.user!.id,
      'CREATE_OFFERING_RECEIPT',
      'TitheOfferingEnvelope',
      envelope.id,
      { receiptNumber, totalAmount, paymentMethod: data.paymentMethod },
      req.ip
    );

    res.status(201).json(envelope);
  } catch (err) {
    next(err);
  }
});

// ==========================================
// 3. EXPENDITURE REQUISITIONS & VOUCHERS
// ==========================================

const createVoucherSchema = z.object({
  title: z.string().min(3),
  description: z.string().min(5),
  departmentId: z.string(),
  amount: z.number().positive(),
  payeeName: z.string().min(2),
  payeePhone: z.string().optional().nullable(),
  paymentMethod: z.enum(['MPESA', 'CHEQUE', 'CASH', 'BANK_TRANSFER']).default('MPESA'),
});

router.get('/vouchers', authenticate, async (req: AuthRequest, res: Response, next) => {
  try {
    const { status, departmentId } = req.query;

    const where: any = {};
    if (status && typeof status === 'string') {
      where.status = status;
    }
    if (departmentId && typeof departmentId === 'string') {
      where.departmentId = departmentId;
    }

    // If user is a Department Leader, filter by their department unless privileged
    if (
      req.user?.role === 'DEPARTMENT_LEADER' &&
      req.user?.departmentId &&
      !['CHURCH_ADMIN', 'PASTOR', 'HEAD_TREASURER', 'FIRST_ELDER', 'AUDITOR'].includes(req.user.role)
    ) {
      where.departmentId = req.user.departmentId;
    }

    const vouchers = await prisma.expenditureVoucher.findMany({
      where,
      include: {
        department: { select: { id: true, name: true, code: true, budgetAllocation: true, budgetSpent: true } },
        requestedBy: { select: { id: true, fullName: true, role: true } },
        treasurerReviewedBy: { select: { id: true, fullName: true } },
        elderApprovedBy: { select: { id: true, fullName: true } },
      },
      orderBy: { createdAt: 'desc' },
    });

    res.json(vouchers);
  } catch (err) {
    next(err);
  }
});

router.post('/vouchers', authenticate, async (req: AuthRequest, res: Response, next) => {
  try {
    const data = createVoucherSchema.parse(req.body);

    const dept = await prisma.department.findUnique({
      where: { id: data.departmentId },
    });

    if (!dept) {
      res.status(404).json({ error: 'Department not found' });
      return;
    }

    // Check if remaining budget can accommodate this requisition
    const budgetRemaining = dept.budgetAllocation - dept.budgetSpent;
    if (data.amount > budgetRemaining) {
      res.status(400).json({
        error: `Insufficient department budget. Requested: KES ${data.amount.toLocaleString()}, Remaining: KES ${Math.max(0, budgetRemaining).toLocaleString()}`,
      });
      return;
    }

    const currentYear = new Date().getFullYear();
    const count = await prisma.expenditureVoucher.count();
    const voucherNumber = `VOU-${currentYear}-${String(count + 1).padStart(4, '0')}`;

    const voucher = await prisma.expenditureVoucher.create({
      data: {
        voucherNumber,
        title: data.title,
        description: data.description,
        departmentId: data.departmentId,
        requestedById: req.user!.id,
        amount: data.amount,
        payeeName: data.payeeName,
        payeePhone: data.payeePhone || null,
        paymentMethod: data.paymentMethod,
        status: 'SUBMITTED',
      },
      include: {
        department: true,
        requestedBy: true,
      },
    });

    await createAuditLog(
      req.user!.id,
      'CREATE_EXPENDITURE_REQUISITION',
      'ExpenditureVoucher',
      voucher.id,
      { voucherNumber, amount: data.amount, department: dept.name },
      req.ip
    );

    res.status(201).json(voucher);
  } catch (err) {
    next(err);
  }
});

// Step 1 of approval: Treasurer Review
router.post('/vouchers/:id/treasurer-review', authenticate, authorize(['CHURCH_ADMIN', 'HEAD_TREASURER', 'ASSISTANT_TREASURER']), async (req: AuthRequest, res: Response, next) => {
  try {
    const { action, notes } = req.body; // action: 'APPROVE' or 'REJECT'
    const voucher = await prisma.expenditureVoucher.findUnique({ where: { id: req.params.id } });

    if (!voucher) {
      res.status(404).json({ error: 'Voucher not found' });
      return;
    }

    if (voucher.status !== 'SUBMITTED') {
      res.status(400).json({ error: `Cannot review voucher with status '${voucher.status}'` });
      return;
    }

    if (action === 'REJECT') {
      const updated = await prisma.expenditureVoucher.update({
        where: { id: voucher.id },
        data: {
          status: 'REJECTED',
          rejectionReason: notes || 'Rejected during treasury review',
          treasurerReviewedById: req.user!.id,
          treasurerReviewedAt: new Date(),
        },
      });
      await createAuditLog(req.user!.id, 'REJECT_VOUCHER_TREASURY', 'ExpenditureVoucher', voucher.id, { notes }, req.ip);
      res.json(updated);
      return;
    }

    const updated = await prisma.expenditureVoucher.update({
      where: { id: voucher.id },
      data: {
        status: 'TREASURER_REVIEWED',
        treasurerNotes: notes || null,
        treasurerReviewedById: req.user!.id,
        treasurerReviewedAt: new Date(),
      },
    });

    await createAuditLog(req.user!.id, 'TREASURER_REVIEW_VOUCHER', 'ExpenditureVoucher', voucher.id, { notes }, req.ip);
    res.json(updated);
  } catch (err) {
    next(err);
  }
});

// Step 2 of approval: Elder / Pastor Final Authorization
router.post('/vouchers/:id/elder-approve', authenticate, authorize(['CHURCH_ADMIN', 'PASTOR', 'FIRST_ELDER']), async (req: AuthRequest, res: Response, next) => {
  try {
    const { action, notes } = req.body; // action: 'APPROVE' or 'REJECT'
    const voucher = await prisma.expenditureVoucher.findUnique({ where: { id: req.params.id } });

    if (!voucher) {
      res.status(404).json({ error: 'Voucher not found' });
      return;
    }

    if (voucher.status !== 'TREASURER_REVIEWED') {
      res.status(400).json({ error: 'Voucher must be reviewed by treasurer first' });
      return;
    }

    if (action === 'REJECT') {
      const updated = await prisma.expenditureVoucher.update({
        where: { id: voucher.id },
        data: {
          status: 'REJECTED',
          rejectionReason: notes || 'Rejected by Pastor/Elder',
          elderApprovedById: req.user!.id,
          elderApprovedAt: new Date(),
        },
      });
      await createAuditLog(req.user!.id, 'REJECT_VOUCHER_ELDER', 'ExpenditureVoucher', voucher.id, { notes }, req.ip);
      res.json(updated);
      return;
    }

    const updated = await prisma.expenditureVoucher.update({
      where: { id: voucher.id },
      data: {
        status: 'ELDER_APPROVED',
        elderNotes: notes || null,
        elderApprovedById: req.user!.id,
        elderApprovedAt: new Date(),
      },
    });

    await createAuditLog(req.user!.id, 'ELDER_APPROVE_VOUCHER', 'ExpenditureVoucher', voucher.id, { notes }, req.ip);
    res.json(updated);
  } catch (err) {
    next(err);
  }
});

// Step 3: Disbursement & Payout Execution
router.post('/vouchers/:id/disburse', authenticate, authorize(['CHURCH_ADMIN', 'HEAD_TREASURER', 'ASSISTANT_TREASURER']), async (req: AuthRequest, res: Response, next) => {
  try {
    const { paymentReference, paymentMethod } = req.body;
    const voucher = await prisma.expenditureVoucher.findUnique({
      where: { id: req.params.id },
      include: { department: true },
    });

    if (!voucher) {
      res.status(404).json({ error: 'Voucher not found' });
      return;
    }

    if (voucher.status !== 'ELDER_APPROVED') {
      res.status(400).json({ error: 'Voucher requires Elder/Pastor authorization before disbursement' });
      return;
    }

    // Update voucher to PAID
    const updatedVoucher = await prisma.expenditureVoucher.update({
      where: { id: voucher.id },
      data: {
        status: 'PAID',
        paymentReference: paymentReference || `DISB-${Date.now()}`,
        paymentMethod: paymentMethod || voucher.paymentMethod,
        paidAt: new Date(),
      },
    });

    // Increment Department budgetSpent
    await prisma.department.update({
      where: { id: voucher.departmentId },
      data: {
        budgetSpent: { increment: voucher.amount },
      },
    });

    await createAuditLog(
      req.user!.id,
      'DISBURSE_VOUCHER',
      'ExpenditureVoucher',
      voucher.id,
      { amount: voucher.amount, paymentReference, payee: voucher.payeeName },
      req.ip
    );

    res.json(updatedVoucher);
  } catch (err) {
    next(err);
  }
});

// ==========================================
// 4. FINANCIAL STATEMENTS & REPORTS
// ==========================================

router.get('/reports/sda-monthly', authenticate, authorize(['CHURCH_ADMIN', 'PASTOR', 'FIRST_ELDER', 'HEAD_TREASURER', 'AUDITOR']), async (req: AuthRequest, res: Response, next) => {
  try {
    const { month, year } = req.query;
    const targetYear = year ? parseInt(year as string, 10) : new Date().getFullYear();
    const targetMonth = month ? parseInt(month as string, 10) : new Date().getMonth() + 1;

    const startDate = new Date(targetYear, targetMonth - 1, 1);
    const endDate = new Date(targetYear, targetMonth, 0, 23, 59, 59);

    const envelopeItems = await prisma.envelopeItem.findMany({
      where: {
        envelope: {
          transactionDate: { gte: startDate, lte: endDate },
          status: 'CONFIRMED',
        },
      },
      include: { fundCategory: true },
    });

    let totalTithe = 0;
    let totalTrustFunds = 0;
    let totalLocalChurchFunds = 0;
    const categoryBreakdown: Record<string, { name: string; amount: number; type: string; isRemitted: boolean }> = {};

    for (const item of envelopeItems) {
      const cat = item.fundCategory;
      if (!categoryBreakdown[cat.code]) {
        categoryBreakdown[cat.code] = {
          name: cat.name,
          amount: 0,
          type: cat.fundType,
          isRemitted: cat.isRemittedToConference,
        };
      }
      categoryBreakdown[cat.code].amount += item.amount;

      if (cat.code === 'TITHE') {
        totalTithe += item.amount;
      }
      if (cat.fundType === 'CONFERENCE_TRUST') {
        totalTrustFunds += item.amount;
      } else {
        totalLocalChurchFunds += item.amount;
      }
    }

    // Expenditures paid this month
    const paidVouchers = await prisma.expenditureVoucher.findMany({
      where: {
        paidAt: { gte: startDate, lte: endDate },
        status: 'PAID',
      },
      include: { department: true },
    });

    const totalExpenditure = paidVouchers.reduce((acc, v) => acc + v.amount, 0);

    // Net Local Church Operating Position = Local Inflow - Local Outflow
    const netLocalPosition = totalLocalChurchFunds - totalExpenditure;

    res.json({
      period: { year: targetYear, month: targetMonth },
      conferenceTrust: {
        totalTithe,
        totalTrustFunds,
        remittanceObligationToConference: totalTrustFunds, // 100% of trust funds remitted
      },
      localChurch: {
        totalLocalChurchFunds,
        totalExpenditure,
        netLocalPosition,
      },
      categoryBreakdown: Object.values(categoryBreakdown),
      paidVouchers,
    });
  } catch (err) {
    next(err);
  }
});

export default router;
