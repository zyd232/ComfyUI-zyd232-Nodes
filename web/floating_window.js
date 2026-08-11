/**
 * Generic floating window for ComfyUI nodes.
 *
 * This module provides a reusable DOM overlay window that "floats" relative to a
 * ComfyUI node. It is designed to be shared by any node that needs a detached
 * panel (e.g. a streaming-text viewer, an image preview, a settings popup, ...).
 *
 * Features (all generic, no node-specific logic):
 *   - Node-relative positioning: the window keeps a fixed offset (in graph
 *     coordinates) from the node's top-left corner, so it follows the node when
 *     it is moved or the canvas is zoomed/panned.
 *   - Draggable: drag the title bar to move the window; the relative offset is
 *     updated so the window keeps its position relative to the node.
 *   - Resizable: 8 resize handles (n/s/e/w/ne/nw/se/sw) on the edges/corners.
 *     Resizing from the N/W edges also shifts the anchor, so the relative offset
 *     is refreshed accordingly.
 *   - Collapsible: collapse to just the title bar (no residual body height).
 *   - Persistence: geometry (relative offset + size) is stored in
 *     `node.properties` so it is saved with the workflow and restored on load.
 */

import { app } from "../../../scripts/app.js";

// ============ Constants ============

const DEFAULT_TITLE_HEIGHT = 28;
const DEFAULT_MIN_WIDTH = 200;
const DEFAULT_MIN_HEIGHT = 120;
const RESIZE_DIRS = ["n", "s", "e", "w", "ne", "nw", "se", "sw"];

// ============ Internal registry ============

// Every live floating window, keyed by node. Used by the global position-sync
// loop to keep all windows following their nodes on every canvas redraw.
const liveWindows = new Map();

let positionSyncInstalled = false;

// ============ Small helpers ============

/**
 * Chain a callback onto an existing object method without clobbering it.
 */
function chainCallback(object, property, callback) {
    if (object == null) return;
    if (property in object) {
        const orig = object[property];
        object[property] = function (...args) {
            const r = orig.apply(this, args);
            callback.apply(this, args);
            return r;
        };
    } else {
        object[property] = callback;
    }
}

/**
 * Pointer-capture drag helper. Filters moves by pointerId, auto-removes its
 */
function dragPointer(e, target, onMove, onEnd) {
    try { target.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ }
    const move = (me) => { if (me.pointerId === e.pointerId) onMove(me); };
    const end = (ue) => {
        if (ue.pointerId !== e.pointerId) return;
        target.removeEventListener("pointermove", move);
        target.removeEventListener("pointerup", end);
        target.removeEventListener("pointercancel", end);
        if (onEnd) onEnd(ue);
    };
    target.addEventListener("pointermove", move);
    target.addEventListener("pointerup", end);
    target.addEventListener("pointercancel", end);
}

// ============ Position sync (global) ============

/**
 * Compute the screen position of a window given its node-relative offset.
 * The offset is in graph coordinates relative to the node's top-left corner.
 */
function applyWindowTransform(win) {
    const node = win.node;
    const panel = win.panel;
    const canvas = app.canvas;
    if (!canvas || !panel || !node.graph) return;

    const geom = win.getGeometry();
    if (!geom) return;

    const ds = canvas.ds;
    const scale = ds.scale;
    const rect = canvas.canvas.getBoundingClientRect();

    // baseLeft/baseTop = screen position of the node's top-left corner.
    const baseLeft = rect.left + (node.pos[0] + ds.offset[0]) * scale;
    const baseTop = rect.top + (node.pos[1] + ds.offset[1]) * scale;

    // The window is positioned at (node.pos + geom.offset) in graph coords,
    // scaled to screen space. We use a transform so the window content scales
    // with the canvas zoom (matching the original streaming_text behavior).
    //
    // IMPORTANT: When the canvas is at 100% zoom (scale === 1) we position the
    // panel with plain left/top instead of a transform. A transform (even
    // scale(1)) creates a new rendering context that can suppress the native
    // scrollbar of inner overflow:auto containers in some browsers. Using
    // left/top at scale 1 keeps the scrollbar fully visible and interactive.
    const left = baseLeft + geom.x * scale;
    const top = baseTop + geom.y * scale;
    if (Math.abs(scale - 1) < 1e-6) {
        const sig = `p:${left},${top}`;
        if (win._sig !== sig) {
            panel.style.position = "fixed";
            panel.style.left = left + "px";
            panel.style.top = top + "px";
            panel.style.transform = "none";
            win._sig = sig;
        }
    } else {
        const tf = `translate(${left}px,${top}px) scale(${scale})`;
        if (win._sig !== tf) {
            panel.style.position = "fixed";
            panel.style.transformOrigin = "top left";
            panel.style.transform = tf;
            // Clear any left/top left over from the scale===1 branch so they
            // don't double-offset the transform.
            panel.style.left = "0px";
            panel.style.top = "0px";
            win._sig = tf;
        }
    }
}

function syncAllWindows() {
    for (const win of liveWindows.values()) {
        if (!win.panel || !win.panel.isConnected) continue;
        applyWindowTransform(win);
    }
}

function installPositionSync() {
    if (positionSyncInstalled) return;
    positionSyncInstalled = true;
    chainCallback(app.canvas, "onDrawForeground", () => {
        syncAllWindows();
    });
}

// ============ Floating window controller ============

/**
 * Create a floating window attached to a node.
 *
 * @param {object} node - The ComfyUI node the window follows.
 * @param {object} options
 * @param {string} options.title - Title bar text.
 * @param {HTMLElement|Function} options.content - Body content element, or a
 *   function `(panel, win) => HTMLElement` that builds it.
 * @param {object} [options.defaultSize] - Default {w, h} when no saved geometry.
 * @param {object} [options.defaultOffset] - Default {x, y} relative offset.
 * @param {string} [options.storageKey] - Key under node.properties to persist
 *   geometry. Defaults to "zyd232Float".
 * @param {number} [options.titleHeight] - Title bar height in px.
 * @param {number} [options.minWidth] - Minimum window width.
 * @param {number} [options.minHeight] - Minimum window height.
 * @param {Function} [options.onCollapse] - Called with (collapsed) after toggle.
 * @returns {object} The window controller.
 */
export function createFloatingWindow(node, options = {}) {
    const storageKey = options.storageKey || "zyd232Float";
    const titleHeight = options.titleHeight || DEFAULT_TITLE_HEIGHT;
    const minWidth = options.minWidth || DEFAULT_MIN_WIDTH;
    const minHeight = options.minHeight || DEFAULT_MIN_HEIGHT;

    // ---- Geometry (persisted in node.properties) ----
    function readGeom() {
        const g = node.properties && node.properties[storageKey];
        if (g && typeof g.x === "number" && typeof g.y === "number") {
            return {
                x: g.x,
                y: g.y,
                w: typeof g.w === "number" ? g.w : (options.defaultSize?.w || DEFAULT_MIN_WIDTH),
                h: typeof g.h === "number" ? g.h : (options.defaultSize?.h || DEFAULT_MIN_HEIGHT),
            };
        }
        return {
            x: options.defaultOffset?.x ?? 0,
            y: options.defaultOffset?.y ?? 0,
            w: options.defaultSize?.w || DEFAULT_MIN_WIDTH,
            h: options.defaultSize?.h || DEFAULT_MIN_HEIGHT,
        };
    }

    function writeGeom(geom) {
        if (!node.properties) node.properties = {};
        node.properties[storageKey] = {
            x: Math.round(geom.x),
            y: Math.round(geom.y),
            w: Math.round(geom.w),
            h: Math.round(geom.h),
        };
    }

    // ---- DOM construction ----
    const panel = document.createElement("div");
    panel.className = "zyd232-float-window";
    Object.assign(panel.style, {
        position: "fixed",
        display: "flex",
        flexDirection: "column",
        backgroundColor: "#1e1e1e",
        border: "1px solid #3a3a3a",
        borderRadius: "6px",
        boxShadow: "0 0 10px rgba(0,0,0,0.6)",
        zIndex: "100",
        overflow: "hidden",
        transformOrigin: "0 0",
        fontFamily: "sans-serif",
        color: "#e0e0e0",
        minWidth: minWidth + "px",
        minHeight: minHeight + "px",
    });

    // Title bar (draggable)
    const titleBar = document.createElement("div");
    titleBar.className = "zyd232-float-titlebar";
    Object.assign(titleBar.style, {
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        height: titleHeight + "px",
        padding: "0 8px",
        backgroundColor: "#2a2a2a",
        borderBottom: "1px solid #3a3a3a",
        flexShrink: "0",
        userSelect: "none",
        cursor: "move",
    });

    const title = document.createElement("span");
    title.textContent = options.title || "";
    title.style.fontSize = "12px";
    title.style.fontWeight = "bold";
    title.style.color = "#ccc";
    title.style.flex = "1";
    title.style.overflow = "hidden";
    title.style.whiteSpace = "nowrap";
    title.style.textOverflow = "ellipsis";

    const btnRow = document.createElement("div");
    Object.assign(btnRow.style, {
        display: "flex",
        alignItems: "center",
        gap: "4px",
        flexShrink: "0",
    });

    titleBar.append(title, btnRow);
    panel.appendChild(titleBar);

    // Body (content area)
    const body = document.createElement("div");
    body.className = "zyd232-float-body";
    Object.assign(body.style, {
        display: "flex",
        flexDirection: "column",
        flex: "1",
        minHeight: "0",
        overflow: "hidden",
    });
    panel.appendChild(body);

    // Resize handles
    const handles = {};
    for (const dir of RESIZE_DIRS) {
        const h = document.createElement("div");
        h.className = "zyd232-float-rsz zyd232-float-rsz-" + dir;
        Object.assign(h.style, {
            position: "absolute",
            zIndex: "20",
            touchAction: "none",
        });
        // Edge/corner geometry + cursor
        if (dir === "n") { h.style.top = "0"; h.style.left = "11px"; h.style.right = "11px"; h.style.height = "6px"; h.style.cursor = "ns-resize"; }
        else if (dir === "s") { h.style.bottom = "0"; h.style.left = "11px"; h.style.right = "11px"; h.style.height = "6px"; h.style.cursor = "ns-resize"; }
        else if (dir === "e") { h.style.right = "0"; h.style.top = "11px"; h.style.bottom = "11px"; h.style.width = "6px"; h.style.cursor = "ew-resize"; }
        else if (dir === "w") { h.style.left = "0"; h.style.top = "11px"; h.style.bottom = "11px"; h.style.width = "6px"; h.style.cursor = "ew-resize"; }
        else if (dir === "ne") { h.style.top = "0"; h.style.right = "0"; h.style.width = "12px"; h.style.height = "12px"; h.style.cursor = "nesw-resize"; }
        else if (dir === "nw") { h.style.top = "0"; h.style.left = "0"; h.style.width = "12px"; h.style.height = "12px"; h.style.cursor = "nwse-resize"; }
        else if (dir === "se") { h.style.bottom = "0"; h.style.right = "0"; h.style.width = "12px"; h.style.height = "12px"; h.style.cursor = "nwse-resize"; }
        else if (dir === "sw") { h.style.bottom = "0"; h.style.left = "0"; h.style.width = "12px"; h.style.height = "12px"; h.style.cursor = "nesw-resize"; }
        h.addEventListener("pointerdown", (e) => startResize(e, dir));
        panel.appendChild(h);
        handles[dir] = h;
    }

    // ---- Controller state ----
    const win = {
        node,
        panel,
        titleBar,
        btnRow,
        body,
        handles,
        storageKey,
        titleHeight,
        minWidth,
        minHeight,
        _sig: "",
        _collapsed: false,
        _geom: readGeom(),
        _onCollapse: options.onCollapse || null,
    };

    // ---- Geometry accessors ----
    win.getGeometry = () => win._geom;
    win.setGeometry = (geom) => {
        win._geom = { x: geom.x, y: geom.y, w: geom.w, h: geom.h };
        panel.style.width = geom.w + "px";
        panel.style.height = geom.h + "px";
        win._sig = "";
        applyWindowTransform(win);
        writeGeom(win._geom);
    };

    // ---- Collapse ----
    win.isCollapsed = () => win._collapsed;
    win.setCollapsed = (collapsed) => {
        win._collapsed = !!collapsed;
        panel.classList.toggle("zyd232-float-collapsed", win._collapsed);
        if (win._collapsed) {
            // Collapse to just the title bar: hide the body and drop the
            // min-height so no residual empty space remains below the title.
            body.style.display = "none";
            panel.style.minHeight = "0px";
            panel.style.height = titleHeight + "px";
        } else {
            body.style.display = "flex";
            panel.style.minHeight = minHeight + "px";
            panel.style.height = win._geom.h + "px";
        }
        if (win._onCollapse) win._onCollapse(win._collapsed);
    };
    win.toggleCollapsed = () => win.setCollapsed(!win._collapsed);

    // ---- Drag (title bar) ----
    function startDrag(e) {
        if (e.button !== 0) return;
        e.preventDefault();
        const sx = e.clientX, sy = e.clientY;
        const gx0 = win._geom.x, gy0 = win._geom.y;
        const scale = app.canvas?.ds?.scale || 1;
        dragPointer(e, titleBar, (me) => {
            // Update the node-relative offset (graph coords) so the window
            // keeps its position relative to the node.
            win._geom.x = gx0 + (me.clientX - sx) / scale;
            win._geom.y = gy0 + (me.clientY - sy) / scale;
            win._sig = "";
            applyWindowTransform(win);
        }, () => {
            writeGeom(win._geom);
            flushChange();
        });
    }
    titleBar.addEventListener("pointerdown", (e) => {
        // Ignore drags that start on a button inside the title bar.
        if (e.target.closest("button")) return;
        startDrag(e);
    });

    // ---- Resize (8 directions) ----
    function startResize(e, dir) {
        if (e.button !== 0) return;
        e.preventDefault();
        e.stopPropagation();
        const scale = app.canvas?.ds?.scale || 1;
        const sx = e.clientX, sy = e.clientY;
        const w0 = panel.offsetWidth, h0 = panel.offsetHeight;
        const gx0 = win._geom.x, gy0 = win._geom.y;
        dragPointer(e, e.currentTarget, (me) => {
            const dx = (me.clientX - sx) / scale;
            const dy = (me.clientY - sy) / scale;
            let w = w0, h = h0, gx = gx0, gy = gy0;
            if (dir.indexOf("e") >= 0) w = w0 + dx;
            if (dir.indexOf("s") >= 0) h = h0 + dy;
            if (dir.indexOf("w") >= 0) { w = w0 - dx; gx = gx0 + dx; }
            if (dir.indexOf("n") >= 0) { h = h0 - dy; gy = gy0 + dy; }
            if (w < minWidth) { if (dir.indexOf("w") >= 0) gx -= (minWidth - w); w = minWidth; }
            if (h < minHeight) { if (dir.indexOf("n") >= 0) gy -= (minHeight - h); h = minHeight; }
            win._geom.w = w;
            win._geom.h = h;
            win._geom.x = gx;
            win._geom.y = gy;
            panel.style.width = Math.round(w) + "px";
            panel.style.height = Math.round(h) + "px";
            win._sig = "";
            applyWindowTransform(win);
        }, () => {
            writeGeom(win._geom);
            flushChange();
        });
    }

    // ---- Persistence helpers ----
    function flushChange() {
        // Nudge ComfyUI's change tracker (it snapshots on mouseup, which our
        // preventDefault'd drags suppress).
        try { window.dispatchEvent(new MouseEvent("mouseup")); } catch (err) { /* ignore */ }
    }

    // ---- Content ----
    if (typeof options.content === "function") {
        options.content(body, win);
    } else if (options.content) {
        body.appendChild(options.content);
    }

    // ---- Initial geometry ----
    panel.style.width = win._geom.w + "px";
    panel.style.height = win._geom.h + "px";

    // ---- Attach & register ----
    document.body.appendChild(panel);
    liveWindows.set(node, win);
    installPositionSync();
    applyWindowTransform(win);

    // ---- Lifecycle: restore on load, clean up on remove ----
    chainCallback(node, "onConfigure", function () {
        // Re-read persisted geometry (workflow just loaded / pasted).
        win._geom = readGeom();
        panel.style.width = win._geom.w + "px";
        panel.style.height = win._geom.h + "px";
        win._sig = "";
        applyWindowTransform(win);
    });

    chainCallback(node, "onRemoved", function () {
        if (panel.parentNode) panel.parentNode.removeChild(panel);
        liveWindows.delete(node);
    });

    return win;
}

// ============ Convenience: add a button to a window's title bar ============

/**
 * Create a small title-bar button (used by consumers to add collapse/close/etc).
 * @param {string} label - Button text.
 * @param {string} title - Tooltip.
 * @param {Function} onClick - Click handler.
 * @returns {HTMLButtonElement}
 */
export function makeTitleButton(label, title, onClick) {
    const btn = document.createElement("button");
    btn.textContent = label;
    btn.title = title;
    Object.assign(btn.style, {
        width: "24px",
        height: "20px",
        fontSize: "11px",
        lineHeight: "1",
        padding: "0",
        border: "1px solid #555",
        borderRadius: "4px",
        backgroundColor: "#2b2b2b",
        color: "#ddd",
        cursor: "pointer",
    });
    btn.addEventListener("mouseenter", () => { btn.style.backgroundColor = "#3a3a3a"; });
    btn.addEventListener("mouseleave", () => { btn.style.backgroundColor = "#2b2b2b"; });
    btn.addEventListener("click", onClick);
    return btn;
}
