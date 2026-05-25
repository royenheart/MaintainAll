/**
 * WebDAV client for syncing knowledge base backups.
 * Supports PUT (upload), GET (download), PROPFIND (list), DELETE.
 */

export class WebDAVClient {
  constructor(url, username, password) {
    this.baseUrl = url.endsWith('/') ? url : url + '/';
    this.username = username;
    this.password = password;

    // Warn if not HTTPS (Basic Auth sends credentials in cleartext)
    if (this.baseUrl.startsWith('http://')) {
      console.warn('[BookmarksCleaner] WebDAV over HTTP — credentials will be sent in cleartext. Use HTTPS.');
    }
  }

  /** Returns true if the URL uses HTTPS. */
  get isSecure() {
    return this.baseUrl.startsWith('https://');
  }

  get authHeader() {
    return 'Basic ' + btoa(`${this.username}:${this.password}`);
  }

  get headers() {
    return {
      'Authorization': this.authHeader,
      'Content-Type': 'application/octet-stream'
    };
  }

  /**
   * Upload a file to WebDAV.
   * @param {string} remotePath - relative path on server (e.g. 'knowledge_base.md')
   * @param {string|Blob} content - file content
   * @returns {Promise<boolean>}
   */
  async put(remotePath, content) {
    const url = this.baseUrl + remotePath.replace(/^\//, '');
    const response = await fetch(url, {
      method: 'PUT',
      headers: this.headers,
      body: content
    });
    return response.ok;
  }

  /**
   * Create a WebDAV directory. Returns true if created or already exists.
   * @param {string} remoteDir
   * @returns {Promise<boolean>}
   */
  async mkcol(remoteDir) {
    const clean = remoteDir.replace(/^\/|\/$/g, '');
    if (!clean) return true;
    const url = this.baseUrl + clean + '/';
    const response = await fetch(url, {
      method: 'MKCOL',
      headers: { 'Authorization': this.authHeader }
    });
    return response.ok || response.status === 405;
  }

  /**
   * Ensure a nested directory exists.
   * @param {string} remoteDir
   * @returns {Promise<boolean>}
   */
  async ensureDirectory(remoteDir) {
    const parts = remoteDir.split('/').map(p => p.trim()).filter(Boolean);
    let current = '';
    for (const part of parts) {
      current = current ? `${current}/${part}` : part;
      const ok = await this.mkcol(current);
      if (!ok) return false;
    }
    return true;
  }

  /**
   * Download a file from WebDAV.
   * @param {string} remotePath
   * @returns {Promise<string|null>}
   */
  async get(remotePath) {
    const url = this.baseUrl + remotePath.replace(/^\//, '');
    const response = await fetch(url, {
      method: 'GET',
      headers: { 'Authorization': this.authHeader }
    });
    if (!response.ok) return null;
    return response.text();
  }

  /**
   * List files in a directory (PROPFIND with Depth: 1).
   * @param {string} remoteDir
   * @returns {Promise<Array<{href: string, size: number, lastModified: string}>>}
   */
  async list(remoteDir = '') {
    const url = this.baseUrl + remoteDir.replace(/^\//, '');
    // Simple PROPFIND body for file listing
    const body = `<?xml version="1.0"?>
<d:propfind xmlns:d="DAV:">
  <d:prop>
    <d:getcontentlength/>
    <d:getlastmodified/>
    <d:displayname/>
  </d:prop>
</d:propfind>`;

    const response = await fetch(url, {
      method: 'PROPFIND',
      headers: {
        'Authorization': this.authHeader,
        'Content-Type': 'application/xml',
        'Depth': '1'
      },
      body
    });

    if (!response.ok) return [];

    const xml = await response.text();
    return parsePropfind(xml);
  }

  /**
   * Delete a file.
   * @param {string} remotePath
   * @returns {Promise<boolean>}
   */
  async delete(remotePath) {
    const url = this.baseUrl + remotePath.replace(/^\//, '');
    const response = await fetch(url, {
      method: 'DELETE',
      headers: { 'Authorization': this.authHeader }
    });
    return response.ok;
  }

  /**
   * Test connection.
   * @returns {Promise<{ok: boolean, error?: string}>}
   */
  async testConnection() {
    try {
      // PROPFIND with Depth:0 probes server without triggering CORS preflight issues
      const body = `<?xml version="1.0"?>
<d:propfind xmlns:d="DAV:">
  <d:prop><d:displayname/></d:prop>
</d:propfind>`;
      const response = await fetch(this.baseUrl, {
        method: 'PROPFIND',
        headers: {
          'Authorization': this.authHeader,
          'Depth': '0'
        },
        body
      });
      return { ok: response.ok, error: response.ok ? null : `HTTP ${response.status}` };
    } catch (err) {
      return { ok: false, error: err.message };
    }
  }

  /**
   * Sync knowledge base: upload current KB, download any newer version.
   * Simple strategy: upload always, no conflict resolution.
   * @param {string} kbMarkdown - current KB content
   * @returns {Promise<{uploaded: boolean, downloaded: string|null}>}
   */
  async syncKnowledgeBase(kbMarkdown) {
    const filename = 'knowledge_base.md';
    const uploaded = await this.put(filename, kbMarkdown);
    return { uploaded, downloaded: null };
  }
}

/**
 * Parse PROPFIND XML response into a simple list.
 */
function parsePropfind(xml) {
  const items = [];
  const responses = xml.split('<d:response>');
  for (const resp of responses.slice(1)) {
    const href = extractXML(resp, 'd:href') || extractXML(resp, 'D:href');
    const size = extractXML(resp, 'd:getcontentlength') || extractXML(resp, 'D:getcontentlength');
    const modified = extractXML(resp, 'd:getlastmodified') || extractXML(resp, 'D:getlastmodified');
    if (href && href !== '/') {
      items.push({
        href: href.trim(),
        size: parseInt(size) || 0,
        lastModified: modified?.trim() || ''
      });
    }
  }
  return items;
}

function extractXML(xml, tag) {
  const match = xml.match(new RegExp(`<${tag}[^>]*>([^<]*)</${tag}>`, 'i'));
  return match ? match[1] : null;
}
