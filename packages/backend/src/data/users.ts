import type { UserProfile } from '../domain/types';

/**
 * Demo 會員。inbrAccountId 沿用命題數據集裡的 uuid 格式（pms_form_feedback.inbr_account_id）。
 * preferences 在真實情境是由歷史訂單（mms_order_record）+ 對話累積算出來的，
 * 這裡先放初始值，agent 每次對話會持續往上疊加。
 */
export const DEMO_USER_ID = '019a52d3-7f6b-7a51-a53a-3c365f741b49';

export const SEED_USERS: UserProfile[] = [
  {
    inbrAccountId: DEMO_USER_ID,
    displayName: '陳小美',
    mobile: '0935777888',
    email: 'demo@openpoint.example',
    points: 1280,
    addresses: [
      {
        countyCode: '01',
        countyName: '台北市',
        districtCode: '007',
        districtName: '大安區',
        detail: '復興南路一段 100 號 5 樓',
      },
      {
        countyCode: '02',
        countyName: '新北市',
        districtCode: '013',
        districtName: '板橋區',
        detail: '文化路二段 20 號（爸媽家）',
      },
    ],
    appliances: [
      {
        applianceId: 'A1',
        kind: 'AC',
        brand: '大金',
        variant: '分離式',
        installedYear: 2018,
        location: '主臥',
      },
      {
        applianceId: 'A2',
        kind: 'AC',
        brand: '日立',
        variant: '窗型',
        installedYear: 2014,
        location: '客廳',
      },
      { applianceId: 'A3', kind: 'WASHER', brand: 'LG', installedYear: 2021 },
    ],
    preferences: {
      priceSensitivity: 0.6,
      preferredContactTime: '2',
      preferredVendorTags: ['原廠零件', '保固一年'],
      interestedCategories: ['AC_CLEAN', 'HOME_CLEAN'],
      blockedVendorIds: [],
      notes: ['過去偏好假日以外時段', '曾反映不喜歡被推銷加購'],
    },
  },
];
