// ─── Types ────────────────────────────────────────────────────────────────────

export interface PostMetadata {
  title: string;
  url: string;
  excerpt: string;
  tags: string[];
  content: string;
}

export interface ShortUrls {
  linkedin: string;
  bluesky: string;
}

// ─── Payload normalization ────────────────────────────────────────────────────

export function normalizePayload(payload: Record<string, unknown>): PostMetadata {
  // Ghost CMS native format
  if (payload.post && typeof payload.post === 'object') {
    const post = (payload.post as Record<string, unknown>).current as Record<string, unknown>;
    return {
      title: String(post.title ?? ''),
      url: String(post.url ?? ''),
      excerpt: String(post.excerpt ?? post.custom_excerpt ?? ''),
      tags: Array.isArray(post.tags)
        ? (post.tags as Array<{ name: string }>).map(t => t.name)
        : [],
      content: String(post.plaintext ?? ''),
    };
  }
  // Custom flat format
  return {
    title: String(payload.title ?? ''),
    url: String(payload.url ?? ''),
    excerpt: String(payload.excerpt ?? ''),
    tags: Array.isArray(payload.tags) ? (payload.tags as string[]) : [],
    content: String(payload.content ?? payload.content_preview ?? ''),
  };
}

// ─── URL shortening ───────────────────────────────────────────────────────────

function extractSlug(url: string): string {
  try {
    const parts = new URL(url).pathname.replace(/\/$/, '').split('/');
    return parts[parts.length - 1] || 'post';
  } catch {
    return 'post';
  }
}

async function shortenWithTinyURL(longUrl: string, token: string): Promise<string> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10_000);
  try {
    const res = await fetch('https://api.tinyurl.com/create', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ url: longUrl, domain: 'tinyurl.com' }),
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(`TinyURL error ${res.status}`);
    const data = await res.json();
    return data.data?.tiny_url ?? longUrl;
  } catch {
    return longUrl; // fallback to long URL
  } finally {
    clearTimeout(timeout);
  }
}

export async function generateShortUrls(
  baseUrl: string,
  tinyurlToken: string
): Promise<ShortUrls> {
  const slug = extractSlug(baseUrl);
  const linkedinLong = `${baseUrl}?utm_source=linkedin&utm_medium=social&utm_campaign=${slug}`;
  const blueskyLong = `${baseUrl}?utm_source=bluesky&utm_medium=social&utm_campaign=${slug}`;
  const [linkedin, bluesky] = await Promise.all([
    shortenWithTinyURL(linkedinLong, tinyurlToken),
    shortenWithTinyURL(blueskyLong, tinyurlToken),
  ]);
  return { linkedin, bluesky };
}

// ─── Social post generation ───────────────────────────────────────────────────

const LINKEDIN_PROMPT = `You are a LinkedIn content specialist with expertise in AI and technology content.
Create a high-engagement LinkedIn post for a blog article using the details below.

Blog Title: {title}
Blog URL: {url}
Excerpt: {excerpt}
Tags: {tags}

Full Article Content:
{content}

---

LINKEDIN POST REQUIREMENTS:
Structure:
1. Open with a compelling problem statement hook
2. "I just published [brief description]"
3. "What makes this approach powerful:" followed by 4-5 checkmark bullets (✅) with concrete benefits
4. "Perfect for:" followed by 5-6 bullet points (•) of specific use cases
5. Call to action with the blog URL: {url}
6. Engagement question
7. 8-10 relevant hashtags

Tone: Professional but conversational. Never invent claims not in the article.
Length: 1,200–1,500 characters.
Output the LinkedIn post only.`;

const BLUESKY_PROMPT = `You are a social media specialist with expertise in AI and technology content.
Create a high-engagement Bluesky post for a blog article using the details below.

Blog Title: {title}
Blog URL: {url}
Excerpt: {excerpt}
Tags: {tags}

Full Article Content:
{content}

---

BLUESKY POST REQUIREMENTS:
Structure:
1. Emoji + one punchy statement (max 10 words)
2. 2-3 lines expanding on the insight
3. "Just published:" + one sentence summary
4. 3-4 bullet points using → arrows with concrete topics covered
5. Closing sentence reinforcing value
6. The blog URL: {url}

Max 300 characters. Output the Bluesky post only.`;

async function callAnthropic(prompt: string, apiKey: string): Promise<string> {
  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      model: 'claude-haiku-4-5-20251001',
      max_tokens: 1024,
      messages: [{ role: 'user', content: prompt }],
    }),
  });
  if (!res.ok) throw new Error(`Anthropic API error ${res.status}`);
  const data = await res.json();
  return data.content?.[0]?.text ?? '';
}

export async function generateSocialPosts(
  metadata: PostMetadata,
  shortUrls: ShortUrls,
  anthropicApiKey: string
): Promise<{ linkedin: string; bluesky: string }> {
  const tagsStr = metadata.tags.join(', ');
  const buildPrompt = (template: string, url: string) =>
    template
      .replace(/{title}/g, metadata.title)
      .replace(/{url}/g, url)
      .replace(/{excerpt}/g, metadata.excerpt)
      .replace(/{tags}/g, tagsStr)
      .replace(/{content}/g, metadata.content.slice(0, 8000));

  const [linkedin, bluesky] = await Promise.all([
    callAnthropic(buildPrompt(LINKEDIN_PROMPT, shortUrls.linkedin), anthropicApiKey),
    callAnthropic(buildPrompt(BLUESKY_PROMPT, shortUrls.bluesky), anthropicApiKey),
  ]);
  return {
    linkedin: linkedin.slice(0, 3000),
    bluesky: bluesky.slice(0, 300),
  };
}

// ─── Email ────────────────────────────────────────────────────────────────────

function escapeHTML(s: string): string {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function buildHtmlEmail(
  metadata: PostMetadata,
  posts: { linkedin: string; bluesky: string } | null,
  errorMessage: string | null
): string {
  const style = `body{font-family:Arial,sans-serif;line-height:1.6;color:#333;max-width:600px;margin:0 auto;padding:20px}
h1{color:#2563eb}h2{color:#1e40af;margin-top:30px}
.error{background:#fee2e2;border-left:4px solid #dc2626;padding:15px;margin:20px 0}
.meta{background:#f3f4f6;padding:15px;border-radius:5px;margin:20px 0}
.box{background:#f9fafb;border:1px solid #e5e7eb;padding:15px;border-radius:5px;margin:15px 0;font-family:monospace;white-space:pre-wrap}
a{color:#2563eb}`;

  const metaBlock = `<div class="meta">
<p><strong>Title:</strong> ${escapeHTML(metadata.title)}</p>
<p><strong>URL:</strong> <a href="${escapeHTML(metadata.url)}">${escapeHTML(metadata.url)}</a></p>
<p><strong>Excerpt:</strong> ${escapeHTML(metadata.excerpt)}</p>
<p><strong>Tags:</strong> ${escapeHTML(metadata.tags.join(', '))}</p>
</div>`;

  if (errorMessage || !posts) {
    return `<!DOCTYPE html><html><head><meta charset="UTF-8"><style>${style}</style></head><body>
<h1>🚨 New Blog Post Published (Error Generating Posts)</h1>
<div class="error"><strong>Error:</strong> ${escapeHTML(errorMessage ?? 'Unknown error')}</div>
${metaBlock}
</body></html>`;
  }

  return `<!DOCTYPE html><html><head><meta charset="UTF-8"><style>${style}</style></head><body>
<h1>✅ New Blog Post Published!</h1>
${metaBlock}
<h2>📘 LinkedIn Post</h2>
<div class="box">${escapeHTML(posts.linkedin)}</div>
<h2>🦋 Bluesky Post</h2>
<div class="box">${escapeHTML(posts.bluesky)}</div>
</body></html>`;
}

export interface EmailConfig {
  mailgunApiKey: string;
  mailgunDomain: string;
  emailFrom: string;
  emailTo: string;
}

export async function sendEmail(
  metadata: PostMetadata,
  posts: { linkedin: string; bluesky: string } | null,
  errorMessage: string | null,
  config: EmailConfig
): Promise<void> {
  const html = buildHtmlEmail(metadata, posts, errorMessage);
  const subject = posts
    ? `New Blog Post: ${metadata.title} - Social Media Content Ready`
    : `New Blog Post: ${metadata.title} - Error Generating Posts`;

  const form = new FormData();
  form.append('from', config.emailFrom);
  form.append('to', config.emailTo);
  form.append('subject', subject);
  form.append('html', html);

  const res = await fetch(
    `https://api.mailgun.net/v3/${config.mailgunDomain}/messages`,
    {
      method: 'POST',
      headers: { Authorization: `Basic ${btoa(`api:${config.mailgunApiKey}`)}` },
      body: form,
    }
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Mailgun error ${res.status}: ${text}`);
  }
}

// ─── Main orchestrator ────────────────────────────────────────────────────────

export interface WebhookEnv {
  tinyurlToken: string;
  anthropicApiKey: string;
  mailgunApiKey: string;
  mailgunDomain: string;
  emailFrom: string;
  emailTo: string;
}

export async function processWebhook(
  metadata: PostMetadata,
  env: WebhookEnv
): Promise<void> {
  // 1. Shorten URLs (with fallback)
  let shortUrls: ShortUrls;
  try {
    shortUrls = await generateShortUrls(metadata.url, env.tinyurlToken);
  } catch {
    const slug = extractSlug(metadata.url);
    shortUrls = {
      linkedin: `${metadata.url}?utm_source=linkedin&utm_medium=social&utm_campaign=${slug}`,
      bluesky: `${metadata.url}?utm_source=bluesky&utm_medium=social&utm_campaign=${slug}`,
    };
  }

  // 2. Generate social posts
  let posts: { linkedin: string; bluesky: string } | null = null;
  let postError: string | null = null;
  try {
    posts = await generateSocialPosts(metadata, shortUrls, env.anthropicApiKey);
  } catch (err) {
    postError = (err as Error).message;
  }

  // 3. Send email (best-effort)
  await sendEmail(metadata, posts, postError, {
    mailgunApiKey: env.mailgunApiKey,
    mailgunDomain: env.mailgunDomain,
    emailFrom: env.emailFrom,
    emailTo: env.emailTo,
  });
}
