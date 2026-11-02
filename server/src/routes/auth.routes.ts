import { Router, Response } from 'express';
import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import { z } from 'zod';
import { prisma } from '../prisma/client';
import { authenticate, authorize, AuthRequest, createAuditLog } from '../middleware/auth';

const router = Router();
const JWT_SECRET = process.env.JWT_SECRET || 'churchconnect_secure_jwt_secret_key_2026_sda_ke';
const JWT_EXPIRES_IN = process.env.JWT_EXPIRES_IN || '7d';

const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(6),
});

router.post('/login', async (req, res, next) => {
  try {
    const { email, password } = loginSchema.parse(req.body);

    const user = await prisma.user.findUnique({
      where: { email: email.toLowerCase() },
      include: {
        department: true,
        ledDepartment: true,
      },
    });

    if (!user || !user.active) {
      res.status(401).json({ error: 'Invalid email credentials or inactive account' });
      return;
    }

    const isMatch = await bcrypt.compare(password, user.passwordHash);
    if (!isMatch) {
      res.status(401).json({ error: 'Invalid password credentials' });
      return;
    }

    const token = jwt.sign(
      { id: user.id, email: user.email, role: user.role },
      JWT_SECRET,
      { expiresIn: JWT_EXPIRES_IN }
    );

    await createAuditLog(user.id, 'LOGIN', 'User', user.id, { email: user.email, role: user.role }, req.ip);

    res.json({
      token,
      user: {
        id: user.id,
        email: user.email,
        fullName: user.fullName,
        phone: user.phone,
        role: user.role,
        departmentId: user.departmentId,
        departmentName: user.department?.name || user.ledDepartment?.name || null,
      },
    });
  } catch (err) {
    next(err);
  }
});

router.get('/me', authenticate, async (req: AuthRequest, res: Response, next) => {
  try {
    const user = await prisma.user.findUnique({
      where: { id: req.user!.id },
      select: {
        id: true,
        email: true,
        fullName: true,
        phone: true,
        role: true,
        departmentId: true,
        active: true,
        department: { select: { id: true, name: true, code: true } },
        ledDepartment: { select: { id: true, name: true, code: true } },
      },
    });

    if (!user) {
      res.status(404).json({ error: 'User not found' });
      return;
    }

    res.json({
      ...user,
      departmentName: user.department?.name || user.ledDepartment?.name || null,
    });
  } catch (err) {
    next(err);
  }
});

const changePasswordSchema = z.object({
  currentPassword: z.string(),
  newPassword: z.string().min(6),
});

router.post('/change-password', authenticate, async (req: AuthRequest, res: Response, next) => {
  try {
    const { currentPassword, newPassword } = changePasswordSchema.parse(req.body);

    const user = await prisma.user.findUnique({
      where: { id: req.user!.id },
    });

    if (!user) {
      res.status(404).json({ error: 'User not found' });
      return;
    }

    const isMatch = await bcrypt.compare(currentPassword, user.passwordHash);
    if (!isMatch) {
      res.status(400).json({ error: 'Incorrect current password' });
      return;
    }

    const newHash = await bcrypt.hash(newPassword, 10);
    await prisma.user.update({
      where: { id: user.id },
      data: { passwordHash: newHash },
    });

    await createAuditLog(user.id, 'CHANGE_PASSWORD', 'User', user.id, {}, req.ip);

    res.json({ message: 'Password updated successfully' });
  } catch (err) {
    next(err);
  }
});

router.get('/users', authenticate, authorize(['CHURCH_ADMIN', 'PASTOR', 'FIRST_ELDER', 'HEAD_TREASURER']), async (_req, res, next) => {
  try {
    const users = await prisma.user.findMany({
      select: {
        id: true,
        email: true,
        fullName: true,
        phone: true,
        role: true,
        active: true,
        departmentId: true,
        department: { select: { id: true, name: true } },
        createdAt: true,
      },
      orderBy: { fullName: 'asc' },
    });

    res.json(users);
  } catch (err) {
    next(err);
  }
});

const registerOfficerSchema = z.object({
  email: z.string().email(),
  password: z.string().min(6),
  fullName: z.string().min(2),
  phone: z.string().optional(),
  role: z.string(),
  departmentId: z.string().optional().nullable(),
});

router.post('/register-officer', authenticate, authorize(['CHURCH_ADMIN', 'PASTOR']), async (req: AuthRequest, res: Response, next) => {
  try {
    const data = registerOfficerSchema.parse(req.body);
    const existing = await prisma.user.findUnique({ where: { email: data.email.toLowerCase() } });
    if (existing) {
      res.status(409).json({ error: 'User with this email already exists' });
      return;
    }

    const passwordHash = await bcrypt.hash(data.password, 10);
    const newUser = await prisma.user.create({
      data: {
        email: data.email.toLowerCase(),
        passwordHash,
        fullName: data.fullName,
        phone: data.phone || null,
        role: data.role,
        departmentId: data.departmentId || null,
      },
      select: {
        id: true,
        email: true,
        fullName: true,
        phone: true,
        role: true,
        departmentId: true,
      },
    });

    await createAuditLog(req.user!.id, 'REGISTER_OFFICER', 'User', newUser.id, { email: newUser.email, role: newUser.role }, req.ip);

    res.status(201).json(newUser);
  } catch (err) {
    next(err);
  }
});

export default router;
