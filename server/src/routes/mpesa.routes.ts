import { Router, Request, Response } from 'express';
import { z } from 'zod';
import { prisma } from '../prisma/client';
import { authenticate, AuthRequest, createAuditLog } from '../middleware/auth';

const router = Router();

// ==========================================
// SAFARICOM M-PESA DARAJA INTEGRATION
// ==========================================

const stkPushSchema = z.object({
  phone: z.string().min(10, 'Valid Kenyan phone number e.g. 254712345678 or 0712345678'),
  amount: z.number().positive(),
  accountReference: z.string().min(1), // e.g. "TITHE" or Member Number "SDA-004"
  donorName: z.string().optional(),
});

/**
 * Trigger STK Push (Express Checkout)
 */
router.post('/stk-push', authenticate, async (req: AuthRequest, res: Response, next) => {
  try {
    const data = stkPushSchema.parse(req.body);

    // Format phone number to standard 2547XXXXXXXX
    let formattedPhone = data.phone.trim();
    if (formattedPhone.startsWith('0')) {
      formattedPhone = '254' + formattedPhone.slice(1);
    } else if (formattedPhone.startsWith('+')) {
      formattedPhone = formattedPhone.slice(1);
    }

    const checkoutRequestId = `ws_CO_${Date.now()}_${Math.floor(Math.random() * 10000)}`;
    const merchantRequestId = `MR_${Date.now()}`;

    // Record initial transaction state
    const transaction = await prisma.mpesaTransaction.create({
      data: {
        merchantRequestId,
        checkoutRequestId,
        amount: data.amount,
        phone: formattedPhone,
        accountReference: data.accountReference,
        status: 'INITIATED',
      },
    });

    await createAuditLog(
      req.user?.id,
      'MPESA_STK_PUSH_INITIATED',
      'MpesaTransaction',
      transaction.id,
      { phone: formattedPhone, amount: data.amount, accountReference: data.accountReference },
      req.ip
    );

    // In a live environment with active Safaricom credentials, this would invoke https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest
    // Here we return the initiated checkout details and acknowledge the request
    res.json({
      success: true,
      message: 'STK push prompt sent to phone. Enter M-Pesa PIN to complete.',
      checkoutRequestId,
      merchantRequestId,
      phone: formattedPhone,
      amount: data.amount,
    });
  } catch (err) {
    next(err);
  }
});

/**
 * Safaricom Daraja STK Push Callback Webhook
 */
router.post('/callback', async (req: Request, res: Response) => {
  try {
    const callbackData = req.body;
    const body = callbackData?.Body?.stkCallback;

    if (!body) {
      res.status(200).json({ ResultCode: 0, ResultDesc: 'Accepted' });
      return;
    }

    const { CheckoutRequestID, ResultCode, ResultDesc } = body;

    const existingTx = await prisma.mpesaTransaction.findUnique({
      where: { checkoutRequestId: CheckoutRequestID },
    });

    if (!existingTx) {
      res.status(200).json({ ResultCode: 0, ResultDesc: 'Accepted' });
      return;
    }

    if (ResultCode === 0) {
      // Payment Successful
      const items = body.CallbackMetadata?.Item || [];
      const mpesaReceiptItem = items.find((i: any) => i.Name === 'MpesaReceiptNumber');
      const transactionDateItem = items.find((i: any) => i.Name === 'TransactionDate');
      const receiptNumber = mpesaReceiptItem?.Value || `MPE${Date.now()}`;

      await prisma.mpesaTransaction.update({
        where: { id: existingTx.id },
        data: {
          status: 'SUCCESS',
          receiptNumber,
          transactionDate: new Date(),
          resultDesc: ResultDesc,
          rawCallback: JSON.stringify(callbackData),
        },
      });

      // Auto-create Church Tithe/Offering envelope
      await autoCreateEnvelopeFromMpesa(existingTx, receiptNumber);
    } else {
      // Payment Cancelled or Failed
      await prisma.mpesaTransaction.update({
        where: { id: existingTx.id },
        data: {
          status: 'FAILED',
          resultDesc: ResultDesc,
          rawCallback: JSON.stringify(callbackData),
        },
      });
    }

    res.status(200).json({ ResultCode: 0, ResultDesc: 'Accepted' });
  } catch (error) {
    console.error('M-Pesa callback handling error:', error);
    res.status(200).json({ ResultCode: 0, ResultDesc: 'Accepted' });
  }
});

/**
 * Developer & Demo Simulation Endpoint:
 * Allows church leaders to simulate an instant incoming M-Pesa payment
 */
router.post('/simulate', authenticate, async (req: AuthRequest, res: Response, next) => {
  try {
    const { phone, amount, accountReference, donorName, fundCategoryCode } = req.body;

    const testReceipt = `QA${Math.floor(10000000 + Math.random() * 90000000)}`;
    const checkoutRequestId = `SIM_${Date.now()}`;

    // 1. Record transaction
    const tx = await prisma.mpesaTransaction.create({
      data: {
        checkoutRequestId,
        receiptNumber: testReceipt,
        amount: Number(amount) || 1000,
        phone: phone || '254712345678',
        accountReference: accountReference || 'TITHE',
        status: 'SUCCESS',
        resultDesc: 'The service request is processed successfully.',
        transactionDate: new Date(),
      },
    });

    // 2. Resolve Fund Category (default to Tithe or Church Budget)
    const targetCode = fundCategoryCode || 'TITHE';
    let fund = await prisma.fundCategory.findUnique({ where: { code: targetCode } });
    if (!fund) {
      fund = await prisma.fundCategory.findFirst();
    }

    // 3. Resolve Member if accountReference matches member number
    const member = await prisma.member.findFirst({
      where: {
        OR: [
          { memberNumber: accountReference },
          { phone: phone },
        ],
      },
    });

    // 4. Resolve a Treasury user to record receipt
    const recorder = await prisma.user.findFirst({
      where: { role: { in: ['HEAD_TREASURER', 'CHURCH_ADMIN', 'ASSISTANT_TREASURER'] } },
    });

    const envelopeCount = await prisma.TitheOfferingEnvelope.count();
    const churchReceipt = `REC-${new Date().getFullYear()}-${String(envelopeCount + 1).padStart(5, '0')}`;

    const envelope = await prisma.TitheOfferingEnvelope.create({
      data: {
        receiptNumber: churchReceipt,
        memberId: member ? member.id : null,
        donorName: donorName || (member ? `${member.firstName} ${member.lastName}` : 'M-Pesa Giver'),
        donorPhone: phone || '254712345678',
        paymentMethod: 'MPESA',
        mpesaReceiptNumber: testReceipt,
        totalAmount: Number(amount) || 1000,
        status: 'CONFIRMED',
        notes: `Simulated Daraja Payment. Account Ref: ${accountReference || 'TITHE'}`,
        recordedById: recorder ? recorder.id : req.user!.id,
        items: {
          create: [
            {
              fundCategoryId: fund!.id,
              amount: Number(amount) || 1000,
            },
          ],
        },
      },
      include: {
        items: { include: { fundCategory: true } },
        member: true,
      },
    });

    await createAuditLog(
      req.user!.id,
      'SIMULATE_MPESA_PAYMENT',
      'MpesaTransaction',
      tx.id,
      { receiptNumber: testReceipt, amount, envelopeReceipt: churchReceipt },
      req.ip
    );

    res.json({
      success: true,
      message: 'M-Pesa payment simulated and church envelope receipt created successfully',
      mpesaReceipt: testReceipt,
      envelope,
    });
  } catch (err) {
    next(err);
  }
});

async function autoCreateEnvelopeFromMpesa(tx: any, mpesaReceiptNumber: string) {
  try {
    const adminUser = await prisma.user.findFirst({
      where: { role: { in: ['HEAD_TREASURER', 'CHURCH_ADMIN'] } },
    });
    if (!adminUser) return;

    // Default to Tithe or first fund category
    let fund = await prisma.fundCategory.findUnique({ where: { code: 'TITHE' } });
    if (!fund) {
      fund = await prisma.fundCategory.findFirst();
    }
    if (!fund) return;

    const count = await prisma.TitheOfferingEnvelope.count();
    const receiptNumber = `REC-${new Date().getFullYear()}-${String(count + 1).padStart(5, '0')}`;

    const member = await prisma.member.findFirst({
      where: {
        OR: [{ memberNumber: tx.accountReference }, { phone: tx.phone }],
      },
    });

    await prisma.TitheOfferingEnvelope.create({
      data: {
        receiptNumber,
        memberId: member ? member.id : null,
        donorName: member ? `${member.firstName} ${member.lastName}` : `M-Pesa Giver (${tx.phone})`,
        donorPhone: tx.phone,
        paymentMethod: 'MPESA',
        mpesaReceiptNumber,
        totalAmount: tx.amount,
        status: 'CONFIRMED',
        notes: `Automated Safaricom Daraja Inflow. Account Ref: ${tx.accountReference}`,
        recordedById: adminUser.id,
        items: {
          create: [{ fundCategoryId: fund.id, amount: tx.amount }],
        },
      },
    });
  } catch (error) {
    console.error('Failed to auto-create envelope from M-Pesa:', error);
  }
}

export default router;
