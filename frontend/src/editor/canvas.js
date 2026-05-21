import { Canvas, FabricObject, IText } from 'fabric';
export const CUSTOM_PROPS = ['labelforge_raw_content'];
// Register the custom prop so canvas.toJSON() includes it on every object automatically.
FabricObject.customProperties.push('labelforge_raw_content');
/** Create a Fabric Canvas sized to label pixels, displayed scaled to fit the container. */
export function initCanvas(el, labelW, labelH, containerW) {
    const maxDisplayH = 600;
    const scale = Math.min(1, (containerW - 48) / labelW, maxDisplayH / labelH);
    const displayW = Math.round(labelW * scale);
    const displayH = Math.round(labelH * scale);
    const canvas = new Canvas(el, {
        backgroundColor: '#ffffff',
        selection: true,
    });
    canvas.setDimensions({ width: displayW, height: displayH });
    canvas.setZoom(scale);
    // Sync labelforge_raw_content whenever text is edited inline.
    // text:changed target is IText — no manual annotation needed.
    canvas.on('text:changed', (e) => {
        e.target.set('labelforge_raw_content', e.target.text ?? '');
    });
    return { canvas, scale };
}
export function addTextElement(canvas, defaultFont) {
    const vp = canvas.viewportTransform ?? [1, 0, 0, 1, 0, 0];
    const scale = vp[0];
    const canvasVirtualW = (canvas.width ?? 400) / scale;
    const canvasVirtualH = (canvas.height ?? 200) / scale;
    const text = new IText('Text', {
        left: Math.round(canvasVirtualW * 0.05),
        top: Math.round(canvasVirtualH * 0.05),
        fontFamily: defaultFont,
        fontSize: 48,
        fill: '#000000',
    });
    text.set('labelforge_raw_content', 'Text');
    // Keep raw content in sync when text changes
    text.on('changed', () => {
        text.set('labelforge_raw_content', text.text ?? '');
    });
    canvas.add(text);
    canvas.setActiveObject(text);
    canvas.renderAll();
}
export function deleteSelected(canvas) {
    const active = canvas.getActiveObjects();
    if (active.length === 0)
        return;
    active.forEach(obj => canvas.remove(obj));
    canvas.discardActiveObject();
    canvas.renderAll();
}
export function getCanvasJSON(canvas) {
    // customProperties registered above ensures labelforge_raw_content is included.
    return canvas.toJSON();
}
export async function loadCanvasJSON(canvas, json) {
    await canvas.loadFromJSON(json);
    // Re-attach raw content sync to each loaded text object
    canvas.getObjects().forEach(obj => {
        if (obj.type === 'i-text' || obj.type === 'text' || obj.type === 'textbox') {
            const t = obj;
            t.on('changed', () => {
                t.set('labelforge_raw_content', t.text ?? '');
            });
        }
    });
    canvas.renderAll();
}
