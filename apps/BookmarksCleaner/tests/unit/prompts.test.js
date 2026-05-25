import { describe, test, expect } from '@jest/globals';

let DEFAULT_PROMPTS, fillPrompt;

beforeAll(async () => {
  const mod = await import('../../lib/prompts.js');
  ({ DEFAULT_PROMPTS, fillPrompt } = mod);
});

describe('DEFAULT_PROMPTS', () => {
  test('has all required prompt keys', () => {
    const keys = ['titleCleaner', 'titleCleanerUser', 'classify', 'classifyUser',
                  'structureOrganizer', 'structureOrganizerUser',
                  'topicSummary', 'topicSummaryUser'];
    for (const k of keys) {
      expect(DEFAULT_PROMPTS[k]).toBeDefined();
      expect(DEFAULT_PROMPTS[k].length).toBeGreaterThan(10);
    }
  });
});

describe('fillPrompt', () => {
  test('replaces placeholders', () => {
    const template = 'Hello {name}, you have {count} items';
    const result = fillPrompt(template, { name: 'World', count: '5' });
    expect(result).toBe('Hello World, you have 5 items');
  });

  test('handles missing vars gracefully', () => {
    const template = 'Hello {name}';
    const result = fillPrompt(template, {});
    expect(result).toBe('Hello {name}');
  });
});
