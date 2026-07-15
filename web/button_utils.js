/**
 * Generic button utilities for ComfyUI custom widgets.
 * Provides shared styles, drawing helpers, proportional width calculation,
 * and factory functions to create full-width or multi-button row widgets.
 */

import { app } from "../../../scripts/app.js";

// ============ Style Constants ============

export const BTN_NORMAL_BG = "#2b2b2b";
export const BTN_PRESSED_BG = "#383838";
export const BTN_BORDER_COLOR = "#555555";
export const BTN_TEXT_COLOR = "#ddd";
export const BTN_PRESSED_TEXT = "#fff";
export const BTN_HEIGHT = 26;
export const OUTER_MARGIN = 15;
export const BTN_GAP = 4;
// Padding above/below buttons within the widget area
export const BTN_PAD_V = 4;

// ============ Drawing Helpers ============

/**
 * Draw a single pill-shaped button on the canvas.
 * @param {Canvas2DRenderingContext} ctx - Canvas context
 * @param {number} x - X position
 * @param {number} y - Y position
 * @param {number} w - Button width
 * @param {number} h - Button height
 * @param {string} label - Button text label
 * @param {boolean} isPressed - Whether the button is in pressed state
 */
export function drawSingleBtn(ctx, x, y, w, h, label, isPressed) {
    const r = Math.round(h / 2); // pill shape
    ctx.beginPath();
    ctx.roundRect(x, y, w, h, r);
    ctx.fillStyle = isPressed ? BTN_PRESSED_BG : BTN_NORMAL_BG;
    ctx.fill();
    ctx.strokeStyle = BTN_BORDER_COLOR;
    ctx.lineWidth = 1;
    ctx.stroke();

    ctx.fillStyle = isPressed ? BTN_PRESSED_TEXT : BTN_TEXT_COLOR;
    ctx.font = "12px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(label, x + w / 2, y + h / 2);
}

// ============ Width Calculation ============

/**
 * Calculate button widths proportional to their label text width.
 * Measures each label using ctx.measureText and distributes the available
 * totalWidth proportionally, respecting minimum widths (text + padding).
 *
 * @param {Canvas2DRenderingContext} ctx - Canvas context (must have font set)
 * @param {string[]} labels - Array of button label strings
 * @param {number} totalWidth - Total available width (excluding outer margins)
 * @param {number} gap - Gap between buttons in pixels
 * @param {number} [padding=12] - Single-side horizontal padding per button
 * @returns {number[]} Array of computed widths, one per label
 */
export function calculateProportionalButtonWidths(ctx, labels, totalWidth, gap, padding = 12) {
    const n = labels.length;
    if (n === 0) return [];
    if (n === 1) return [totalWidth];

    // Measure each label's text width
    const measuredWidths = labels.map(label => ctx.measureText(label).width);

    // Minimum width for each button = text width + padding on both sides
    const minWidths = measuredWidths.map(w => w + padding * 2);

    // Total gap space needed
    const totalGap = gap * (n - 1);

    // Sum of all minimum widths
    const sumMinWidths = minWidths.reduce((a, b) => a + b, 0);

    // Available width for proportional distribution (after removing gaps)
    const availableWidth = totalWidth - totalGap;

    if (availableWidth >= sumMinWidths) {
        // Extra space to distribute proportionally
        const extraSpace = availableWidth - sumMinWidths;
        return minWidths.map(minW => {
            const ratio = minW / sumMinWidths;
            return minW + extraSpace * ratio;
        });
    } else {
        // Not enough space — distribute proportionally based on minimum widths
        return minWidths.map(minW => {
            const ratio = minW / sumMinWidths;
            return availableWidth * ratio;
        });
    }
}

// ============ Hit Detection ============

/**
 * Determine which button was clicked based on dynamic button widths.
 *
 * @param {number} posX - Click X coordinate (relative to widget top-left)
 * @param {number[]} widths - Array of button widths
 * @param {number} gap - Gap between buttons
 * @param {number} margin - Left outer margin offset
 * @returns {number} Index of the clicked button, or -1 if none
 */
export function getButtonIndexAtPos(posX, widths, gap, margin) {
    let offset = posX - margin;
    for (let i = 0; i < widths.length; i++) {
        if (offset >= 0 && offset < widths[i]) {
            return i;
        }
        offset -= (widths[i] + gap);
    }
    return -1;
}

// ============ Factory Functions ============

/**
 * Create a full-width single button widget for ComfyUI nodes.
 * The button spans the entire available width (minus outer margins).
 *
 * @param {string} label - Button text label
 * @param {Function} onClick - Callback invoked on button click
 * @param {Object} [options] - Optional configuration
 * @param {string} [options.name] - Widget name (default: "button_" + random id)
 * @returns {{name, type, options, value, last_y, draw, mouse, computeSize}}
 */
export function createFullWidthButton(label, onClick, options = {}) {
    let pressed = false;

    return {
        name: options.name || `button_${Math.random().toString(36).slice(2, 8)}`,
        type: "custom",
        options: { serialize: false },
        value: "",
        last_y: 0,

        draw(ctx, self, width, posY, height) {
            const x = OUTER_MARGIN;
            const y = posY + BTN_PAD_V;
            const w = width - OUTER_MARGIN * 2;
            drawSingleBtn(ctx, x, y, w, BTN_HEIGHT, label, pressed);
        },

        mouse(event, pos, self) {
            if (event.type === "pointerdown") {
                pressed = true;
                app.canvas.dirty_canvas = true;
                return true;
            }

            if (event.type === "pointerup") {
                if (!pressed) return false;
                pressed = false;
                app.canvas.dirty_canvas = true;
                onClick();
                return true;
            }

            return false;
        },

        computeSize(width) {
            return [width, BTN_PAD_V + BTN_HEIGHT + BTN_PAD_V];
        }
    };
}

/**
 * Create a multi-button row widget where widths are proportional to label length.
 * Each button's width is calculated based on its label text width using
 * calculateProportionalButtonWidths. Widths are cached during draw so the
 * mouse handler can use them without needing a canvas context.
 *
 * @param {string[]} labels - Array of button text labels
 * @param {Function[]} onClickHandlers - Array of click callbacks (one per label)
 * @param {Object} [options] - Optional configuration
 * @param {string} [options.name] - Widget name
 * @returns {{name, type, options, value, last_y, draw, mouse, computeSize}}
 */
export function createMultiButtonRow(labels, onClickHandlers, options = {}) {
    let pressedIdx = -1;
    // Cache computed widths from the last draw call for hit detection in mouse handler
    let cachedWidths = [];

    return {
        name: options.name || `button_row_${Math.random().toString(36).slice(2, 8)}`,
        type: "custom",
        options: { serialize: false },
        value: "",
        last_y: 0,

        draw(ctx, self, width, posY, height) {
            const totalWidth = width - OUTER_MARGIN * 2;
            cachedWidths = calculateProportionalButtonWidths(ctx, labels, totalWidth, BTN_GAP);

            let x = OUTER_MARGIN;
            for (let i = 0; i < labels.length; i++) {
                const y = posY + BTN_PAD_V;
                drawSingleBtn(ctx, x, y, cachedWidths[i], BTN_HEIGHT, labels[i], pressedIdx === i);
                x += cachedWidths[i] + BTN_GAP;
            }
        },

        mouse(event, pos, self) {
            // Use cached widths from last draw call (avoids needing ctx in mouse handler)
            const btnWidths = cachedWidths.length === labels.length ? cachedWidths : [];

            if (event.type === "pointerdown") {
                if (btnWidths.length === 0) return false;
                const idx = getButtonIndexAtPos(pos[0], btnWidths, BTN_GAP, OUTER_MARGIN);
                if (idx >= 0 && idx < labels.length) {
                    pressedIdx = idx;
                    app.canvas.dirty_canvas = true;
                    return true;
                }
            }

            if (event.type === "pointerup") {
                if (pressedIdx === -1) return false;
                if (btnWidths.length === 0) {
                    pressedIdx = -1;
                    return false;
                }
                const idx = getButtonIndexAtPos(pos[0], btnWidths, BTN_GAP, OUTER_MARGIN);
                const wasPressed = pressedIdx;
                pressedIdx = -1;
                app.canvas.dirty_canvas = true;

                if (idx >= 0 && idx < labels.length && idx === wasPressed) {
                    onClickHandlers[idx]();
                    return true;
                }
            }

            return false;
        },

        computeSize(width) {
            return [width, BTN_PAD_V + BTN_HEIGHT + BTN_PAD_V];
        }
    };
}
