// Build script: emit the host bundle (lib/index.js, ESM), the client bundle
// (lib/client.js wrapped for window.__ModuleLoader__.load), and type declarations
// (lib/types/**/*.d.ts). The client wrapper is required by dsh's client-modules
// loader; otherwise it reports "loaded without registering ... via
// __ModuleLoader__.load".
//
// Type declarations do not use tsdown's experimental dts output. They use the
// TypeScript compiler API with tsconfig.json, emitDeclarationOnly over src/**,
// and write to lib/types (referenced by package.json types/exports).

import { build } from 'tsdown'
import ts from 'typescript'

const ID = '@royenheart/dsh-plugin-maintainall'

// 1. Host bundle: dsh loads it with import(), so keep ESM
await build({
  entry: { index: 'src/index.ts' },
  outDir: 'lib',
  format: 'es',
  platform: 'node',
  clean: true,
  outputOptions: {
    entryFileNames: 'index.js',
  },
})

// 2. Client bundle: CJS wrapped in __ModuleLoader__.load; react and peers use
//    the loader module table, while relative imports are bundled
await build({
  entry: { client: 'src/client.ts' },
  outDir: 'lib',
  format: 'cjs',
  platform: 'browser',
  external: ['react', /^react\//, /^@deepseek-ai\//],
  clean: false,
  outputOptions: {
    entryFileNames: 'client.js',
    banner: `window.__ModuleLoader__.load({ id: ${JSON.stringify(ID)}, factory: (require) => {`,
    intro: 'var module = { exports: {} }; var exports = module.exports;',
    footer: 'return module.exports; } });',
  },
})

// 3. Type declarations: tsc emitDeclarationOnly over src/**, output to lib/types/
const configPath = ts.findConfigFile('.', ts.sys.fileExists, 'tsconfig.json')
if (!configPath) throw new Error('tsconfig.json not found')
const { config, error: readError } = ts.readConfigFile(configPath, ts.sys.readFile)
if (readError) throw new Error(ts.flattenDiagnosticMessageText(readError.messageText, '\n'))
const parsed = ts.parseJsonConfigFileContent(config, ts.sys, '.', {
  noEmit: false,
  emitDeclarationOnly: true,
  declaration: true,
  rootDir: 'src',
  outDir: 'lib/types',
})
const files = parsed.fileNames.filter((f) => f.startsWith('src/') || f.startsWith('src\\'))
const program = ts.createProgram(files, parsed.options)
const emit = program.emit()
const diagnostics = [...ts.getPreEmitDiagnostics(program), ...emit.diagnostics]
if (diagnostics.length > 0) {
  const host = {
    getCanonicalFileName: (f) => f,
    getCurrentDirectory: () => process.cwd(),
    getNewLine: () => '\n',
  }
  process.stderr.write(ts.formatDiagnosticsWithColorAndContext(diagnostics, host))
}
if (emit.emitSkipped || diagnostics.some((d) => d.category === ts.DiagnosticCategory.Error)) {
  throw new Error('declaration emit failed')
}
