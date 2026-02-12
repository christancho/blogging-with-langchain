/**
 * Cloudflare Worker for Blog Post Notification Webhook
 * Receives publication events, generates social media posts, and sends email notifications
 */

// Prompt templates for social media post generation
// Edit these directly to customize LinkedIn and Bluesky post formats
const LINKEDIN_PROMPT = `You are a professional LinkedIn content creator. Create a compelling LinkedIn post to promote a new blog article.

Blog Title: {title}
Blog URL: {url}
Excerpt: {excerpt}
Tags: {tags}

Guidelines:
- Professional and insightful tone
- Highlight key takeaways or value proposition
- Include relevant hashtags (3-5 max)
- Add a call-to-action to read the full article
- Keep it under 3000 characters
- Make it engaging and thought-provoking
- Include the blog URL

Format the post as if you're posting directly to LinkedIn. Make it compelling enough that professionals will want to click through and read the full article.`;

const BLUESKY_PROMPT = `You are a social media expert creating engaging Bluesky posts. Create a conversational post to promote a new blog article.

Blog Title: {title}
Blog URL: {url}
Excerpt: {excerpt}
Tags: {tags}

Guidelines:
- Conversational and approachable tone
- Must be under 300 characters (Bluesky's limit)
- Include the blog URL
- Make it catchy and shareable
- Focus on the main hook or insight
- No hashtags (Bluesky doesn't use them the same way)

Format the post as if you're posting directly to Bluesky. Keep it brief, engaging, and make people want to click through to read more.`;

/**
 * Main Worker fetch handler
 */
export default {
	async fetch(request, env) {
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

			// Generate social media posts
			let posts;
			let postGenerationError = null;
			try {
				posts = await generateSocialPosts(metadata, env);
			} catch (e) {
				console.error('Post generation failed:', e);
				postGenerationError = e.message;
				// Continue to send email with error message
			}

			// Send email notification
			try {
				await sendEmailNotification(metadata, posts, postGenerationError, env);
			} catch (e) {
				console.error('Email notification failed:', e);
				return new Response(JSON.stringify({
					error: 'Email delivery failed',
					message: e.message
				}), {
					status: 500,
					headers: { 'Content-Type': 'application/json' }
				});
			}

			// Success
			return new Response(JSON.stringify({
				success: true,
				message: 'Notification sent successfully'
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
			content_preview: post.plaintext ? post.plaintext.substring(0, 500) : ''
		};
	}

	// Custom publisher format
	return {
		title: payload.title || '',
		url: payload.url || '',
		excerpt: payload.excerpt || '',
		tags: Array.isArray(payload.tags) ? payload.tags : [],
		content_preview: payload.content_preview || ''
	};
}

/**
 * Generate social media posts using Anthropic Claude API
 */
async function generateSocialPosts(metadata, env) {
	const { title, url, excerpt, tags } = metadata;

	// Prepare prompt context
	const tagsStr = Array.isArray(tags) ? tags.join(', ') : '';

	// Generate LinkedIn post
	const linkedinPrompt = LINKEDIN_PROMPT
		.replace('{title}', title)
		.replace('{url}', url)
		.replace('{excerpt}', excerpt)
		.replace('{tags}', tagsStr);

	const linkedinPost = await callAnthropicAPI(linkedinPrompt, env);

	// Verify LinkedIn character limit
	if (linkedinPost.length > 3000) {
		console.warn('LinkedIn post exceeds 3000 characters, truncating...');
	}

	// Generate Bluesky post
	const blueskyPrompt = BLUESKY_PROMPT
		.replace('{title}', title)
		.replace('{url}', url)
		.replace('{excerpt}', excerpt)
		.replace('{tags}', tagsStr);

	const blueskyPost = await callAnthropicAPI(blueskyPrompt, env);

	// Verify Bluesky character limit
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
				model: 'claude-3-5-sonnet-20241022',
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
