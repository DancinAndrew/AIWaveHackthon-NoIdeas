import type { VendorProposal } from '../types';
import { PERIOD_LABEL } from '../types';
import { StarIcon } from './icons';

const money = (n: number) => n.toLocaleString('zh-TW');

/** 把 2026-08-02 轉成「8/2（日）」，讓會員一眼看懂是禮拜幾 */
function friendlyDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  const week = ['日', '一', '二', '三', '四', '五', '六'][d.getDay()];
  const today = new Date();
  const diff = Math.round((d.getTime() - new Date(today.toDateString()).getTime()) / 86400000);
  const prefix = diff === 0 ? '今天 ' : diff === 1 ? '明天 ' : '';
  return `${prefix}${d.getMonth() + 1}/${d.getDate()}（${week}）`;
}

/**
 * 廠商方案卡。
 *
 * 所有數字都直接來自後端 —— 前端不做任何金額計算，
 * 這樣「報價由規則引擎產生、不是 LLM 編的」這個保證才守得住。
 */
export function ProposalCard({
  proposal,
  isBest,
  onPick,
  disabled,
}: {
  proposal: VendorProposal;
  isBest: boolean;
  onPick: (p: VendorProposal) => void;
  disabled?: boolean;
}) {
  const q = proposal.quote;
  const risks = q.majorRisks ?? [];

  return (
    <article className={`proposal${isBest ? ' best' : ''}`}>
      <div className="proposal-top">
        {isBest && <span className="best-tag">推薦</span>}
        <span className="proposal-name">{proposal.vendorName}</span>
        <span className="rating">
          <StarIcon size={11} /> {proposal.rating}
        </span>
      </div>

      <div className="price">
        {money(q.estimatedMin)}–{money(q.estimatedMax)} <small>元</small>
      </div>
      <div className="meta">
        含到府檢測 {money(q.inspectionFee)} 元 · 最快{' '}
        {friendlyDate(proposal.earliestSlot.date)}
        {PERIOD_LABEL[proposal.earliestSlot.period] ?? ''}
      </div>

      <div className="chips">
        {proposal.supportsPoints && <span className="chip green">可折點數</span>}
        {proposal.tags.slice(0, 4).map((t) => (
          <span key={t} className="chip">
            {t}
          </span>
        ))}
      </div>

      {proposal.reasons.length > 0 && (
        <ul>
          {proposal.reasons.slice(0, 3).map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      )}

      {risks.length > 0 && (
        <div className="risk">
          最壞情況：
          {risks
            .map((r) => `${r.name} ${money(r.minPrice)}–${money(r.maxPrice)} 元`)
            .join('、')}
          （不含在上方報價內）
        </div>
      )}

      <button
        className={`pick${isBest ? '' : ' ghost'}`}
        onClick={() => onPick(proposal)}
        disabled={disabled}
      >
        就約這家
      </button>
    </article>
  );
}
