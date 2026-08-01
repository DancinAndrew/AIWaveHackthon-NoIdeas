import type { Vendor } from '../domain/types';

/** 判斷廠商是否服務該縣市／行政區 */
export function vendorCovers(vendor: Vendor, countyCode: string, districtCode?: string): boolean {
  const c = vendor.coverage.find((x) => x.countyCode === countyCode);
  if (!c) return false;
  if (c.districtCodes === 'ALL') return true;
  if (!districtCode) return true;
  return c.districtCodes.includes(districtCode);
}
