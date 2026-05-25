import { describe, test, expect, jest, afterEach } from '@jest/globals';
import { TextDecoder, TextEncoder } from 'util';
import { ReadableStream } from 'stream/web';

let DeepSeekClient;

beforeAll(async () => {
  global.TextDecoder = TextDecoder;
  const mod = await import('../../lib/deepseek.js');
  ({ DeepSeekClient } = mod);
});

afterEach(() => {
  jest.restoreAllMocks();
});

function streamResponse(chunks) {
  const encoder = new TextEncoder();
  return {
    ok: true,
    body: new ReadableStream({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
        controller.close();
      },
    }),
  };
}

describe('DeepSeekClient', () => {
  test('uses JSON mode and thinking mode for structure organization on pro model', async () => {
    global.fetch = jest.fn().mockResolvedValue(streamResponse([
      'data: {"choices":[{"delta":{"reasoning_content":"规划分类"}}]}\n\n',
      'data: {"choices":[{"delta":{"content":"{\\"folders\\":[],\\"bookmarks\\":[]}"}}]}\n\n',
      'data: [DONE]\n\n',
    ]));
    const client = new DeepSeekClient('sk-test', 'deepseek-v4-pro');
    const thinking = [];
    const plan = await client.analyzeBookmarkStructure([
      { title: 'LLVM 入门', url: 'https://example.com', path: ['Bookmarks Bar', '编译'], isTutorial: true },
    ], [], { onThinking: delta => thinking.push(delta) });

    const body = JSON.parse(fetch.mock.calls[0][1].body);
    expect(body.model).toBe('deepseek-v4-pro');
    expect(body.response_format).toEqual({ type: 'json_object' });
    expect(body.thinking).toEqual({ type: 'enabled' });
    expect(body.reasoning_effort).toBe('high');
    expect(body.temperature).toBeUndefined();
    expect(plan).toEqual({ folders: [], bookmarks: [] });
    expect(thinking.join('')).toContain('规划分类');
  });

  test('passes abort signal through chat requests', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ choices: [{ message: { content: 'ok' } }] }),
    });
    const controller = new AbortController();
    const client = new DeepSeekClient('sk-test', 'deepseek-v4-flash');
    await client.chat([{ role: 'user', content: 'hi' }], { signal: controller.signal });

    expect(fetch.mock.calls[0][1].signal).toBe(controller.signal);
  });
});
