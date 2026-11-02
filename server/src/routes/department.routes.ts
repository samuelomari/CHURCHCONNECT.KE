import { Router, Response } from 'express';
import { z } from 'zod';
import { prisma } from '../prisma/client';
import { authenticate, authorize, AuthRequest, createAuditLog } from '../middleware/auth';

const router = Router();

const departmentSchema = z.object({
  name: z.string().min(2),
  code: z.string().min(2).max(10),
  description: z.string().optional().nullable(),
  leaderId: z.string().optional().nullable(),
  budgetAllocation: z.number().min(0).default(0),
});

router.get('/', authenticate, async (_req, res, next) => {
  try {
    const departments = await prisma.department.findMany({
      include: {
        leader: {
          select: { id: true, fullName: true, email: true, phone: true },
        },
        _count: {
          select: { churchMembers: true, vouchers: true },
        },
      },
      orderBy: { name: 'asc' },
    });

    const enriched = departments.map((d) => ({
      ...d,
      budgetRemaining: Math.max(0, d.budgetAllocation - d.budgetSpent),
      memberCount: d._count.churchMembers,
      voucherCount: d._count.vouchers,
    }));

    res.json(enriched);
  } catch (err) {
    next(err);
  }
});

router.get('/:id', authenticate, async (req: AuthRequest, res: Response, next) => {
  try {
    const dept = await prisma.department.findUnique({
      where: { id: req.params.id },
      include: {
        leader: {
          select: { id: true, fullName: true, email: true, phone: true },
        },
        churchMembers: {
          select: {
            id: true,
            memberNumber: true,
            firstName: true,
            lastName: true,
            phone: true,
            status: true,
          },
        },
        vouchers: {
          orderBy: { createdAt: 'desc' },
          take: 20,
          include: {
            requestedBy: { select: { fullName: true } },
          },
        },
        events: {
          orderBy: { startDate: 'asc' },
        },
      },
    });

    if (!dept) {
      res.status(404).json({ error: 'Department not found' });
      return;
    }

    res.json({
      ...dept,
      budgetRemaining: Math.max(0, dept.budgetAllocation - dept.budgetSpent),
    });
  } catch (err) {
    next(err);
  }
});

router.post('/', authenticate, authorize(['CHURCH_ADMIN', 'PASTOR', 'HEAD_TREASURER']), async (req: AuthRequest, res: Response, next) => {
  try {
    const data = departmentSchema.parse(req.body);

    const existingCode = await prisma.department.findUnique({ where: { code: data.code.toUpperCase() } });
    if (existingCode) {
      res.status(409).json({ error: `Department code ${data.code} already exists` });
      return;
    }

    const dept = await prisma.department.create({
      data: {
        name: data.name,
        code: data.code.toUpperCase(),
        description: data.description || null,
        leaderId: data.leaderId || null,
        budgetAllocation: data.budgetAllocation || 0,
      },
      include: { leader: true },
    });

    await createAuditLog(req.user!.id, 'CREATE_DEPARTMENT', 'Department', dept.id, { name: dept.name, code: dept.code }, req.ip);

    res.status(201).json(dept);
  } catch (err) {
    next(err);
  }
});

router.put('/:id', authenticate, authorize(['CHURCH_ADMIN', 'PASTOR', 'HEAD_TREASURER']), async (req: AuthRequest, res: Response, next) => {
  try {
    const data = departmentSchema.partial().parse(req.body);

    const updated = await prisma.department.update({
      where: { id: req.params.id },
      data: {
        ...data,
        code: data.code ? data.code.toUpperCase() : undefined,
      },
      include: { leader: true },
    });

    await createAuditLog(req.user!.id, 'UPDATE_DEPARTMENT', 'Department', updated.id, { name: updated.name }, req.ip);

    res.json(updated);
  } catch (err) {
    next(err);
  }
});

export default router;
