export const stubsViewTemplate = `
  <div class="grid-2">
    <div class="panel">
      <h3>空桩 · 外送化验快递 <span class="tag warn" v-if="pendingLabJobs.length">待回 {{ pendingLabJobs.length }}</span></h3>
      <p class="muted">接口可点，默认 dry_run，未接通外送系统。回执列空即“待回”，回执未到准排页结案键拒写。</p>
      <label>采样号</label><input v-model="labForm.sample_code"/>
      <label>快递槽</label><input v-model="labForm.courier_slot"/>
      <div class="actions"><button @click="enqueueLab">演练入队</button></div>
      <table style="margin-top:0.8rem">
        <thead><tr><th>ID</th><th>采样</th><th>槽</th><th>作业态</th><th>回执列</th><th>回执号</th></tr></thead>
        <tbody>
          <tr v-for="j in labJobs" :key="j.id">
            <td>{{ j.id }}</td><td>{{ j.sample_code }}</td><td>{{ j.courier_slot }}</td>
            <td>{{ j.status }}</td>
            <td :class="j.receipt_status ? 'pass' : 'fail'">{{ j.receipt_status || "待回" }}</td>
            <td>{{ j.receipt_no || "—" }}</td>
          </tr>
        </tbody>
      </table>
      <h3 style="margin-top:1rem">回执到达签收</h3>
      <label>外送作业 ID</label>
      <select v-model.number="receiptForm.job_id">
        <option v-for="j in labJobs" :key="j.id" :value="j.id">{{ j.id }} · {{ j.sample_code }} · {{ j.receipt_status || "待回" }}</option>
      </select>
      <label>回执号（可空自动）</label><input v-model="receiptForm.receipt_no"/>
      <div class="actions"><button @click="markLabReceipt">回执签收</button></div>
    </div>
    <div class="panel">
      <h3>空桩 · 污泥消化排程</h3>
      <p class="muted">接口可点，默认 dry_run，未接通污泥仓排程。</p>
      <label>厂 ID</label><input type="number" v-model.number="sludgeForm.plant_id"/>
      <label>消化仓</label><input v-model="sludgeForm.digester_bay"/>
      <div class="actions"><button @click="enqueueSludge">演练入队</button></div>
      <table style="margin-top:0.8rem">
        <thead><tr><th>ID</th><th>仓</th><th>模式</th><th>状态</th></tr></thead>
        <tbody>
          <tr v-for="j in sludgeJobs" :key="j.id"><td>{{ j.id }}</td><td>{{ j.digester_bay }}</td><td>{{ j.mode }}</td><td>{{ j.status }}</td></tr>
        </tbody>
      </table>
    </div>
  </div>`;
