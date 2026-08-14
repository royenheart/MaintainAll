// 构建脚本: 产出 host 半边 (lib/index.js, ESM) 和 client 半边 (lib/client.js,
// CJS + window.__ModuleLoader__.load 包装)。client 半边必须是这个包装格式,
// dsh 的 client-modules 加载器才会把它注册为插件 (否则报 "loaded without
// registering ... via __ModuleLoader__.load")。

import { build } from 'tsdown'

const ID = '@maintainall/dsh-plugin-skills-manager'

// 1. host 半边: dsh loader 用 import() 加载, 保持 ESM
await build({
  entry: ['src/index.ts'],
  outDir: 'lib',
  format: 'es',
  platform: 'node',
  clean: true,
})

// 2. client 半边: CJS + __ModuleLoader__.load 包装; react 等从 loader 的
//    module table 走 require, 其余(相对导入)打进 bundle
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
