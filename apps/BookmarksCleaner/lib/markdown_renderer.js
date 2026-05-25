/**
 * Simple Markdown → HTML renderer.
 * Handles headings, bold, italic, code blocks, inline code, lists, links, images,
 * tables, blockquotes, horizontal rules.
 */

export function renderMarkdown(md) {
  if (!md) return '';

  let html = md;

  // Fenced code blocks (```lang\n...\n```)
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    const escaped = escapeHTML(code.trimEnd());
    return `<pre><code class="language-${lang || ''}">${escaped}</code></pre>`;
  });

  // Inline code (`...`)
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Headings (# ## ### ...)
  html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

  // Horizontal rules
  html = html.replace(/^(---|\*\*\*|___)\s*$/gm, '<hr>');

  // Bold and italic
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  html = html.replace(/___(.+?)___/g, '<strong><em>$1</em></strong>');
  html = html.replace(/__(.+?)__/g, '<strong>$1</strong>');
  html = html.replace(/_(.+?)_/g, '<em>$1</em>');

  // Images
  html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1">');

  // Links
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');

  // Blockquotes
  html = html.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');
  // Merge adjacent blockquotes
  html = html.replace(/<\/blockquote>\n<blockquote>/g, '\n');

  // Tables - simple pipe table support
  html = renderTables(html);

  // Ordered lists (process first, before unordered lists)
  html = renderLists(html, 'ol', /(?:^\d+\.\s+.+\n?)+/gm, /^\d+\.\s+/);
  // Unordered lists
  html = renderLists(html, 'ul', /(?:^[-*]\s+.+\n?)+/gm, /^[-*]\s+/);

  // Paragraphs: wrap remaining lines that aren't already wrapped in tags
  const lines = html.split('\n');
  const result = [];
  let inParagraph = false;

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      if (inParagraph) {
        result.push('</p>');
        inParagraph = false;
      }
      continue;
    }
    // Skip lines that are already HTML tags
    if (/^<(\/?(h[1-4]|p|ul|ol|li|pre|blockquote|hr|table|thead|tbody|tr|th|td)\b)/.test(trimmed)) {
      if (inParagraph) {
        result.push('</p>');
        inParagraph = false;
      }
      result.push(trimmed);
      continue;
    }
    if (!inParagraph) {
      result.push('<p>');
      inParagraph = true;
    } else {
      result.push('<br>');
    }
    result.push(trimmed);
  }

  if (inParagraph) {
    result.push('</p>');
  }

  return result.join('\n');
}

function renderTables(html) {
  // Match table blocks: header row, separator row, body rows
  return html.replace(/(\|[^\n]+\|\n\|[\-\s|:]+\|\n(?:\|[^\n]+\|\n?)*)/g, (block) => {
    const rows = block.trim().split('\n');
    if (rows.length < 2) return block;

    // Skip separator row
    const headerCells = parseTableRow(rows[0]);
    let table = '<table><thead><tr>';
    for (const cell of headerCells) {
      table += `<th>${cell}</th>`;
    }
    table += '</tr></thead><tbody>';

    for (let i = 2; i < rows.length; i++) {
      const cells = parseTableRow(rows[i]);
      table += '<tr>';
      for (const cell of cells) {
        table += `<td>${cell}</td>`;
      }
      table += '</tr>';
    }

    table += '</tbody></table>';
    return table;
  });
}

function parseTableRow(row) {
  return row.split('|')
    .map(c => c.trim())
    .filter(c => c.length > 0)
    .map(c => c.replace(/<\/?[^>]+>/g, '')); // remove any existing tags for safety
}

function renderLists(html, tag, outerPattern, prefixPattern) {
  return html.replace(outerPattern, (block) => {
    const items = block.trim().split('\n').filter(l => l.trim());
    let list = `<${tag}>`;
    for (const item of items) {
      list += `<li>${item.replace(prefixPattern, '').trim()}</li>`;
    }
    list += `</${tag}>`;
    return list;
  });
}

function escapeHTML(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
