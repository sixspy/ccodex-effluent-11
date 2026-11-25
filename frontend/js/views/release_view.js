export const releaseViewTemplate = `
  <div class="grid-2">
    <div class="panel">
      <h3>准排放记录</h3>
      <table>
        <thead><tr><th>准排号</th><th>采样</th><th>口</th><th>值班</th><th>时间</th></tr></thead>
        <tbody>
          <tr v-for="r in releases" :key="r.id">
            <td>{{ r.release_ref }}</td><td>{{ r.sample_code }}</td><td>{{ r.outfall_code }}</td>
            <td>{{ r.officer }}</td><td>{{ r.released_at }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="panel">
      <h3>签发准排</h3>
      <label>已裁定采样</label>
      <select v-model.number="releaseForm.sample_id">
        <option v-for="s in releasableSamples" :key="s.id" :value="s.id">{{ s.sample_code }} · {{ s.status }}</option>
      </select>
      <label>值班员</label><input v-model="releaseForm.officer"/>
      <div class="actions"><button @click="createRelease">准排</button></div>
    </div>
    <div class="panel" style="grid-column:1 / -1">
      <h3>排放批结案（回执禁结 · 当日锁死）</h3>
      <p class="muted">
        拍板口径：外送回执到达与结案完成写库两边不得混用。
        甲路径（正式）回执列空当场拒写、完成态零改；乙路径（影子）无回执只登记待回报草稿，
        回执到达后原子升正、草稿作废。双口径混用即无回执出正式完成，旁门不要。
      </p>
      <p v-if="pendingLabJobs.length" class="banner err" style="margin:0.4rem 0">
        空桩待回 {{ pendingLabJobs.length }} 笔：{{ pendingLabJobs.map(j => j.sample_code).join("、") }} —— 这些批次正式结案键拒写
      </p>
      <div class="form-row">
        <div>
          <label>已封批待结案采样</label>
          <select v-model.number="completeForm.sample_id">
            <option v-for="s in completableSamples" :key="s.id" :value="s.id">{{ s.sample_code }} · {{ s.status }}</option>
          </select>
        </div>
        <div>
          <label>结案路径</label>
          <select v-model="completeForm.mode">
            <option value="formal">甲 · 正式（无回执拒写）</option>
            <option value="shadow">乙 · 影子（仅登记草稿）</option>
          </select>
        </div>
      </div>
      <div class="actions">
        <button class="warn" @click="completeCase">结案写口</button>
      </div>
    </div>
  </div>`;
