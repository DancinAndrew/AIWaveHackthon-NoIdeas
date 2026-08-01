/**
 * 從統一資訊提供的「縣市區域範例資料.json」產生 TS 常數檔。
 * 該檔案是多個 JSON 物件串接（{"sys_county":[...]} 後面接 {"sys_district":[...]}），
 * 不是合法的單一 JSON，所以這裡用括號配對切開後逐段 parse。
 *
 * 用法：node scripts/gen-geo.mjs
 */
import { readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const dataDir = readdirSync('.').find((d) => d.includes('命題數據集'));
if (!dataDir) throw new Error('找不到命題數據集資料夾');
const src = join(dataDir, '縣市區域範例資料.json');
const raw = readFileSync(src, 'utf8');

/** 用大括號配對，把串接的多個 JSON 物件切出來 */
function splitJsonObjects(text) {
  const out = [];
  let depth = 0;
  let start = -1;
  let inStr = false;
  let esc = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inStr) {
      if (esc) esc = false;
      else if (c === '\\') esc = true;
      else if (c === '"') inStr = false;
      continue;
    }
    if (c === '"') inStr = true;
    else if (c === '{') {
      if (depth === 0) start = i;
      depth++;
    } else if (c === '}') {
      depth--;
      if (depth === 0 && start >= 0) {
        out.push(text.slice(start, i + 1));
        start = -1;
      }
    }
  }
  return out;
}

const counties = [];
const districts = [];
for (const chunk of splitJsonObjects(raw)) {
  let obj;
  try {
    obj = JSON.parse(chunk);
  } catch {
    continue;
  }
  if (Array.isArray(obj.sys_county)) counties.push(...obj.sys_county);
  if (Array.isArray(obj.sys_district)) districts.push(...obj.sys_district);
}

const activeCounties = counties
  .filter((c) => c.is_deleted === '0')
  .sort((a, b) => a.sort - b.sort)
  .map((c) => ({ code: c.code, name: c.name }));

const activeDistricts = districts
  .filter((d) => d.is_deleted === '0')
  .sort((a, b) => (a.county_code === b.county_code ? a.sort - b.sort : a.county_code.localeCompare(b.county_code)))
  .map((d) => ({ code: d.code, countyCode: d.county_code, name: d.name, zip: d.zip }));

const banner = `/**
 * 自動產生，請勿手改。來源：${src.replace(/\\/g, '/')}
 * 重新產生：node scripts/gen-geo.mjs
 * sys_county / sys_district（縣市代碼 2 碼、行政區代碼 3 碼）
 */`;

const ts = `${banner}

export interface CountyRow {
  code: string;
  name: string;
}

export interface DistrictRow {
  code: string;
  countyCode: string;
  name: string;
  zip: string;
}

export const COUNTIES: CountyRow[] = ${JSON.stringify(activeCounties, null, 2)};

export const DISTRICTS: DistrictRow[] = ${JSON.stringify(activeDistricts, null, 2)};
`;

const outPath = join('packages', 'backend', 'src', 'data', 'geo.generated.ts');
writeFileSync(outPath, ts, 'utf8');
console.log(`counties=${activeCounties.length} districts=${activeDistricts.length} -> ${outPath}`);
