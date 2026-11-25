export const dashboardViewTemplate = `
  <section class="hero-strip">
    <h2>污水排放批总览</h2>
    <p>采样入库 → 超标挂起 → 准排裁定 → 封批升代 → 许可对账</p>
  </section>
  <div class="stats">
    <div class="stat"><div class="n">{{ dash.plants || 0 }}</div><div class="l">处理厂</div></div>
    <div class="stat"><div class="n">{{ dash.outfalls || 0 }}</div><div class="l">排放口</div></div>
    <div class="stat"><div class="n">{{ dash.samples || 0 }}</div><div class="l">采样批次</div></div>
    <div class="stat"><div class="n">{{ dash.open_exceeds || 0 }}</div><div class="l">开放超标</div></div>
    <div class="stat"><div class="n">{{ dash.discharge_releases || 0 }}</div><div class="l">已准排</div></div>
    <div class="stat"><div class="n">{{ dash.discharge_seals || 0 }}</div><div class="l">已封批</div></div>
    <div class="stat"><div class="n">{{ dash.permits || 0 }}</div><div class="l">许可册</div></div>
    <div class="stat"><div class="n">{{ dash.side_pending || 0 }}</div><div class="l">旁路挂起</div></div>
    <div class="stat"><div class="n" :class="dash.pending_lab_receipts ? 'fail' : ''">{{ dash.pending_lab_receipts || 0 }}</div><div class="l">待回外送</div></div>
    <div class="stat"><div class="n">{{ dash.shadow_pending || 0 }}</div><div class="l">影子待回报</div></div>
    <div class="stat"><div class="n">{{ dash.formal_closed || 0 }}</div><div class="l">正式结案</div></div>
  </div>
  <p class="muted">待回外送数与空桩页同态；外送回执未到禁止结案，正式完成态零写。</p>
    <div class="panel">
      <h3>产品骨架</h3>
      <p class="muted">{{ (dash.meta && dash.meta.skeleton) || "—" }}</p>
    </div>`;
