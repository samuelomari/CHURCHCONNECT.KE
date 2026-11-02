import { Router, Response } from 'express';
import { z } from 'zod';
import { prisma } from '../prisma/client';
import { authenticate, authorize, AuthRequest, createAuditLog } from '../middleware/auth';

const router = Router();

const memberSchema = z.object({
  memberNumber: z.string().min(1),
  firstName: z.string().min(1),
  lastName: z.string().min(1),
  phone: z.string().optional().nullable(),
  email: z.string().email().optional().nullable().or(z.literal('')),
  gender: z.enum(['MALE', 'FEMALE']),
  dateOfBirth: z.string().optional().nullable(),
  baptismDate: z.string().optional().nullable(),
  baptismChurch: z.string().optional().nullable(),
  status: z.enum(['ACTIVE', 'TRANSFERRED', 'INACTIVE', 'DECEASED']).default('ACTIVE'),
  emergencyContactName: z.string().optional().nullable(),
  emergencyContactPhone: z.string().optional().nullable(),
  residence: z.string().optional().nullable(),
  departmentId: z.string().optional().nullable(),
});

router.get('/', authenticate, async (req: AuthRequest, res: Response, next) => {
  try {
    const { search, status, departmentId } = req.query;

    const where: any = {};
    if (status && typeof status === 'string') {
      where.status = status;
    }
    if (departmentId && typeof departmentId === 'string') {
      where.departmentId = departmentId;
    }
    if (search && typeof search === 'string') {
      where.OR = [
        { firstName: { contains: search } },
        { lastName: { contains: search } },
        { memberNumber: { contains: search } },
        { phone: { contains: search } },
      ];
    }

    const members = await prisma.member.findMany({
      where,
      include: {
        department: { select: { id: true, name: true, code: true } },
      },
      orderBy: { lastName: 'asc' },
    });

    res.json(members);
  } catch (err) {
    next(err);
  }
});

router.get('/stats/summary', authenticate, async (_req, res, next) => {
  try {
    const total = await prisma.member.count();
    const active = await prisma.member.count({ where: { status: 'ACTIVE' } });
    const male = await prisma.member.count({ where: { gender: 'MALE', status: 'ACTIVE' } });
    const female = await prisma.member.count({ where: { gender: 'FEMALE', status: 'ACTIVE' } });
    const baptized = await prisma.member.count({ where: { baptismDate: { not: null }, status: 'ACTIVE' } });

    res.json({
      total,
      active,
      male,
      female,
      baptized,
    });
  } catch (err) {
    next(err);
  }
});

router.get('/:id', authenticate, async (req: AuthRequest, res: Response, next) => {
  try {
    const member = await prisma.member.findUnique({
      where: { id: req.params.id },
      include: {
        department: true,
        envelopes: {
          take: 10,
          orderBy: { transactionDate: 'desc' },
          include: {
            items: {
              include: { fundCategory: true },
            },
          },
        },
      },
    });

    if (!member) {
      res.status(404).json({ error: 'Member not found' });
      return;
    }

    res.json(member);
  } catch (err) {
    next(err);
  }
});

router.post('/', authenticate, authorize(['CHURCH_ADMIN', 'CHURCH_CLERK', 'PASTOR']), async (req: AuthRequest, res: Response, next) => {
  try {
    const data = memberSchema.parse(req.body);

    const existingNumber = await prisma.member.findUnique({
      where: { memberNumber: data.memberNumber },
    });
    if (existingNumber) {
      res.status(409).json({ error: `Member number ${data.memberNumber} is already assigned.` });
      return;
    }

    const member = await prisma.member.create({
      data: {
        memberNumber: data.memberNumber,
        firstName: data.firstName,
        lastName: data.lastName,
        phone: data.phone || null,
        email: data.email || null,
        gender: data.gender,
        dateOfBirth: data.dateOfBirth ? new Date(data.dateOfBirth) : null,
        baptismDate: data.baptismDate ? new Date(data.baptismDate) : null,
        baptismChurch: data.baptismChurch || null,
        status: data.status,
        emergencyContactName: data.emergencyContactName || null,
        emergencyContactPhone: data.emergencyContactPhone || null,
        residence: data.residence || null,
        departmentId: data.departmentId || null,
      },
      include: { department: true },
    });

    await createAuditLog(req.user!.id, 'CREATE_MEMBER', 'Member', member.id, { memberNumber: member.memberNumber, name: `${member.firstName} ${member.lastName}` }, req.ip);

    res.status(201).json(member);
  } catch (err) {
    next(err);
  }
});

router.put('/:id', authenticate, authorize(['CHURCH_ADMIN', 'CHURCH_CLERK', 'PASTOR']), async (req: AuthRequest, res: Response, next) => {
  try {
    const data = memberSchema.partial().parse(req.body);

    const updated = await prisma.member.update({
      where: { id: req.params.id },
      data: {
        ...data,
        dateOfBirth: data.dateOfBirth ? new Date(data.dateOfBirth) : undefined,
        baptismDate: data.baptismDate ? new Date(data.baptismDate) : undefined,
      },
      include: { department: true },
    });

    await createAuditLog(req.user!.id, 'UPDATE_MEMBER', 'Member', updated.id, { memberNumber: updated.memberNumber }, req.ip);

    res.json(updated);
  } catch (err) {
    next(err);
  }
});

export default router;
