import { Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';
import { prisma } from '../prisma/client';

const JWT_SECRET = process.env.JWT_SECRET || 'churchconnect_secure_jwt_secret_key_2026_sda_ke';

export interface AuthenticatedUser {
  id: string;
  email: string;
  fullName: string;
  role: string;
  departmentId?: string | null;
}

export interface AuthRequest extends Request {
  user?: AuthenticatedUser;
}

export const authenticate = async (req: AuthRequest, res: Response, next: NextFunction): Promise<void> => {
  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    res.status(401).json({ error: 'Authorization header missing or invalid' });
    return;
  }

  const token = authHeader.split(' ')[1];
  try {
    const decoded = jwt.verify(token, JWT_SECRET) as { id: string; email: string; role: string };
    const user = await prisma.user.findUnique({
      where: { id: decoded.id },
      select: {
        id: true,
        email: true,
        fullName: true,
        role: true,
        departmentId: true,
        active: true,
      },
    });

    if (!user || !user.active) {
      res.status(401).json({ error: 'User is inactive or not found' });
      return;
    }

    req.user = user;
    next();
  } catch (err) {
    res.status(401).json({ error: 'Invalid or expired token' });
  }
};

export const authorize = (allowedRoles: string[]) => {
  return (req: AuthRequest, res: Response, next: NextFunction): void => {
    if (!req.user) {
      res.status(401).json({ error: 'Authentication required' });
      return;
    }

    if (req.user.role === 'CHURCH_ADMIN') {
      return next(); // Church admin has universal supervisory access
    }

    if (!allowedRoles.includes(req.user.role)) {
      res.status(403).json({
        error: `Access forbidden: Role '${req.user.role}' lacks permission for this action`,
      });
      return;
    }

    next();
  };
};

export const createAuditLog = async (
  userId: string | undefined,
  action: string,
  entity: string,
  entityId?: string,
  details?: Record<string, any>,
  ipAddress?: string
) => {
  try {
    await prisma.auditLog.create({
      data: {
        userId: userId || null,
        action,
        entity,
        entityId: entityId || null,
        details: details ? JSON.stringify(details) : null,
        ipAddress: ipAddress || null,
      },
    });
  } catch (error) {
    console.error('Audit log creation failed:', error);
  }
};
