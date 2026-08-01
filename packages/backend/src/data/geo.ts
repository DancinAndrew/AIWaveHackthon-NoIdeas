import type { Address } from '../domain/types';
import { COUNTIES, DISTRICTS } from './geo.generated';

/** 台北/臺北、台中/臺中 等異體字正規化 */
function normalize(name: string): string {
  return name.trim().replace(/臺/g, '台').replace(/\s/g, '');
}

const countyByCode = new Map(COUNTIES.map((c) => [c.code, c]));
const districtByCode = new Map(DISTRICTS.map((d) => [d.code, d]));

export function findCounty(input: string): { code: string; name: string } | undefined {
  const q = normalize(input);
  const exact = COUNTIES.find((c) => normalize(c.name) === q);
  if (exact) return exact;
  // 「台北」→「台北市」
  return COUNTIES.find((c) => normalize(c.name).startsWith(q) || q.startsWith(normalize(c.name)));
}

export function findDistrict(
  countyCode: string,
  input: string,
): { code: string; name: string } | undefined {
  const q = normalize(input);
  const pool = DISTRICTS.filter((d) => d.countyCode === countyCode);
  const exact = pool.find((d) => normalize(d.name) === q);
  if (exact) return exact;
  return pool.find((d) => normalize(d.name).startsWith(q) || q.startsWith(normalize(d.name)));
}

export function listDistricts(countyCode: string): string[] {
  return DISTRICTS.filter((d) => d.countyCode === countyCode).map((d) => d.name);
}

/**
 * 把使用者口語地址解析成 Address（含統一資訊的 county/district code）。
 * 例：「台北市大同區承德路三段10號」
 */
export function resolveAddress(input: {
  county?: string;
  district?: string;
  detail?: string;
  freeText?: string;
}): Address | undefined {
  let countyRaw = input.county;
  let districtRaw = input.district;
  let detail = input.detail;

  if (input.freeText && (!countyRaw || !districtRaw)) {
    const text = normalize(input.freeText);
    const county = COUNTIES.find((c) => text.includes(normalize(c.name)));
    if (county) {
      countyRaw = county.name;
      const rest = text.slice(text.indexOf(normalize(county.name)) + county.name.length);
      const district = DISTRICTS.filter((d) => d.countyCode === county.code).find((d) =>
        rest.startsWith(normalize(d.name)),
      );
      if (district) {
        districtRaw = district.name;
        detail = detail ?? rest.slice(district.name.length);
      } else {
        detail = detail ?? rest;
      }
    }
  }

  if (!countyRaw) return undefined;
  const county = findCounty(countyRaw);
  if (!county) return undefined;

  const district = districtRaw ? findDistrict(county.code, districtRaw) : undefined;
  if (!district) return undefined;

  return {
    countyCode: county.code,
    countyName: county.name,
    districtCode: district.code,
    districtName: district.name,
    detail: detail?.trim() || undefined,
  };
}

export function describeAddress(a: Address): string {
  return `${a.countyName}${a.districtName}${a.detail ?? ''}`;
}

export function countyName(code: string): string {
  return countyByCode.get(code)?.name ?? code;
}

export function districtName(code: string): string {
  return districtByCode.get(code)?.name ?? code;
}
