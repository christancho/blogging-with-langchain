# Blog Notification Webhook

Cloudflare Worker that sends email notifications with AI-generated social media posts when blog articles are published.

## Features

- 📧 Email notifications via Mailgun
- 🤖 AI-generated LinkedIn posts (professional tone, <3000 chars)
- 🦋 AI-generated Bluesky posts (conversational tone, <300 chars)
- 🔄 Handles both Ghost CMS webhooks and custom publisher calls
- ⚡ Serverless edge deployment with Cloudflare Workers
- 🛡️ Built-in error handling and fallback emails

## Architecture

```
Ghost CMS (post.published event) → Cloudflare Worker → Anthropic API → Mailgun → Email
                                          ↓
                                   (generates posts)
```

**Trigger**: Ghost CMS webhook fires when any post is published (via Python script or Ghost admin UI)

## Prerequisites

- Cloudflare account (free tier works)
- Mailgun account (free tier: 5,000 emails/month)
- Anthropic API key (for Claude LLM)
- Node.js 18+ and npm

## Setup

### 1. Install Wrangler CLI

```bash
npm install -g wrangler
```

### 2. Authenticate with Cloudflare

```bash
wrangler login
```

This opens a browser for OAuth authentication.

### 3. Install Dependencies

```bash
npm install
```

### 4. Configure Secrets

The worker requires 5 secrets to be configured:

```bash
# Anthropic API key (for generating social posts)
wrangler secret put ANTHROPIC_API_KEY

# Mailgun API key (from mailgun.com dashboard)
wrangler secret put MAILGUN_API_KEY

# Mailgun domain (e.g., mg.yourdomain.com or sandbox domain)
wrangler secret put MAILGUN_DOMAIN

# Email sender address (must be verified in Mailgun)
wrangler secret put EMAIL_FROM

# Your email address (where notifications are sent)
wrangler secret put EMAIL_TO
```

**Getting API Keys:**

- **Anthropic**: https://console.anthropic.com/settings/keys
- **Mailgun**: https://app.mailgun.com/app/account/security/api_keys

### 5. Deploy

```bash
wrangler deploy
```

The worker will be deployed to: `https://blog-notification-webhook.<your-subdomain>.workers.dev`

## Configuration

### Mailgun Setup

1. **Sign up**: https://mailgun.com (free tier available)
2. **Add domain** or use sandbox domain for testing
3. **Verify domain**: Add DNS records (SPF, DKIM, CNAME)
4. **Get API key**: Dashboard → Settings → API Keys
5. **Configure secrets** (see step 4 above)

**Note**: Sandbox domains can only send to authorized recipients. Add your email in Mailgun dashboard → Sending → Authorized Recipients.

### Customizing Prompts

Edit the prompt templates directly in `worker.js`:

- **LinkedIn prompt**: Lines 10-26 (professional tone, hashtags, CTAs)
- **Bluesky prompt**: Lines 28-43 (conversational tone, 300 char limit)

After editing, redeploy: `wrangler deploy`

## Testing

### Test Locally

```bash
wrangler dev
```

Then send a test request:

```bash
curl -X POST http://localhost:8787 \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Blog Post",
    "url": "https://example.com/test",
    "excerpt": "This is a test excerpt.",
    "tags": ["test"],
    "content": "Introduction: This is a comprehensive guide to testing webhooks...\n\nTable of Contents:\n- Getting Started\n- Best Practices\n- Common Issues\n\nFull article content here..."
  }'
```

### Test Production

```bash
curl -X POST https://blog-notification-webhook.<your-subdomain>.workers.dev \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Blog Post",
    "url": "https://example.com/test",
    "excerpt": "This is a test excerpt.",
    "tags": ["test"],
    "content": "Introduction: This is a comprehensive guide...\n\nFull article content..."
  }'
```

Expected response:
```json
{"success":true,"message":"Notification sent successfully"}
```

Check your email for the notification!

## Integration

### Ghost CMS Webhook (Required)

Configure Ghost to trigger the webhook whenever a post is published:

1. Go to Ghost Admin → Settings → Integrations
2. Add custom integration: "Blog Notification Webhook"
3. Add webhook:
   - **Event**: `Post published`
   - **Target URL**: Your worker URL
4. **Save**

**This webhook will trigger for ALL published posts**, whether published via:
- Python blog generator (`python main.py`)
- Ghost admin UI (manual publish)
- Ghost API (any other method)

Test by publishing a post via either method and checking your email.

## Payload Format

The worker accepts two payload formats:

### Custom Format

```json
{
  "title": "Blog Post Title",
  "url": "https://example.com/blog-post",
  "excerpt": "Post excerpt or summary",
  "tags": ["tag1", "tag2"],
  "content": "Full article content for better post generation..."
}
```

### Ghost CMS Format

```json
{
  "post": {
    "current": {
      "title": "Blog Post Title",
      "url": "https://example.com/blog-post",
      "excerpt": "Post excerpt",
      "tags": [{"name": "tag1"}, {"name": "tag2"}],
      "plaintext": "Full article content..."
    }
  }
}
```

**What the LLM receives:**
- Full article content (introduction, table of contents, all sections)
- The LLM reads the intro and TOC to understand main topics
- Generates posts highlighting specific insights and value propositions
- More accurate and compelling posts than using just excerpts

The worker automatically normalizes both formats.

## Error Handling

### LLM API Failure

If Anthropic API fails, the worker sends a fallback email with:
- Error message
- Blog post metadata
- Basic manual post template

### Mailgun API Failure

Returns HTTP 500 with error details:
- **401**: Invalid Mailgun API key
- **429**: Rate limit exceeded
- **5xx**: Mailgun service error

### Invalid Requests

- **405**: Non-POST requests
- **400**: Invalid JSON payload

## Monitoring

### View Logs

```bash
wrangler tail
```

Shows real-time logs from your worker.

### Cloudflare Dashboard

- **Workers & Pages** → Your worker → Metrics
- View request counts, errors, CPU time
- Free tier: 100,000 requests/day

### Mailgun Dashboard

- **Sending** → **Logs**
- Track email delivery, opens, clicks
- Debug delivery issues

## Troubleshooting

### Email not received

1. **Check Mailgun logs**: Dashboard → Sending → Logs
2. **Verify domain**: Make sure SPF/DKIM records are configured
3. **Check spam folder**: Emails might be filtered
4. **Sandbox domain**: Add recipient to authorized recipients list
5. **Test locally**: Run `wrangler dev` and check logs

### LLM errors

1. **Verify API key**: Check `ANTHROPIC_API_KEY` secret
2. **Check quota**: Ensure Anthropic account has credits
3. **View logs**: `wrangler tail` to see error details

### Deployment issues

1. **Authentication**: Run `wrangler login` again
2. **Secrets missing**: Ensure all 5 secrets are configured
3. **Syntax errors**: Check worker.js for JavaScript errors

### Worker not triggering

1. **Python config**: Verify `WEBHOOK_ENABLED=true` in `.env`
2. **URL correct**: Check `WEBHOOK_URL` matches deployed worker
3. **Ghost webhook**: Verify webhook is active in Ghost settings

## Development

### Project Structure

```
cloudflare-worker/
├── worker.js           # Main worker code
├── wrangler.toml       # Cloudflare configuration
├── package.json        # npm dependencies
├── .gitignore          # Ignore node_modules
└── README.md           # This file
```

### Local Development

```bash
# Install dependencies
npm install

# Run locally
wrangler dev

# Deploy to production
wrangler deploy

# View logs
wrangler tail
```

### Updating Secrets

```bash
# Update a single secret
wrangler secret put SECRET_NAME

# List all secrets (doesn't show values)
wrangler secret list

# Delete a secret
wrangler secret delete SECRET_NAME
```

## Auto-Deployment (GitHub Actions)

The `.github/workflows/deploy-worker.yml` workflow automatically deploys the worker when changes are pushed to the `cloudflare-worker/` directory.

**Setup:**

1. Create Cloudflare API token: https://dash.cloudflare.com/profile/api-tokens
2. Add to GitHub: Repository → Settings → Secrets → Actions
3. Secret name: `CLOUDFLARE_API_TOKEN`
4. Push changes to `main` branch → auto-deployment triggers

## Cost

### Free Tier Limits

- **Cloudflare Workers**: 100,000 requests/day
- **Mailgun**: 5,000 emails/month
- **Anthropic**: Pay per token (check pricing)

Typical usage for a blog:
- ~10-20 posts/month = well within free tiers
- Estimated cost: <$1/month

## Security

- **API keys**: Stored as encrypted Worker secrets (not in code)
- **No authentication**: Worker URL is public (anyone can POST)
  - Low risk: Only sends email to configured address
  - Can add signature verification if needed
- **Ghost webhook**: Optional signature verification available

## Support

- **Cloudflare Docs**: https://developers.cloudflare.com/workers/
- **Mailgun Docs**: https://documentation.mailgun.com/
- **Anthropic Docs**: https://docs.anthropic.com/

## License

MIT
