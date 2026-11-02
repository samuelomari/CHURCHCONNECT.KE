import { Router, Response } from 'express';
import { z } from 'zod';
import { prisma } from '../prisma/client';
import { authenticate, authorize, AuthRequest, createAuditLog } from '../middleware/auth';

const router = Router();

// ==========================================
// 1. EVENTS & PROGRAMMES
// ==========================================

const eventSchema = z.object({
  title: z.string().min(2),
  description: z.string().optional().nullable(),
  departmentId: z.string().optional().nullable(),
  coordinatorId: z.string().optional().nullable(),
  location: z.string().min(2),
  startDate: z.string(),
  endDate: z.string(),
  isPublic: z.boolean().default(true),
});

router.get('/', authenticate, async (req: AuthRequest, res: Response, next) => {
  try {
    const { departmentId } = req.query;
    const where: any = {};
    if (departmentId && typeof departmentId === 'string') {
      where.departmentId = departmentId;
    }

    const events = await prisma.event.findMany({
      where,
      include: {
        department: { select: { id: true, name: true, code: true } },
        coordinator: { select: { id: true, fullName: true } },
      },
      orderBy: { startDate: 'asc' },
    });

    res.json(events);
  } catch (err) {
    next(err);
  }
});

router.post('/', authenticate, authorize(['CHURCH_ADMIN', 'PASTOR', 'FIRST_ELDER', 'CHURCH_CLERK', 'DEPARTMENT_LEADER']), async (req: AuthRequest, res: Response, next) => {
  try {
    const data = eventSchema.parse(req.body);

    const event = await prisma.event.create({
      data: {
        title: data.title,
        description: data.description || null,
        departmentId: data.departmentId || null,
        coordinatorId: data.coordinatorId || req.user!.id,
        location: data.location,
        startDate: new Date(data.startDate),
        endDate: new Date(data.endDate),
        isPublic: data.isPublic,
      },
      include: {
        department: true,
        coordinator: true,
      },
    });

    await createAuditLog(req.user!.id, 'CREATE_EVENT', 'Event', event.id, { title: event.title }, req.ip);

    res.status(201).json(event);
  } catch (err) {
    next(err);
  }
});

// ==========================================
// 2. ATTENDANCE TRACKING
// ==========================================

const attendanceSchema = z.object({
  serviceType: z.enum(['SABBATH_SCHOOL', 'DIVINE_SERVICE', 'YOUTH_SERVICE', 'MIDWEEK_PRAYER', 'SPECIAL_EVENT']),
  date: z.string(),
  adultCount: z.number().int().min(0),
  childrenCount: z.number().int().min(0),
  visitorsCount: z.number().int().min(0),
  notes: z.string().optional().nullable(),
});

router.get('/attendance', authenticate, async (_req, res, next) => {
  try {
    const records = await prisma.attendance.findMany({
      include: {
        recordedBy: { select: { id: true, fullName: true } },
      },
      orderBy: { date: 'desc' },
      take: 50,
    });
    res.json(records);
  } catch (err) {
    next(err);
  }
});

router.post('/attendance', authenticate, authorize(['CHURCH_ADMIN', 'CHURCH_CLERK', 'PASTOR', 'FIRST_ELDER']), async (req: AuthRequest, res: Response, next) => {
  try {
    const data = attendanceSchema.parse(req.body);
    const totalCount = data.adultCount + data.childrenCount + data.visitorsCount;

    const record = await prisma.attendance.create({
      data: {
        serviceType: data.serviceType,
        date: new Date(data.date),
        adultCount: data.adultCount,
        childrenCount: data.childrenCount,
        visitorsCount: data.visitorsCount,
        totalCount,
        notes: data.notes || null,
        recordedById: req.user!.id,
      },
      include: { recordedBy: true },
    });

    await createAuditLog(req.user!.id, 'RECORD_ATTENDANCE', 'Attendance', record.id, { serviceType: record.serviceType, totalCount }, req.ip);

    res.status(201).json(record);
  } catch (err) {
    next(err);
  }
});

export default router;
