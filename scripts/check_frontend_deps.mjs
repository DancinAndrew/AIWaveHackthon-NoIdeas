/**
 * 檢查前端相依是否真的可用（不只是資料夾存在）。
 * npm 新版會擋住未核准的 install script，esbuild 的平台 binary 可能沒下載，
 * 那樣 vite 會在啟動時才爆，這支腳本讓問題提早浮現。
 */
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const nm = join(root, 'node_modules');

function pkgVersion(name) {
  const p = join(nm, ...name.split('/'), 'package.json');
  if (!existsSync(p)) return null;
  try {
    return JSON.parse(readFileSync(p, 'utf8')).version;
  } catch {
    return null;
  }
}

const checks = [
  ['react', 'react'],
  ['react-dom', 'react-dom'],
  ['vite', 'vite'],
  ['@vitejs/plugin-react', '@vitejs/plugin-react'],
  ['typescript', 'typescript'],
  ['esbuild', 'esbuild'],
];

let fail = 0;
for (const [label, name] of checks) {
  const v = pkgVersion(name);
  if (v) {
    console.log(`  [PASS] ${label.padEnd(22)} ${v}`);
  } else {
    console.log(`  [FAIL] ${label.padEnd(22)} 找不到`);
    fail++;
  }
}

// esbuild 的平台 binary：Windows 是 @esbuild/win32-x64 裡的 esbuild.exe
const esbuildExe = join(nm, '@esbuild', 'win32-x64', 'esbuild.exe');
if (existsSync(esbuildExe)) {
  console.log('  [PASS] esbuild 平台 binary       已存在');
} else {
  console.log('  [FAIL] esbuild 平台 binary       缺少（vite 會啟動失敗）');
  console.log('         解法：cmd /c "npm approve-scripts --allow-scripts-pending"');
  fail++;
}

console.log('');
console.log(fail === 0 ? '前端相依 OK' : `有 ${fail} 項問題`);
process.exit(fail === 0 ? 0 : 1);
