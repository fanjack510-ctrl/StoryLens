/** VIP / license surface for ordinary users (placeholders until product launch). */

export function SettingsLicenseTab() {
  return (
    <article className="settings-panel" data-testid="settings-panel-license">
      <header className="settings-panel-header">
        <h2>授权与会员</h2>
        <p>当前为免费版，全部现有功能均可使用。</p>
      </header>

      <dl className="ai-status-meta">
        <div>
          <dt>当前版本</dt>
          <dd>免费版</dd>
        </div>
        <div>
          <dt>VIP 状态</dt>
          <dd data-testid="vip-status">即将开放</dd>
        </div>
      </dl>

      <label className="settings-field">
        <span>激活码</span>
        <input
          disabled
          placeholder="VIP 上线后在此输入"
          aria-label="激活码"
          data-testid="vip-activation-input"
        />
      </label>

      <section className="privacy-note" data-testid="vip-feature-slot">
        <h3>VIP 功能预览</h3>
        <p>更高分析配额、优先支持等权益正在筹备中，不会限制你当前的使用。</p>
      </section>

      <button type="button" disabled data-testid="vip-purchase">
        购买 VIP（即将开放）
      </button>
    </article>
  );
}
