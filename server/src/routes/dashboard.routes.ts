import { Router, Response } from 'express';
import { prisma } from '../prisma/client';
import { authenticate, authorize, AuthRequest } from '../middleware/auth';

const router = Router();

router.get('/overview', authenticate, async (req: AuthRequest, res: Response, next) => {
  try {
    const role = req.user?.role;
    const departmentId = req.user?.departmentId;

    // 1. General Metrics
    const totalMembers = await prisma.member.count({ where: { status: 'ACTIVE' } });
    const totalDepartments = await prisma.department.count();

    // 2. Financial Metrics (Year to Date)
    const currentYear = new Date().getFullYear();
    const startOfYear = new Date(currentYear, 0, 1);

    const envelopesYTD = await prisma.TitheOfferingEnvelope.findMany({
      where: {
        transactionDate: { gte: startOfYear },
        status: 'CONFIRMED',
      },
      include: {
        items: { include: { fundCategory: true } },
      },
    });

    let totalInflowYTD = 0;
    let totalTitheYTD = 0;
    let totalLocalChurchYTD = 0;
    const categoryTotals: Record<string, { name: string; amount: number; type: string }> = {};

    for (const env of envelopesYTD) {
      totalInflowYTD += env.totalAmount;
      for (const item of env.items) {
        const cat = item.fundCategory;
        if (!categoryTotals[cat.name]) {
          categoryTotals[cat.name] = { name: cat.name, amount: 0, type: cat.fundType };
        }
        categoryTotals[cat.name].amount += item.amount;

        if (cat.code === 'TITHE') {
          totalTitheYTD += item.amount;
        }
        if (cat.fundType === 'LOCAL_CHURCH') {
          totalLocalChurchYTD += item.amount;
        }
      }
    }

    // 3. Vouchers & Expenditures
    const vouchersYTD = await prisma.expenditureVoucher.findMany({
      where: {
        createdAt: { gte: startOfYear },
      },
    });

    const totalExpenditureYTD = vouchersYTD
      .filter((v) => v.status === 'PAID')
      .reduce((sum, v) => sum + v.amount, 0);

    const pendingTreasurerCount = vouchersYTD.filter((v) => v.status === 'SUBMITTED').length;
    const pendingElderCount = vouchersYTD.filter((v) => v.status === 'TREASURER_REVIEWED').length;

    // 4. Monthly Trend Data (Last 6 Months)
    const monthsData: { month: string; tithe: number; localChurch: number; expenditure: number }[] = [];
    for (let i = 5; i >= 0; i--) {
      const d = new Date();
      d.setMonth(d.getMonth() - i);
      const year = d.getFullYear();
      const monthIndex = d.getMonth();
      const mStart = new Date(year, monthIndex, 1);
      const mEnd = new Date(year, monthIndex + 1, 0, 23, 59, 59);
      const mName = mStart.toLocaleString('default', { month: 'short' });

      // Envelopes in this month
      const mEnvelopes = await prisma.envelopeItem.findMany({
        where: {
          envelope: {
            transactionDate: { gte: mStart, lte: mEnd },
            status: 'CONFIRMED',
          },
        },
        include: { fundCategory: true },
      });

      let mTithe = 0;
      let mLocal = 0;
      mEnvelopes.forEach((it) => {
        if (it.fundCategory.code === 'TITHE') mTithe += it.amount;
        if (it.fundCategory.fundType === 'LOCAL_CHURCH') mLocal += it.amount;
      });

      const mExpenditure = await prisma.expenditureVoucher.aggregate({
        where: {
          paidAt: { gte: mStart, lte: mEnd },
          status: 'PAID',
        },
        _sum: { amount: true },
      });

      monthsData.push({
        month: mName,
        tithe: mTithe,
        localChurch: mLocal,
        expenditure: mExpenditure._sum.amount || 0,
      });
    }

    // 5. Recent Activity
    const recentEnvelopes = await prisma.TitheOfferingEnvelope.findMany({
      take: 5,
      orderBy: { transactionDate: 'desc' },
      include: {
        member: { select: { firstName: true, lastName: true } },
      },
    });

    const recentVouchers = await prisma.expenditureVoucher.findMany({
      take: 5,
      orderBy: { createdAt: 'desc' },
      include: {
        department: { select: { name: true } },
      },
    });

    // 6. Upcoming Events
    const upcomingEvents = await prisma.event.findMany({
      where: {
        startDate: { gte: new Date() },
      },
      orderBy: { startDate: 'asc' },
      take: 3,
    });

    // 7. Department leader specific info
    let deptInfo = null;
    if (departmentId) {
      deptInfo = await prisma.department.findUnique({
        where: { id: departmentId },
      });
    }

    res.json({
      role,
      summary: {
        totalMembers,
        totalDepartments,
        totalInflowYTD,
        totalTitheYTD,
        totalLocalChurchYTD,
        totalExpenditureYTD,
        netLocalReserves: totalLocalChurchYTD - totalExpenditureYTD,
        pendingTreasurerCount,
        pendingElderCount,
      },
      categoryDistribution: Object.values(categoryTotals),
      monthlyTrends: monthsData,
      recentEnvelopes,
      recentVouchers,
      upcomingEvents,
      deptInfo,
    });
  } catch (err) {
    next(err);
  }
});

router.get('/audit-logs', authenticate, authorize(['CHURCH_ADMIN', 'PASTOR', 'FIRST_ELDER', 'HEAD_TREASURER', 'AUDITOR']), async (_req, res, next) => {
  try {
    const logs = await prisma.auditLog.findMany({
      take: 100,
      orderBy: { createdAt: 'desc' },
      include: {
        user: { select: { fullName: true, role: true, email: true } },
      },
    });
    res.json(logs);
  } catch (err) {
    next(err);
  }
});

export default router;
