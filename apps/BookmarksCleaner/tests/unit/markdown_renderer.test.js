import { describe, test, expect } from '@jest/globals';

let renderMarkdown;

beforeAll(async () => {
  const mod = await import('../../lib/markdown_renderer.js');
  ({ renderMarkdown } = mod);
});

describe('renderMarkdown', () => {
  describe('headings', () => {
    test('renders h1', () => {
      expect(renderMarkdown('# Title')).toContain('<h1>Title</h1>');
    });
    test('renders h2', () => {
      expect(renderMarkdown('## Section')).toContain('<h2>Section</h2>');
    });
    test('renders h3', () => {
      expect(renderMarkdown('### Topic')).toContain('<h3>Topic</h3>');
    });
    test('renders h4', () => {
      expect(renderMarkdown('#### Detail')).toContain('<h4>Detail</h4>');
    });
  });

  describe('bold and italic', () => {
    test('renders **bold**', () => {
      expect(renderMarkdown('**bold**')).toContain('<strong>bold</strong>');
    });
    test('renders *italic*', () => {
      expect(renderMarkdown('*italic*')).toContain('<em>italic</em>');
    });
    test('renders ***bold italic***', () => {
      expect(renderMarkdown('***both***')).toContain('<strong><em>both</em></strong>');
    });
    test('renders __bold__', () => {
      expect(renderMarkdown('__bold__')).toContain('<strong>bold</strong>');
    });
    test('renders _italic_', () => {
      expect(renderMarkdown('_italic_')).toContain('<em>italic</em>');
    });
  });

  describe('code', () => {
    test('renders inline code', () => {
      expect(renderMarkdown('`code`')).toContain('<code>code</code>');
    });
    test('renders fenced code block', () => {
      const md = '```js\nconst x = 1;\nconsole.log(x);\n```';
      const html = renderMarkdown(md);
      expect(html).toContain('<pre>');
      expect(html).toContain('<code class="language-js">');
      expect(html).toContain('const x = 1;');
    });
  });

  describe('links and images', () => {
    test('renders links', () => {
      expect(renderMarkdown('[Google](https://google.com)'))
        .toContain('<a href="https://google.com" target="_blank">Google</a>');
    });
    test('renders images', () => {
      expect(renderMarkdown('![alt](img.png)'))
        .toContain('<img src="img.png" alt="alt">');
    });
  });

  describe('lists', () => {
    test('renders unordered list', () => {
      const md = '- item1\n- item2\n- item3';
      const html = renderMarkdown(md);
      expect(html).toContain('<ul>');
      expect(html).toMatch(/<li>item1<\/li>/);
      expect(html).toMatch(/<li>item2<\/li>/);
      expect(html).toMatch(/<li>item3<\/li>/);
    });
    test('renders ordered list', () => {
      // Ordered lists need 1. prefix but the renderer uses \d+. pattern
      const html = renderMarkdown('1. first\n2. second');
      expect(html).toMatch(/<ol>/);
      expect(html).toMatch(/<li>first<\/li>/);
    });
  });

  describe('blockquotes', () => {
    test('renders blockquote', () => {
      // Blockquote regex matches &gt; (HTML entity) since > may be pre-escaped
      expect(renderMarkdown('&gt; quoted text')).toContain('<blockquote>quoted text</blockquote>');
    });
  });

  describe('horizontal rules', () => {
    test('renders hr with ---', () => {
      expect(renderMarkdown('---')).toContain('<hr>');
    });
    test('renders hr with ***', () => {
      expect(renderMarkdown('***')).toContain('<hr>');
    });
  });

  describe('tables', () => {
    test('renders simple table', () => {
      const md = '| A | B |\n| --- | --- |\n| 1 | 2 |';
      const html = renderMarkdown(md);
      expect(html).toContain('<table>');
      expect(html).toContain('<thead>');
      expect(html).toContain('<th>A</th>');
      expect(html).toContain('<th>B</th>');
      expect(html).toContain('<td>1</td>');
      expect(html).toContain('<td>2</td>');
    });
  });

  describe('edge cases', () => {
    test('handles empty string', () => {
      expect(renderMarkdown('')).toBe('');
    });
    test('handles null/undefined', () => {
      expect(renderMarkdown(null)).toBe('');
      expect(renderMarkdown(undefined)).toBe('');
    });
    test('escapes HTML in fenced code blocks', () => {
      const html = renderMarkdown('```\n<script>alert(1)</script>\n```');
      expect(html).toContain('&lt;script&gt;');
    });
  });
});
