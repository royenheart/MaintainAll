import { describe, test, expect, jest } from '@jest/globals';

let WebDAVClient;

beforeAll(async () => {
  const mod = await import('../../lib/webdav.js');
  ({ WebDAVClient } = mod);
});

describe('WebDAVClient', () => {
  let client;

  beforeEach(() => {
    client = new WebDAVClient('https://dav.example.com/', 'user', 'pass');
  });

  test('normalizes URL without trailing slash', () => {
    const c = new WebDAVClient('https://dav.example.com', 'user', 'pass');
    // baseUrl is private (this.baseUrl), test via a mock request
  });

  test('constructs Basic Auth header correctly', () => {
    const header = client.authHeader;
    expect(header).toMatch(/^Basic /);
    // Base64 of 'user:pass' = 'dXNlcjpwYXNz'
    expect(header).toBe('Basic dXNlcjpwYXNz');
  });

  test('detects insecure HTTP URL', () => {
    const warn = jest.spyOn(console, 'warn').mockImplementation(() => {});
    const c = new WebDAVClient('http://dav.example.com', 'user', 'pass');
    expect(c.isSecure).toBe(false);
    expect(warn).toHaveBeenCalledWith(
      expect.stringContaining('HTTP')
    );
    warn.mockRestore();
  });

  test('detects secure HTTPS URL', () => {
    expect(client.isSecure).toBe(true);
  });

  test('headers include Authorization', () => {
    const headers = client.headers;
    expect(headers['Authorization']).toBe('Basic dXNlcjpwYXNz');
    expect(headers['Content-Type']).toBe('application/octet-stream');
  });

  describe('put', () => {
    test('sends PUT request with correct headers', async () => {
      global.fetch = jest.fn().mockResolvedValue({ ok: true });
      const result = await client.put('file.txt', 'content');
      expect(result).toBe(true);
      expect(fetch).toHaveBeenCalledWith(
        'https://dav.example.com/file.txt',
        expect.objectContaining({
          method: 'PUT',
          headers: expect.objectContaining({
            'Authorization': 'Basic dXNlcjpwYXNz',
          }),
          body: 'content',
        })
      );
    });

    test('returns false on failure', async () => {
      global.fetch = jest.fn().mockResolvedValue({ ok: false });
      const result = await client.put('file.txt', 'data');
      expect(result).toBe(false);
    });
  });

  describe('mkcol / ensureDirectory', () => {
    test('creates nested directories with MKCOL', async () => {
      global.fetch = jest.fn().mockResolvedValue({ ok: true, status: 201 });
      const ok = await client.ensureDirectory('BookmarksCleaner/nested');
      expect(ok).toBe(true);
      expect(fetch).toHaveBeenNthCalledWith(
        1,
        'https://dav.example.com/BookmarksCleaner/',
        expect.objectContaining({ method: 'MKCOL' })
      );
      expect(fetch).toHaveBeenNthCalledWith(
        2,
        'https://dav.example.com/BookmarksCleaner/nested/',
        expect.objectContaining({ method: 'MKCOL' })
      );
    });

    test('treats existing directory as success', async () => {
      global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 405 });
      await expect(client.mkcol('BookmarksCleaner')).resolves.toBe(true);
    });
  });

  describe('get', () => {
    test('returns text on success', async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        text: () => Promise.resolve('file content'),
      });
      const result = await client.get('file.txt');
      expect(result).toBe('file content');
    });

    test('returns null on 404', async () => {
      global.fetch = jest.fn().mockResolvedValue({ ok: false });
      const result = await client.get('nonexistent.txt');
      expect(result).toBeNull();
    });
  });

  describe('delete', () => {
    test('sends DELETE request', async () => {
      global.fetch = jest.fn().mockResolvedValue({ ok: true });
      const result = await client.delete('file.txt');
      expect(result).toBe(true);
      expect(fetch).toHaveBeenCalledWith(
        'https://dav.example.com/file.txt',
        expect.objectContaining({ method: 'DELETE' })
      );
    });
  });

  describe('testConnection', () => {
    test('returns ok on success', async () => {
      global.fetch = jest.fn().mockResolvedValue({ ok: true });
      const result = await client.testConnection();
      expect(result).toEqual({ ok: true, error: null });
      expect(fetch).toHaveBeenCalledWith(
        'https://dav.example.com/',
        expect.objectContaining({ method: 'PROPFIND' })
      );
    });

    test('returns error on network failure', async () => {
      global.fetch = jest.fn().mockRejectedValue(new Error('Network error'));
      const result = await client.testConnection();
      expect(result.ok).toBe(false);
      expect(result.error).toContain('Network error');
    });
  });
});
