/**
 * Generic button utilities for ComfyUI custom widgets.
 *
 * These helpers create buttons using ComfyUI's DEFAULT button widget
 * implementation (node.addWidget("button", ...)), so rendering, hit-testing
 * and sizing are all handled by the framework (same approach as rgthree's
 * Seed node). The returned widgets are normal ComfyUI button widgets that can
 * be inserted anywhere in node.widgets.
 */

/**
 * Create a full-width single button widget using ComfyUI's default button
 * implementation.
 *
 * @param {object} node - The ComfyUI node instance to attach the button to.
 * @param {string} label - Button text label.
 * @param {Function} onClick - Callback invoked on button click.
 * @param {Object} [options] - Optional configuration.
 * @param {string} [options.name] - Widget name (default: "button_" + random id).
 * @returns {object} The created ComfyUI button widget.
 */
export function createFullWidthButton(node, label, onClick, options = {}) {
    return node.addWidget(
        "button",
        label,
        "",
        onClick,
        { serialize: false, ...(options.name ? { name: options.name } : {}) }
    );
}

/**
 * Create one ComfyUI default button widget per label.
 *
 * Note: unlike the previous custom implementation (which drew multiple buttons
 * side-by-side in a single row), each button here is a separate default widget
 * and therefore occupies its own row. Functionally equivalent, but visually the
 * buttons stack vertically.
 *
 * @param {object} node - The ComfyUI node instance to attach the buttons to.
 * @param {string[]} labels - Array of button text labels.
 * @param {Function[]} onClickHandlers - Array of click callbacks (one per label).
 * @param {Object} [options] - Optional configuration.
 * @param {string} [options.name] - Base widget name (default: "button_row_" + random id).
 * @returns {object[]} Array of created ComfyUI button widgets (one per label).
 */
export function createMultiButtonRow(node, labels, onClickHandlers, options = {}) {
    const baseName = options.name || `button_row_${Math.random().toString(36).slice(2, 8)}`;
    return labels.map((label, i) => {
        return node.addWidget(
            "button",
            label,
            "",
            onClickHandlers[i],
            { serialize: false, name: `${baseName}_${i}` }
        );
    });
}
