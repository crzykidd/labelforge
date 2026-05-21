export const TOKEN_KEY = 'labelforge_token';
function getToken() {
    return localStorage.getItem(TOKEN_KEY) ?? '';
}
async function apiFetch(path, options = {}) {
    const res = await fetch(path, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${getToken()}`,
            ...options.headers,
        },
    });
    if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
            const body = await res.json();
            if (body.detail)
                detail = String(body.detail);
        }
        catch { /* use status fallback */ }
        throw new Error(detail);
    }
    return res.json();
}
export function getLabels() {
    return apiFetch('/api/labels');
}
export function getFonts() {
    return apiFetch('/api/fonts');
}
export function quickPrint(req) {
    return apiFetch('/api/print/quick', {
        method: 'POST',
        body: JSON.stringify(req),
    });
}
export async function previewQuick(req) {
    const res = await fetch('/api/preview/quick', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify(req),
    });
    if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
            const body = await res.json();
            if (body.detail)
                detail = String(body.detail);
        }
        catch { /* use status fallback */ }
        throw new Error(detail);
    }
    return res.blob();
}
export function listTemplates() {
    return apiFetch('/api/templates');
}
export function getTemplate(name) {
    return apiFetch(`/api/templates/${encodeURIComponent(name)}`);
}
export function createTemplate(body) {
    return apiFetch('/api/templates', {
        method: 'POST',
        body: JSON.stringify(body),
    });
}
export function updateTemplate(name, body) {
    return apiFetch(`/api/templates/${encodeURIComponent(name)}`, {
        method: 'PUT',
        body: JSON.stringify(body),
    });
}
export function deleteTemplate(name) {
    return apiFetch(`/api/templates/${encodeURIComponent(name)}`, { method: 'DELETE' });
}
export async function previewTemplate(name, fields) {
    const res = await fetch(`/api/preview/${encodeURIComponent(name)}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({ fields }),
    });
    if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
            const body = await res.json();
            if (body.detail)
                detail = String(body.detail);
        }
        catch { /* use status fallback */ }
        throw new Error(detail);
    }
    return res.blob();
}
export function getSettings() {
    return apiFetch('/api/settings');
}
export function putSettings(partial) {
    return apiFetch('/api/settings', {
        method: 'PUT',
        body: JSON.stringify(partial),
    });
}
