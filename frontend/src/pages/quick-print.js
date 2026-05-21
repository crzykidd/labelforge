import { getFonts, getLabels, getSettings, previewQuick, quickPrint, TOKEN_KEY } from '../api';
const FORM_FACTOR_LABEL = {
    1: 'Die-cut',
    2: 'Continuous',
    3: 'Round',
    4: 'P-touch Continuous',
};
const FF_ORDER = [2, 1, 3, 4];
function esc(s) {
    return s
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}
export function mountQuickPrint(root) {
    if (!localStorage.getItem(TOKEN_KEY)) {
        renderTokenGate(root);
    }
    else {
        renderForm(root);
    }
}
function renderTokenGate(root) {
    root.innerHTML = `
    <div class="token-gate">
      <h2>LabelForge</h2>
      <p>Enter your API token to continue.</p>
      <input id="token-input" type="password" placeholder="API token" autocomplete="current-password" />
      <button id="token-save">Save token</button>
    </div>
  `;
    const input = root.querySelector('#token-input');
    const btn = root.querySelector('#token-save');
    function save() {
        const val = input.value.trim();
        if (!val)
            return;
        localStorage.setItem(TOKEN_KEY, val);
        renderForm(root);
    }
    btn.addEventListener('click', save);
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter')
        save(); });
}
function renderForm(root) {
    root.innerHTML = `
    <div class="quick-print">
      <h2>Quick Print</h2>
      <div id="status-msg" class="status-msg" hidden></div>
      <form id="print-form" autocomplete="off">
        <div>
          <label for="text">Text</label>
          <textarea id="text" rows="4" required></textarea>
        </div>

        <div>
          <label for="font">Font</label>
          <select id="font"><option value="">Loading…</option></select>
        </div>

        <div>
          <label for="font-size">Font size</label>
          <input id="font-size" type="number" min="6" max="200" value="48" />
        </div>

        <div>
          <label for="label-media">Label media</label>
          <select id="label-media"><option value="">Loading…</option></select>
        </div>

        <div>
          <label>Style</label>
          <div class="checkboxes">
            <label><input id="bold" type="checkbox" /> Bold</label>
            <label><input id="italic" type="checkbox" /> Italic</label>
          </div>
        </div>

        <div>
          <label>Alignment</label>
          <div class="radio-group">
            <label><input type="radio" name="alignment" value="left" checked /> Left</label>
            <label><input type="radio" name="alignment" value="center" /> Center</label>
            <label><input type="radio" name="alignment" value="right" /> Right</label>
          </div>
        </div>

        <div>
          <label>Orientation</label>
          <div class="radio-group">
            <label><input type="radio" name="orientation" value="standard" checked /> Standard</label>
            <label><input type="radio" name="orientation" value="rotated" /> Rotated</label>
          </div>
        </div>

        <div class="actions">
          <button type="button" id="btn-preview" disabled>Preview</button>
          <button type="submit" id="btn-print" disabled>Print</button>
        </div>
      </form>
      <div id="preview-area" class="preview-area" hidden>
        <img id="preview-img" alt="Label preview" />
      </div>
    </div>
  `;
    const form = root.querySelector('#print-form');
    const textarea = root.querySelector('#text');
    const fontSelect = root.querySelector('#font');
    const fontSizeInput = root.querySelector('#font-size');
    const labelSelect = root.querySelector('#label-media');
    const boldCheck = root.querySelector('#bold');
    const italicCheck = root.querySelector('#italic');
    const btnPreview = root.querySelector('#btn-preview');
    const btnPrint = root.querySelector('#btn-print');
    const statusMsg = root.querySelector('#status-msg');
    const previewArea = root.querySelector('#preview-area');
    const previewImg = root.querySelector('#preview-img');
    let previewObjectUrl = null;
    function showStatus(msg, kind) {
        statusMsg.textContent = msg;
        statusMsg.className = `status-msg ${kind}`;
        statusMsg.hidden = false;
    }
    function hideStatus() {
        statusMsg.hidden = true;
    }
    function updateButtons() {
        const empty = textarea.value.trim() === '';
        btnPrint.disabled = empty;
        btnPreview.disabled = empty;
    }
    function buildRequest() {
        const alignment = (form.querySelector('input[name="alignment"]:checked')?.value ?? 'left');
        const orientation = (form.querySelector('input[name="orientation"]:checked')?.value ?? 'standard');
        return {
            text: textarea.value,
            font: fontSelect.value,
            font_size: parseInt(fontSizeInput.value, 10),
            alignment,
            orientation,
            label_media: labelSelect.value,
            bold: boldCheck.checked,
            italic: italicCheck.checked,
        };
    }
    textarea.addEventListener('input', updateButtons);
    btnPreview.addEventListener('click', async () => {
        btnPreview.disabled = true;
        hideStatus();
        try {
            const blob = await previewQuick(buildRequest());
            if (previewObjectUrl)
                URL.revokeObjectURL(previewObjectUrl);
            previewObjectUrl = URL.createObjectURL(blob);
            previewImg.src = previewObjectUrl;
            previewArea.hidden = false;
        }
        catch (err) {
            showStatus(err.message, 'error');
        }
        finally {
            updateButtons();
        }
    });
    // Load fonts, labels, and settings in parallel; settings failure is non-fatal
    Promise.all([
        getFonts(),
        getLabels(),
        getSettings().catch((err) => {
            console.warn('Failed to load settings:', err.message);
            return null;
        }),
    ]).then(([fonts, labels, sett]) => {
        // Populate fonts dropdown
        fontSelect.innerHTML = fonts
            .map(f => `<option value="${esc(f.name)}">${esc(f.name)}</option>`)
            .join('');
        // Group labels by form_factor
        const groups = new Map();
        for (const label of labels) {
            const ff = label.form_factor;
            if (!groups.has(ff))
                groups.set(ff, []);
            groups.get(ff).push(label);
        }
        for (const entries of groups.values()) {
            entries.sort((a, b) => a.display_name.localeCompare(b.display_name));
        }
        const allKeys = [...new Set([...FF_ORDER, ...groups.keys()])];
        labelSelect.innerHTML = allKeys
            .filter(k => groups.has(k))
            .map(k => {
            const groupLabel = FORM_FACTOR_LABEL[k] ?? 'Other';
            const opts = groups
                .get(k)
                .map(l => `<option value="${esc(l.id)}">${esc(l.display_name)}</option>`)
                .join('');
            return `<optgroup label="${esc(groupLabel)}">${opts}</optgroup>`;
        })
            .join('');
        // Restore form from settings; last_quick_print takes precedence over per-key defaults
        const lqp = (sett?.last_quick_print ?? null);
        if (lqp) {
            fontSelect.value = lqp.font ?? String(sett?.default_font ?? 'DejaVuSans');
            fontSizeInput.value = String(lqp.font_size ?? sett?.default_font_size ?? 48);
            labelSelect.value = String(lqp.label_media ?? sett?.default_label_media ?? '62');
            boldCheck.checked = lqp.bold ?? false;
            italicCheck.checked = lqp.italic ?? false;
            const aRadio = form.querySelector(`input[name="alignment"][value="${lqp.alignment ?? 'left'}"]`);
            if (aRadio)
                aRadio.checked = true;
            const oRadio = form.querySelector(`input[name="orientation"][value="${lqp.orientation ?? 'standard'}"]`);
            if (oRadio)
                oRadio.checked = true;
        }
        else {
            const defFont = String(sett?.default_font ?? 'DejaVuSans');
            const defSize = String(sett?.default_font_size ?? 48);
            const defMedia = String(sett?.default_label_media ?? '62');
            const defOrientation = String(sett?.default_orientation ?? 'standard');
            fontSelect.value = defFont;
            fontSizeInput.value = defSize;
            labelSelect.value = defMedia;
            const oRadio = form.querySelector(`input[name="orientation"][value="${defOrientation}"]`);
            if (oRadio)
                oRadio.checked = true;
        }
    }).catch((err) => {
        showStatus(`Failed to load form data: ${err.message}`, 'error');
    });
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        btnPrint.disabled = true;
        hideStatus();
        try {
            const result = await quickPrint(buildRequest());
            // "sent" = transmitted to printer network backend, not confirmed printed
            showStatus(`Sent — job #${result.job_id} (status: ${result.status}). "Sent" means the job was transmitted to the printer; delivery is not confirmed.`, 'success');
        }
        catch (err) {
            showStatus(err.message, 'error');
        }
        finally {
            updateButtons();
        }
    });
}
