/**
 * Cloudflare Worker for Blog Post Notification Webhook
 * Receives publication events, generates social media posts, and sends email notifications
 */

// Prompt templates for social media post generation
// Edit these directly to customize LinkedIn and Bluesky post formats
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

**Structure (follow this exact format):**
1. Open with "🎯 The Problem with [topic]" or a compelling problem statement hook
2. One short paragraph establishing why this matters right now
3. "I just published [brief description of what the article covers]"
4. "What makes this approach powerful:" followed by 4-5 checkmark bullets (✅) with concrete benefits
5. One paragraph expanding on the core value proposition
6. "Perfect for:" followed by 5-6 bullet points (•) of specific use cases or industries
7. Call to action: "Full [guide/breakdown/tutorial] with [code examples/case studies/frameworks] in the article 👇"
8. The blog URL with UTM parameters: {url}?utm_source=linkedin&utm_medium=social&utm_campaign=[slug_from_url]
9. Engagement question: "What's your experience with [topic]? [Specific question related to article]"
10. 8-10 relevant hashtags from the provided tags plus standard ones like #ArtificialIntelligence #AIEngineering #EnterpriseAI

**Tone and Style:**
- Professional but conversational
- Authoritative without being academic
- Direct and confident - avoid weak language like "maybe" or "might"
- Speak to enterprise practitioners and technical leads
- Focus on production/real-world applicability, not theory

**Content Rules:**
- Never invent features, examples, or claims not present in the article
- Extract specific technical details directly from the article content
- Use concrete numbers when available (lines of code, performance metrics, etc.)
- The checkmark bullets must reflect actual article content
- Use cases must be realistic for the technology discussed

**Length:** 
- Aim for 1,200-1,500 characters (optimal LinkedIn engagement range)
- Long enough to add value, short enough to avoid truncation before "see more"

Output the LinkedIn post only, no explanations or commentary.`;

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

**Structure (follow this exact format):**
1. Open with a relevant emoji + one punchy provocative statement or question (max 10 words)
2. One blank line
3. 2-3 lines expanding on the problem or insight (concise, no fluff)
4. One blank line
5. "Just published:" followed by one sentence describing what the article covers
6. One blank line
7. 3-4 bullet points using → arrows listing the concrete topics/examples covered in the article
8. One blank line
9. One closing sentence reinforcing the value (why they should care)
10. One blank line
11. The blog URL with UTM parameters: {url}?utm_source=bluesky&utm_medium=social&utm_campaign=[slug_from_url]
12. One blank line
13. 3-5 hashtags (no spaces, concise, relevant to the article tags provided)

**Tone and Style:**
- Punchy and direct - every word must earn its place
- Conversational but technically credible
- Avoid corporate speak or buzzwords
- Write for AI practitioners, developers, and tech-forward professionals
- Slightly more informal than LinkedIn but still professional

**Content Rules:**
- Never invent features, examples, or claims not present in the article
- Extract specific technical details directly from the article content
- The → bullets must reflect actual article content, not generic claims
- Keep it grounded in production/real-world applicability

**Length:**
- Hard limit: 300 characters per post (Bluesky limit)
- If content exceeds 300 characters, format as a thread:
  - Label each post as 1/3, 2/3, 3/3 etc.
  - Each post must be self-contained and under 300 characters
  - Thread should flow naturally from one post to the next

**Character Count Check:**
- Before outputting, verify each post is under 300 characters
- Count carefully including spaces, emojis (=2 chars), and URLs (=24 chars)

Output the Bluesky post or thread only, no explanations or commentary.`;

/**
 * Main Worker fetch handler
 */
export default {
	async fetch(request, env, ctx) {
		// Only accept POST requests
		if (request.method !== 'POST') {
			return new Response('Method not allowed. Please use POST.', {
				status: 405,
				headers: { 'Allow': 'POST' }
			});
		}

		try {
			// Parse JSON payload
			let payload;
			try {
				payload = await request.json();
			} catch (e) {
				return new Response(JSON.stringify({
					error: 'Invalid JSON payload',
					message: e.message
				}), {
					status: 400,
					headers: { 'Content-Type': 'application/json' }
				});
			}

			// Normalize payload (handle Ghost CMS vs custom format)
			const metadata = normalizePayload(payload);

			// Queue background processing (non-blocking)
			ctx.waitUntil(processNotification(metadata, env));

			// Respond immediately to Ghost webhook
			return new Response(JSON.stringify({
				success: true,
				message: 'Notification queued for processing'
			}), {
				status: 200,
				headers: { 'Content-Type': 'application/json' }
			});

		} catch (e) {
			console.error('Unexpected error:', e);
			return new Response(JSON.stringify({
				error: 'Internal server error',
				message: e.message
			}), {
				status: 500,
				headers: { 'Content-Type': 'application/json' }
			});
		}
	},
};

/**
 * Normalize payload from different sources (Ghost CMS vs custom)
 */
function normalizePayload(payload) {
	// Check if it's a Ghost CMS webhook format
	if (payload.post && payload.post.current) {
		const post = payload.post.current;
		return {
			title: post.title || '',
			url: post.url || '',
			excerpt: post.excerpt || post.custom_excerpt || '',
			tags: post.tags ? post.tags.map(t => t.name) : [],
			content: post.plaintext || ''  // Full content for better context
		};
	}

	// Custom publisher format
	return {
		title: payload.title || '',
		url: payload.url || '',
		excerpt: payload.excerpt || '',
		tags: Array.isArray(payload.tags) ? payload.tags : [],
		content: payload.content || payload.content_preview || ''
	};
}

/**
 * Process notification in background (non-blocking)
 */
async function processNotification(metadata, env) {
	console.log('Starting background notification processing:', metadata.title);

	// Generate social media posts
	let posts;
	let postGenerationError = null;
	try {
		posts = await generateSocialPosts(metadata, env);
		console.log('Social posts generated successfully');
	} catch (e) {
		console.error('Post generation failed:', e);
		postGenerationError = e.message;
		// Continue to send email with error message
	}

	// Send email notification
	try {
		await sendEmailNotification(metadata, posts, postGenerationError, env);
		console.log('Email notification sent successfully');
	} catch (e) {
		console.error('Email notification failed:', e);
		// Log but don't fail - webhook already responded 200
	}

	console.log('Background processing complete for:', metadata.title);
}

/**
 * Generate social media posts using Anthropic Claude API
 */
async function generateSocialPosts(metadata, env) {
	const { title, url, excerpt, tags, content } = metadata;

	// Prepare prompt context
	const tagsStr = Array.isArray(tags) ? tags.join(', ') : '';

	// Use first 2500 chars for faster processing (intro + TOC + first sections)
	const contentSummary = content.substring(0, 2500);

	// Prepare both prompts
	const linkedinPrompt = LINKEDIN_PROMPT
		.replace('{title}', title)
		.replace('{url}', url)
		.replace('{excerpt}', excerpt)
		.replace('{tags}', tagsStr)
		.replace('{content}', contentSummary);

	const blueskyPrompt = BLUESKY_PROMPT
		.replace('{title}', title)
		.replace('{url}', url)
		.replace('{excerpt}', excerpt)
		.replace('{tags}', tagsStr)
		.replace('{content}', contentSummary);

	// Call both APIs in parallel for speed
	const [linkedinPost, blueskyPost] = await Promise.all([
		callAnthropicAPI(linkedinPrompt, env),
		callAnthropicAPI(blueskyPrompt, env)
	]);

	// Verify character limits
	if (linkedinPost.length > 3000) {
		console.warn('LinkedIn post exceeds 3000 characters, truncating...');
	}
	if (blueskyPost.length > 300) {
		console.warn('Bluesky post exceeds 300 characters, truncating...');
	}

	return {
		linkedin: linkedinPost.substring(0, 3000),
		bluesky: blueskyPost.substring(0, 300)
	};
}

/**
 * Call Anthropic Claude API
 */
async function callAnthropicAPI(prompt, env) {
	const apiKey = env.ANTHROPIC_API_KEY;
	if (!apiKey) {
		throw new Error('ANTHROPIC_API_KEY not configured in Worker secrets');
	}

	const controller = new AbortController();
	const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 second timeout

	try {
		const response = await fetch('https://api.anthropic.com/v1/messages', {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'x-api-key': apiKey,
				'anthropic-version': '2023-06-01'
			},
			body: JSON.stringify({
				model: 'claude-sonnet-4-5-20250929',
				max_tokens: 1024,
				messages: [
					{ role: 'user', content: prompt }
				]
			}),
			signal: controller.signal
		});

		clearTimeout(timeoutId);

		if (!response.ok) {
			const errorText = await response.text();
			throw new Error(`Anthropic API error (${response.status}): ${errorText}`);
		}

		const data = await response.json();
		return data.content[0].text;

	} catch (e) {
		clearTimeout(timeoutId);
		if (e.name === 'AbortError') {
			throw new Error('Anthropic API request timed out after 30 seconds');
		}
		throw e;
	}
}

/**
 * Send email notification via Mailgun
 */
async function sendEmailNotification(metadata, posts, errorMessage, env) {
	const { MAILGUN_API_KEY, MAILGUN_DOMAIN, EMAIL_FROM, EMAIL_TO } = env;

	// Validate configuration
	if (!MAILGUN_API_KEY) throw new Error('MAILGUN_API_KEY not configured');
	if (!MAILGUN_DOMAIN) throw new Error('MAILGUN_DOMAIN not configured');
	if (!EMAIL_FROM) throw new Error('EMAIL_FROM not configured');
	if (!EMAIL_TO) throw new Error('EMAIL_TO not configured');

	const { title, url, excerpt, tags } = metadata;
	const tagsStr = Array.isArray(tags) ? tags.join(', ') : '';

	// Generate HTML email
	const htmlBody = generateHTMLEmail(title, url, excerpt, tagsStr, posts, errorMessage);

	// Generate plain text fallback
	const textBody = generatePlainTextEmail(title, url, excerpt, tagsStr, posts, errorMessage);

	// Prepare form data for Mailgun
	const formData = new FormData();
	formData.append('from', EMAIL_FROM);
	formData.append('to', EMAIL_TO);
	formData.append('subject', `New Blog Post: ${title} - Social Media Content Ready`);
	formData.append('html', htmlBody);
	formData.append('text', textBody);

	// Send via Mailgun API
	const mailgunEndpoint = `https://api.mailgun.net/v3/${MAILGUN_DOMAIN}/messages`;
	const basicAuth = btoa(`api:${MAILGUN_API_KEY}`);

	const response = await fetch(mailgunEndpoint, {
		method: 'POST',
		headers: {
			'Authorization': `Basic ${basicAuth}`
		},
		body: formData
	});

	if (!response.ok) {
		const errorText = await response.text();

		// Handle specific Mailgun errors
		if (response.status === 401) {
			throw new Error('Mailgun authentication failed. Check MAILGUN_API_KEY.');
		} else if (response.status === 429) {
			throw new Error('Mailgun rate limit exceeded. Try again later.');
		} else {
			throw new Error(`Mailgun API error (${response.status}): ${errorText}`);
		}
	}

	return await response.json();
}

/**
 * Generate HTML email template
 */
function generateHTMLEmail(title, url, excerpt, tags, posts, errorMessage) {
	if (errorMessage) {
		// Error fallback email
		return `
<!DOCTYPE html>
<html>
<head>
	<meta charset="UTF-8">
	<style>
		body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }
		h1 { color: #2563eb; }
		h2 { color: #1e40af; margin-top: 30px; }
		.error { background-color: #fee2e2; border-left: 4px solid #dc2626; padding: 15px; margin: 20px 0; }
		.metadata { background-color: #f3f4f6; padding: 15px; border-radius: 5px; margin: 20px 0; }
		.post-box { background-color: #f9fafb; border: 1px solid #e5e7eb; padding: 15px; border-radius: 5px; margin: 15px 0; font-family: monospace; white-space: pre-wrap; }
		a { color: #2563eb; }
	</style>
</head>
<body>
	<h1>🚨 New Blog Post Published (Error Generating Posts)</h1>

	<div class="error">
		<strong>Error:</strong> Social media post generation failed.<br>
		<strong>Message:</strong> ${escapeHTML(errorMessage)}
	</div>

	<div class="metadata">
		<h2>Blog Post Details</h2>
		<p><strong>Title:</strong> ${escapeHTML(title)}</p>
		<p><strong>URL:</strong> <a href="${url}">${url}</a></p>
		<p><strong>Excerpt:</strong> ${escapeHTML(excerpt)}</p>
		<p><strong>Tags:</strong> ${escapeHTML(tags)}</p>
	</div>

	<h2>Manual Post Suggestion</h2>
	<p>Since automatic generation failed, here's a basic template you can customize:</p>

	<div class="post-box">
Just published: ${escapeHTML(title)}

${url}

${escapeHTML(excerpt)}
	</div>
</body>
</html>
`;
	}

	// Normal email with generated posts
	return `
<!DOCTYPE html>
<html>
<head>
	<meta charset="UTF-8">
	<style>
		body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }
		h1 { color: #2563eb; }
		h2 { color: #1e40af; margin-top: 30px; }
		.metadata { background-color: #f3f4f6; padding: 15px; border-radius: 5px; margin: 20px 0; }
		.post-box { background-color: #f9fafb; border: 1px solid #e5e7eb; padding: 15px; border-radius: 5px; margin: 15px 0; font-family: monospace; white-space: pre-wrap; }
		a { color: #2563eb; }
		.copy-hint { font-size: 12px; color: #6b7280; margin-top: 5px; }
	</style>
</head>
<body>
	<h1>✅ New Blog Post Published!</h1>

	<div class="metadata">
		<h2>Blog Post Details</h2>
		<p><strong>Title:</strong> ${escapeHTML(title)}</p>
		<p><strong>URL:</strong> <a href="${url}">${url}</a></p>
		<p><strong>Excerpt:</strong> ${escapeHTML(excerpt)}</p>
		<p><strong>Tags:</strong> ${escapeHTML(tags)}</p>
	</div>

	<h2>📘 LinkedIn Post</h2>
	<div class="post-box">${escapeHTML(posts.linkedin)}</div>
	<p class="copy-hint">Copy and paste this into LinkedIn</p>

	<h2>🦋 Bluesky Post</h2>
	<div class="post-box">${escapeHTML(posts.bluesky)}</div>
	<p class="copy-hint">Copy and paste this into Bluesky</p>
</body>
</html>
`;
}

/**
 * Generate plain text email
 */
function generatePlainTextEmail(title, url, excerpt, tags, posts, errorMessage) {
	if (errorMessage) {
		return `
NEW BLOG POST PUBLISHED (ERROR GENERATING POSTS)
================================================

ERROR: ${errorMessage}

BLOG POST DETAILS
-----------------
Title: ${title}
URL: ${url}
Excerpt: ${excerpt}
Tags: ${tags}

MANUAL POST SUGGESTION
----------------------
Just published: ${title}

${url}

${excerpt}
`;
	}

	return `
NEW BLOG POST PUBLISHED
=======================

BLOG POST DETAILS
-----------------
Title: ${title}
URL: ${url}
Excerpt: ${excerpt}
Tags: ${tags}

LINKEDIN POST
-------------
${posts.linkedin}

BLUESKY POST
------------
${posts.bluesky}
`;
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHTML(str) {
	if (!str) return '';
	return String(str)
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;')
		.replace(/'/g, '&#039;');
}
