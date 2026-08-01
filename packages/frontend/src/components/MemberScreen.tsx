import type { UserProfile, UserPreferences } from '../types';
import { PERIOD_LABEL } from '../types';
import { MascotIcon, TileIcon } from './icons';

/**
 * 會員中心。
 *
 * 這個畫面是提案的第二個重點：**管家學到的東西是會員看得見的資產**。
 * OpenPoint 現在不會告訴你「系統覺得你在意價格」，
 * 我們把它攤開，而且會員能理解為什麼下次推薦長那樣。
 */

function SensitivityBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const label = value >= 0.75 ? '很在意價格' : value <= 0.35 ? '不太在意價格' : '中等';
  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: 12,
          marginBottom: 4,
        }}
      >
        <span style={{ color: '#6b7280' }}>價格敏感度</span>
        <span style={{ fontWeight: 700, color: '#00842f' }}>{label}</span>
      </div>
      <div
        style={{ height: 8, borderRadius: 4, background: '#e6e8eb', overflow: 'hidden' }}
        role="img"
        aria-label={`價格敏感度 ${pct}%`}
      >
        <div
          style={{
            width: `${pct}%`,
            height: '100%',
            background: 'linear-gradient(90deg, #7cb342, #00a03e)',
            transition: 'width .4s ease',
          }}
        />
      </div>
      <div style={{ fontSize: 10.5, color: '#9aa1ab', marginTop: 4 }}>
        管家會依這個值調整報價與品質的排序權重
      </div>
    </div>
  );
}

const KIND_LABEL: Record<string, string> = {
  AC: '冷氣',
  WASHER: '洗衣機',
  FRIDGE: '冰箱',
  WATER_HEATER: '熱水器',
};

export function MemberScreen({
  user,
  livePreferences,
}: {
  user?: UserProfile;
  /** 對話中即時更新的偏好，優先於載入時的快照 */
  livePreferences?: UserPreferences | null;
}) {
  if (!user) {
    return (
      <div className="screen">
        <div className="empty-state">
          <MascotIcon size={64} />
          <h3>載入會員資料中</h3>
          <p>連不到後端時這裡會是空的。</p>
        </div>
      </div>
    );
  }

  const prefs = livePreferences ?? user.preferences ?? {};
  const thisYear = new Date().getFullYear();

  return (
    <div className="screen">
      {/* ---- 會員卡 ---- */}
      <div
        style={{
          margin: '10px 12px',
          borderRadius: 14,
          padding: '16px 18px',
          background: 'linear-gradient(120deg, #00a03e, #4a9fd8)',
          color: '#fff',
          boxShadow: '0 1px 3px rgba(0,0,0,.06)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div
            style={{
              width: 46,
              height: 46,
              borderRadius: '50%',
              background: 'rgba(255,255,255,.25)',
              display: 'grid',
              placeItems: 'center',
              fontSize: 20,
              fontWeight: 700,
            }}
            aria-hidden
          >
            {user.displayName.slice(0, 1)}
          </div>
          <div>
            <div style={{ fontSize: 17, fontWeight: 800 }}>{user.displayName}</div>
            <div style={{ fontSize: 11, opacity: 0.9 }}>
              會員編號 {user.inbrAccountId.slice(0, 8)}…
            </div>
          </div>
          <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
            <div style={{ fontSize: 10, opacity: 0.9 }}>OPEN POINT</div>
            <div style={{ fontSize: 22, fontWeight: 800, lineHeight: 1.1 }}>
              {(user.points ?? 0).toLocaleString('zh-TW')}
            </div>
          </div>
        </div>
      </div>

      {/* ---- 管家記住的偏好（提案重點）---- */}
      <section className="card" aria-labelledby="pref-title">
        <div className="card-head green">
          <span id="pref-title">管家記住的事</span>
          <span className="link">會隨對話更新</span>
        </div>
        <div style={{ padding: '14px' }}>
          <SensitivityBar value={prefs.priceSensitivity ?? 0.5} />

          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 5 }}>偏好時段</div>
            <div style={{ display: 'flex', gap: 6 }}>
              {(['1', '2', '3'] as const).map((p) => (
                <span
                  key={p}
                  className={`chip${prefs.preferredContactTime === p ? ' green' : ''}`}
                  style={{ fontSize: 12, padding: '4px 12px' }}
                >
                  {PERIOD_LABEL[p]}
                </span>
              ))}
            </div>
          </div>

          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 5 }}>你重視的服務特質</div>
            <div className="chips">
              {(prefs.preferredVendorTags ?? []).length > 0 ? (
                prefs.preferredVendorTags!.map((t) => (
                  <span key={t} className="chip green" style={{ fontSize: 11.5 }}>
                    {t}
                  </span>
                ))
              ) : (
                <span style={{ fontSize: 12, color: '#9aa1ab' }}>還沒累積</span>
              )}
            </div>
          </div>

          {(prefs.notes ?? []).length > 0 && (
            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 5 }}>管家的觀察筆記</div>
              <ul
                style={{
                  margin: 0,
                  paddingLeft: 16,
                  fontSize: 12,
                  color: '#4b5563',
                  lineHeight: 1.8,
                }}
              >
                {prefs.notes!.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </div>
          )}

          {(prefs.interestedCategories ?? []).length > 0 && (
            <div
              style={{
                marginTop: 16,
                background: '#f6f8fa',
                borderRadius: 10,
                padding: '10px 12px',
              }}
            >
              <div style={{ fontSize: 11.5, color: '#6b7280', lineHeight: 1.7 }}>
                依你的使用紀錄，之後會優先推播：
                <br />
                <strong style={{ color: '#00842f' }}>
                  {prefs
                    .interestedCategories!.map(
                      (c) =>
                        ({
                          AC_REPAIR: '冷氣維修',
                          AC_CLEAN: '冷氣清洗',
                          PLUMBING: '水電修繕',
                          HOME_CLEAN: '居家清潔',
                        })[c] ?? c,
                    )
                    .join('、')}
                </strong>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* ---- 我的家電（agent 免問的依據）---- */}
      <section className="card" aria-labelledby="appl-title">
        <div className="card-head">
          <span id="appl-title">我的家電</span>
          <span className="link" style={{ color: '#9aa1ab' }}>
            {user.appliances.length} 台
          </span>
        </div>
        <div style={{ padding: '4px 0 8px' }}>
          {user.appliances.map((a) => (
            <div
              key={a.applianceId}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 11,
                padding: '9px 14px',
                borderBottom: '1px solid #f2f4f6',
              }}
            >
              <TileIcon
                glyph={a.kind === 'AC' ? '冷' : a.kind === 'WASHER' ? '洗' : '電'}
                bg={a.kind === 'AC' ? '#00a9c8' : '#4a9fd8'}
                size={34}
              />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13.5, fontWeight: 600 }}>
                  {a.location ? `${a.location} · ` : ''}
                  {a.brand} {KIND_LABEL[a.kind] ?? a.kind}
                </div>
                <div style={{ fontSize: 11, color: '#9aa1ab' }}>
                  {a.variant ? `${a.variant} · ` : ''}
                  {a.installedYear
                    ? `${a.installedYear} 年安裝（約 ${thisYear - a.installedYear} 年）`
                    : '安裝年份未填'}
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ---- 常用地址 ---- */}
      <section className="card" aria-labelledby="addr-title">
        <div className="card-head">
          <span id="addr-title">常用地址</span>
        </div>
        <div style={{ padding: '4px 0 8px' }}>
          {user.addresses.map((a, i) => (
            <div
              key={i}
              style={{ padding: '9px 14px', borderBottom: '1px solid #f2f4f6', fontSize: 13 }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                {i === 0 && <span className="chip green">預設</span>}
                <span style={{ fontWeight: 600 }}>
                  {a.countyName}
                  {a.districtName}
                </span>
                <span style={{ marginLeft: 'auto', fontSize: 10.5, color: '#c3c8ce' }}>
                  {a.countyCode}/{a.districtCode}
                </span>
              </div>
              <div style={{ fontSize: 11.5, color: '#6b7280', marginTop: 2 }}>{a.detail}</div>
            </div>
          ))}
        </div>
      </section>

      <div
        style={{
          textAlign: 'center',
          fontSize: 10.5,
          color: '#b6bcc4',
          padding: '6px 24px 18px',
          lineHeight: 1.7,
        }}
      >
        地址與電話目前為明文儲存（demo 用）。
        <br />
        正式環境將依 pms_form_feedback 做法改為 aes256-gcm 加密。
      </div>
    </div>
  );
}
