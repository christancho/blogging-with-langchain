import { after } from 'next/server';
import { normalizePayload, processWebhook, type WebhookEnv } from '@/lib/webhook';

export async function POST(request: Request) {
  let payload: Record<string, unknown>;
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  const metadata = normalizePayload(payload);

  const env: WebhookEnv = {
    tinyurlToken: process.env.TINYURL_API_TOKEN ?? '',
    anthropicApiKey: process.env.ANTHROPIC_API_KEY ?? '',
    mailgunApiKey: process.env.MAILGUN_API_KEY ?? '',
    mailgunDomain: process.env.MAILGUN_DOMAIN ?? '',
    emailFrom: process.env.EMAIL_FROM ?? '',
    emailTo: process.env.EMAIL_TO ?? '',
  };

  // Respond immediately — process in background after response is sent
  after(async () => {
    try {
      await processWebhook(metadata, env);
    } catch (err) {
      console.error('Webhook background processing failed:', err);
    }
  });

  return Response.json({ success: true, message: 'Notification queued for processing' });
}
