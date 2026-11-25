export const reconcileViewTemplate = `
  <div class="grid-2">
    <div class="panel">
      <h3>许可对账</h3>
      <div class="actions"><button class="secondary" @click="loadReconcile">刷新全部</button></div>
      <table>
        <thead><tr><th>许可</th><th>对齐</th><th>证明</th><th>待回外送</th><th>影子草稿</th><th>正式结案</th><th>完结灯</th></tr></thead>
        <tbody>
          <tr v-for="r in reconAllItems" :key="r.permit_code">
            <td>{{ r.permit_code }}</td>
            <td :class="r.balanced?'pass':'fail'">{{ r.balanced ? "齐" : "不齐" }}</td>
            <td :class="r.proof_ready?'pass':'warn'">{{ r.proof_ready ? "可证" : "未齐" }}</td>
            <td :class="r.pending_lab_receipts ? 'fail' : 'pass'">{{ r.pending_lab_receipts || 0 }}</td>
            <td :class="r.shadow_count ? 'warn' : 'muted'">{{ r.shadow_count || 0 }}</td>
            <td class="pass">{{ r.formal_closed_count || 0 }}</td>
            <td :class="r.closed_complete ? 'pass' : 'fail'">{{ r.closed_complete ? "可完结" : "禁完结" }}</td>
          </tr>
        </tbody>
      </table>
      <p class="muted" style="margin-top:0.5rem">对账完结灯与空桩待回互斥；影子完成不得当结案。</p>
    </div>
    <div class="panel">
      <h3>单许可 / 采样证明</h3>
      <label>许可号</label><input v-model="reconCode"/>
      <div class="actions"><button @click="loadReconcileOne">对账</button></div>
      <pre v-if="reconOne" style="white-space:pre-wrap;font-size:0.82rem">{{ JSON.stringify(reconOne, null, 2) }}</pre>
      <label>采样号证明</label><input v-model="proofCode"/>
      <div class="actions"><button class="secondary" @click="loadProof">证明</button></div>
      <pre v-if="proofOne" style="white-space:pre-wrap;font-size:0.82rem">{{ JSON.stringify(proofOne, null, 2) }}</pre>
    </div>
  </div>`;
