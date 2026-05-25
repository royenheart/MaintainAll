/** @type {import('jest').Config} */
export default {
  testEnvironment: 'jsdom',
  testMatch: ['<rootDir>/tests/unit/**/*.test.js'],
  moduleNameMapper: {
    '^(\\.{1,2}/.*)\\.js$': '$1',
  },
  transform: {},
  roots: ['<rootDir>/tests/unit'],
  collectCoverageFrom: [
    'lib/**/*.js',
    '!lib/deepseek.js', // requires fetch mock
  ],
  coverageDirectory: '<rootDir>/build/coverage',
  coverageReporters: ['text', 'lcov'],
};
