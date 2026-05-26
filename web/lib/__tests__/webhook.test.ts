import { normalizePayload, generateShortUrls } from '../webhook';

describe('normalizePayload', () => {
  it('extracts fields from Ghost CMS format', () => {
    const payload = {
      post: {
        current: {
          title: 'Test Post',
          url: 'https://blog.com/test-post',
          excerpt: 'A test excerpt',
          tags: [{ name: 'AI' }, { name: 'LangChain' }],
          plaintext: 'Full article content here',
        },
      },
    };
    const result = normalizePayload(payload);
    expect(result.title).toBe('Test Post');
    expect(result.url).toBe('https://blog.com/test-post');
    expect(result.excerpt).toBe('A test excerpt');
    expect(result.tags).toEqual(['AI', 'LangChain']);
    expect(result.content).toBe('Full article content here');
  });

  it('extracts fields from custom flat format', () => {
    const payload = {
      title: 'Flat Post',
      url: 'https://blog.com/flat-post',
      excerpt: 'Flat excerpt',
      tags: ['tag1', 'tag2'],
      content: 'Flat content',
    };
    const result = normalizePayload(payload);
    expect(result.title).toBe('Flat Post');
    expect(result.tags).toEqual(['tag1', 'tag2']);
  });

  it('handles missing fields gracefully', () => {
    const result = normalizePayload({});
    expect(result.title).toBe('');
    expect(result.tags).toEqual([]);
    expect(result.content).toBe('');
  });
});

describe('generateShortUrls', () => {
  it('falls back to UTM long URLs when TinyURL fails', async () => {
    // Mock fetch to simulate TinyURL failure
    global.fetch = jest.fn().mockRejectedValue(new Error('Network error'));
    const urls = await generateShortUrls('https://blog.com/my-post', 'fake-token');
    expect(urls.linkedin).toContain('utm_source=linkedin');
    expect(urls.bluesky).toContain('utm_source=bluesky');
    expect(urls.linkedin).toContain('https://blog.com/my-post');
  });
});
