import { getPrinterStatus, getSettings, pruneHistory, putSettings } from '../api'

export function mountSettings(root: HTMLElement): void {
  root.innerHTML = `
    <div class="settings-page">
      <h2>Settings</h2>
      <section class="settings-section">
        <h3>Printer</h3>
        <div id="printer-settings"><p>Loading…</p></div>
        <div class="setting-actions">
          <button id="btn-test-printer">Test Printer</button>
        </div>
        <div id="printer-test-result" hidden></div>
      </section>
      <section class="settings-section">
        <h3>History &amp; Retention</h3>
        <div id="retention-status" class="status-msg" hidden></div>
        <div id="retention-form"><p>Loading…</p></div>
      </section>
      <section class="settings-section">
        <h3>Updates</h3>
        <div id="updates-settings"><p>Loading…</p></div>
      </section>
    </div>
  `

  const statusEl = root.querySelector<HTMLDivElement>('#retention-status')!
  const formEl = root.querySelector<HTMLDivElement>('#retention-form')!
  const btnTestPrinter = root.querySelector<HTMLButtonElement>('#btn-test-printer')!
  const printerResultEl = root.querySelector<HTMLDivElement>('#printer-test-result')!
  const printerSettingsEl = root.querySelector<HTMLDivElement>('#printer-settings')!

  btnTestPrinter.addEventListener('click', async () => {
    btnTestPrinter.disabled = true
    btnTestPrinter.textContent = 'Testing…'
    printerResultEl.hidden = true
    printerResultEl.className = ''
    try {
      const { ok, body } = await getPrinterStatus()
      if (ok) {
        const ready = body.ready as boolean
        const model = body.model as string | null
        const loaded = body.loaded_media as Record<string, unknown> | null
        const errors = (body.errors as string[]) ?? []
        const source = body.source as string | null
        const readyText = ready ? 'Ready' : 'Not ready'
        const mediaText = loaded ? (loaded.display_name as string) : 'No media'
        const modelText = model ?? 'Unknown model'
        const errText = errors.length ? `<div class="status-msg error">${errors.join(', ')}</div>` : ''
        printerResultEl.innerHTML = `
          <div class="printer-status-block">
            <span class="printer-status-ready ${ready ? 'ok' : 'warn'}">${readyText}</span>
            <span class="printer-status-model">${modelText}</span>
            <span class="printer-status-media">${mediaText}</span>
            ${errText}
            <span class="printer-status-source">${source ?? ''}</span>
          </div>`
        printerResultEl.className = 'status-msg success'
      } else {
        const msg = (body.message as string) || `HTTP error`
        printerResultEl.textContent = msg
        printerResultEl.className = 'status-msg error'
      }
    } catch (err) {
      printerResultEl.textContent = (err as Error).message
      printerResultEl.className = 'status-msg error'
    } finally {
      printerResultEl.hidden = false
      btnTestPrinter.disabled = false
      btnTestPrinter.textContent = 'Test Printer'
    }
  })

  function showStatus(msg: string, kind: 'success' | 'error'): void {
    statusEl.textContent = msg
    statusEl.className = `status-msg ${kind}`
    statusEl.hidden = false
  }

  function renderForm(settings: Record<string, unknown>): void {
    const mode = (settings.retention_mode as string) || 'forever'
    const count = (settings.retention_count as number) ?? 500
    const days = (settings.retention_days as number) ?? 90

    formEl.innerHTML = `
      <div class="radio-group retention-modes">
        <label><input type="radio" name="retention_mode" value="forever" ${mode === 'forever' ? 'checked' : ''} /> Keep forever</label>
        <label><input type="radio" name="retention_mode" value="last_n" ${mode === 'last_n' ? 'checked' : ''} /> Keep last N</label>
        <label><input type="radio" name="retention_mode" value="last_days" ${mode === 'last_days' ? 'checked' : ''} /> Keep last N days</label>
      </div>
      <div id="count-row" class="setting-row" ${mode !== 'last_n' ? 'hidden' : ''}>
        <span class="setting-row-label">Keep last</span>
        <input type="number" id="retention-count" min="1" max="100000" value="${count}" />
        <span class="setting-hint">most recent unpinned prints</span>
      </div>
      <div id="days-row" class="setting-row" ${mode !== 'last_days' ? 'hidden' : ''}>
        <span class="setting-row-label">Keep prints from last</span>
        <input type="number" id="retention-days" min="1" max="36500" value="${days}" />
        <span class="setting-hint">days</span>
      </div>
      <p class="setting-hint">Pinned prints are never pruned regardless of mode.</p>
      <div class="setting-actions">
        <button id="btn-save" class="btn-primary">Save</button>
        <button id="btn-prune">Run cleanup now</button>
      </div>
    `

    const radios = formEl.querySelectorAll<HTMLInputElement>('input[name="retention_mode"]')
    const countRow = formEl.querySelector<HTMLDivElement>('#count-row')!
    const daysRow = formEl.querySelector<HTMLDivElement>('#days-row')!
    const countInput = formEl.querySelector<HTMLInputElement>('#retention-count')!
    const daysInput = formEl.querySelector<HTMLInputElement>('#retention-days')!
    const btnSave = formEl.querySelector<HTMLButtonElement>('#btn-save')!
    const btnPrune = formEl.querySelector<HTMLButtonElement>('#btn-prune')!

    function getMode(): string {
      return Array.from(radios).find(r => r.checked)?.value ?? 'forever'
    }

    function updateVisibility(): void {
      const m = getMode()
      countRow.hidden = m !== 'last_n'
      daysRow.hidden = m !== 'last_days'
    }

    radios.forEach(r => r.addEventListener('change', updateVisibility))

    btnSave.addEventListener('click', async () => {
      btnSave.disabled = true
      statusEl.hidden = true
      const m = getMode()
      const patch: Record<string, unknown> = { retention_mode: m }
      if (m === 'last_n') patch.retention_count = parseInt(countInput.value, 10) || 500
      if (m === 'last_days') patch.retention_days = parseInt(daysInput.value, 10) || 90
      try {
        await putSettings(patch)
        showStatus('Retention settings saved.', 'success')
      } catch (err) {
        showStatus((err as Error).message, 'error')
      } finally {
        btnSave.disabled = false
      }
    })

    btnPrune.addEventListener('click', async () => {
      btnPrune.disabled = true
      btnPrune.textContent = 'Running…'
      statusEl.hidden = true
      try {
        const result = await pruneHistory()
        const pruned = typeof result.pruned === 'number' ? result.pruned : '?'
        showStatus(`Cleanup done — ${pruned} job(s) removed.`, 'success')
      } catch (err) {
        showStatus((err as Error).message, 'error')
      } finally {
        btnPrune.disabled = false
        btnPrune.textContent = 'Run cleanup now'
      }
    })
  }

  function renderPrinterSettings(settings: Record<string, unknown>): void {
    const checkEnabled = settings.printer_status_check !== false
    const timeout = (settings.printer_status_timeout_ms as number) ?? 2000

    printerSettingsEl.innerHTML = `
      <label class="setting-row">
        <input type="checkbox" id="status-check-enabled" ${checkEnabled ? 'checked' : ''} />
        <span class="setting-row-label">Status check enabled</span>
        <span class="setting-hint">query the printer before each print</span>
      </label>
      <div class="setting-row">
        <span class="setting-row-label">Status timeout</span>
        <input type="number" id="status-timeout" min="100" max="60000" step="100" value="${timeout}" />
        <span class="setting-hint">ms to wait for a status response</span>
      </div>
      <div class="setting-actions">
        <button id="btn-save-printer" class="btn-primary">Save</button>
      </div>
      <div id="printer-save-status" class="status-msg" hidden></div>
    `

    const checkbox = printerSettingsEl.querySelector<HTMLInputElement>('#status-check-enabled')!
    const timeoutInput = printerSettingsEl.querySelector<HTMLInputElement>('#status-timeout')!
    const btnSavePrinter = printerSettingsEl.querySelector<HTMLButtonElement>('#btn-save-printer')!
    const printerSaveStatus = printerSettingsEl.querySelector<HTMLDivElement>('#printer-save-status')!

    btnSavePrinter.addEventListener('click', async () => {
      btnSavePrinter.disabled = true
      printerSaveStatus.hidden = true
      try {
        await putSettings({
          printer_status_check: checkbox.checked,
          printer_status_timeout_ms: parseInt(timeoutInput.value, 10) || 2000,
        })
        printerSaveStatus.textContent = 'Printer settings saved.'
        printerSaveStatus.className = 'status-msg success'
      } catch (err) {
        printerSaveStatus.textContent = (err as Error).message
        printerSaveStatus.className = 'status-msg error'
      } finally {
        printerSaveStatus.hidden = false
        btnSavePrinter.disabled = false
      }
    })
  }

  const updatesSettingsEl = root.querySelector<HTMLDivElement>('#updates-settings')!

  function renderUpdatesSettings(s: Record<string, unknown>): void {
    const checkEnabled = s.update_check_enabled !== false

    updatesSettingsEl.innerHTML = `
      <label class="setting-row">
        <input type="checkbox" id="update-check-enabled" ${checkEnabled ? 'checked' : ''} />
        <span class="setting-row-label">Check for updates</span>
        <span class="setting-hint">Check GitHub for new releases on page load</span>
      </label>
      <div class="setting-actions">
        <button id="btn-save-updates" class="btn-primary">Save</button>
      </div>
      <div id="updates-save-status" class="status-msg" hidden></div>
    `

    const checkbox = updatesSettingsEl.querySelector<HTMLInputElement>('#update-check-enabled')!
    const btnSaveUpdates = updatesSettingsEl.querySelector<HTMLButtonElement>('#btn-save-updates')!
    const updatesSaveStatus = updatesSettingsEl.querySelector<HTMLDivElement>('#updates-save-status')!

    btnSaveUpdates.addEventListener('click', async () => {
      btnSaveUpdates.disabled = true
      updatesSaveStatus.hidden = true
      try {
        await putSettings({ update_check_enabled: checkbox.checked })
        updatesSaveStatus.textContent = 'Update settings saved.'
        updatesSaveStatus.className = 'status-msg success'
      } catch (err) {
        updatesSaveStatus.textContent = (err as Error).message
        updatesSaveStatus.className = 'status-msg error'
      } finally {
        updatesSaveStatus.hidden = false
        btnSaveUpdates.disabled = false
      }
    })
  }

  getSettings()
    .then(s => { renderForm(s); renderPrinterSettings(s); renderUpdatesSettings(s) })
    .catch(err => showStatus((err as Error).message, 'error'))
}
