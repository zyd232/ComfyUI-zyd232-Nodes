/**
 * Streaming Text display panel for the zyd232 LLM Generator node.
 *
 * The LLM Generator node streams its output over WebSocket (event
 * "zyd232/stream_text"). This module creates a floating DOM panel to the right
 * of the node that displays the streamed text in real time.
 *
 * The panel is a DOM overlay created via the shared `createFloatingWindow`
 * helper (web/floating_window.js). That helper provides all the generic
 * floating-window capabilities: node-relative positioning (the panel keeps a
 * fixed offset from the node's top-left corner and follows it when moved or the
 * canvas is zoomed/panned), dragging by the title bar, resizing from 8 handles,
 * collapsing to just the title bar, and persisting geometry in the workflow.
 *
 * This module only owns the Streaming-Text-specific content: reasoning/output
 * rendering, status bar, auto-scroll, clear/copy, and WebSocket event handling.
 */

import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import { createFloatingWindow, makeTitleButton } from "./floating_window.js";
import { loadTranslations, $tSync } from "./i18n.js";

// ============ Panel Geometry ============
const PANEL_GAP = 12; // gap between the node's right edge and the panel
const DEFAULT_WIDTH = 360;
const DEFAULT_HEIGHT = 300;

// ============ Panel State (per node) ============
function getState(node) {
    if (!node.__zyd232Stream) {
        node.__zyd232Stream = {
            content: "",          // accumulated final text
            reasoning: "",        // accumulated reasoning text
            showReasoning: true,  // whether to render the reasoning block
            autoScroll: true,     // whether to keep scrolled to the bottom
            collapsed: false,     // whether the panel is collapsed
            streaming: false,     // whether a generation is in progress
            lastDone: false,      // whether the last generation finished
            locked: false,        // whether the displayed result is locked
            win: null,            // the floating-window controller
            textEl: null,         // the text content element
            statusEl: null,       // the status element
            lockBtn: null,        // the lock/unlock title-bar button
            clearBtn: null,       // the clear title-bar button
        };
    }
    return node.__zyd232Stream;
}

// ============ Locked-result widget helpers ============
// The locked result is persisted in three hidden widgets (use_locked,
// locked_text, locked_reasoning) declared in the backend schema. ComfyUI
// serializes their values into the workflow JSON and passes them to execute(),
// so a locked result survives save/load/share and lets the backend skip the LLM
// call on re-run. These helpers read/write those widgets on the node.

function getLockWidgets(node) {
    const find = (name) => node.widgets ? node.widgets.find(w => w.name === name) : null;
    return {
        useLocked: find("use_locked"),
        lockedText: find("locked_text"),
        lockedReasoning: find("locked_reasoning"),
    };
}

function isNodeLocked(node) {
    const w = getLockWidgets(node);
    return !!(w.useLocked && w.useLocked.value);
}

function setNodeLocked(node, locked, text, reasoning) {
    const w = getLockWidgets(node);
    if (w.useLocked) w.useLocked.value = !!locked;
    if (w.lockedText) w.lockedText.value = text ?? "";
    if (w.lockedReasoning) w.lockedReasoning.value = reasoning ?? "";
    // Mark the node dirty so ComfyUI persists the widget values into the
    // workflow JSON on save.
    if (node.setDirtyCanvas) node.setDirtyCanvas(true, true);
}

// Whether the node's "auto_lock" toggle is enabled. When enabled, the panel
// automatically locks the result as soon as a generation completes.
function isAutoLockEnabled(node) {
    const w = node.widgets ? node.widgets.find(w => w.name === "auto_lock") : null;
    return !!(w && w.value);
}

// Lock the current result: persist content/reasoning into the hidden locked_*
// widgets and update the panel UI (button icon, Clear availability). Shared by
// the manual 🔒 button and the auto_lock feature.
function lockResult(node) {
    const st = getState(node);
    st.locked = true;
    setNodeLocked(node, true, st.content, st.reasoning);
    if (st.lockBtn) {
        st.lockBtn.textContent = "🔒";
        st.lockBtn.title = $tSync("tooltip.unlock");
    }
    if (st.updateClearButton) st.updateClearButton();
    renderText(node);
}

// Unlock the current result: clear the locked state so the node re-runs the LLM.
function unlockResult(node) {
    const st = getState(node);
    st.locked = false;
    setNodeLocked(node, false, "", "");
    if (st.lockBtn) {
        st.lockBtn.textContent = "🔓";
        st.lockBtn.title = $tSync("tooltip.lock");
    }
    if (st.updateClearButton) st.updateClearButton();
    renderText(node);
}

// ============ DOM Panel Creation ============

function createPanel(node) {
    const st = getState(node);

    // Build the body content (status + text) first, then hand it to the shared
    // floating-window helper which wraps it with a draggable/resizable frame.
    const statusEl = document.createElement("div");
    Object.assign(statusEl.style, {
        padding: "4px 8px",
        fontSize: "10px",
        color: "#888",
        borderBottom: "1px solid #2a2a2a",
        flexShrink: "0",
    });
    statusEl.textContent = $tSync("status.idle");

    const textEl = document.createElement("div");
    Object.assign(textEl.style, {
        flex: "1",
        minHeight: "0", // allow the flex child to shrink so the scrollbar appears
        height: "100%", // give the scroll container an explicit height so overflowY:auto triggers reliably
        boxSizing: "border-box",
        overflowY: "auto",
        overflowX: "hidden",
        padding: "6px 8px",
        fontSize: "11px",
        // Use ComfyUI's default font variable so the text follows the
        // frontend's configured font (and theme) instead of a hardcoded one.
        fontFamily: "var(--font-family)",
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
        lineHeight: "1.4",
        color: "#e0e0e0",
        // Cross-browser scrollbar styling. The floating window is scaled with
        // transform: scale() (see floating_window.js), which can hide the native
        // scrollbar. Explicit scrollbar styles force a visible, fixed-width
        // scrollbar that survives the scale transform.
        scrollbarWidth: "thin",          // Firefox
        scrollbarColor: "#555 #2a2a2a",  // Firefox
    });

    // WebKit/Blink (Chrome, Edge, Safari) scrollbar styling. These pseudo-element
    // rules cannot be set via inline style, so inject a small <style> block once.
    if (!window.__zyd232ScrollbarStyleInjected) {
        window.__zyd232ScrollbarStyleInjected = true;
        const style = document.createElement("style");
        style.textContent = `
            .zyd232-float-window ::-webkit-scrollbar {
                width: 10px;
                height: 10px;
            }
            .zyd232-float-window ::-webkit-scrollbar-track {
                background: #2a2a2a;
            }
            .zyd232-float-window ::-webkit-scrollbar-thumb {
                background: #555;
                border-radius: 5px;
                border: 2px solid #2a2a2a;
            }
            .zyd232-float-window ::-webkit-scrollbar-thumb:hover {
                background: #666;
            }
            .zyd232-float-window ::-webkit-scrollbar-corner {
                background: #2a2a2a;
            }
        `;
        document.head.appendChild(style);
    }

    const body = document.createElement("div");
    Object.assign(body.style, {
        display: "flex",
        flexDirection: "column",
        flex: "1",
        minHeight: "0",
        overflow: "hidden",
    });
    body.append(statusEl, textEl);

    // Default offset: to the right of the node's top-left corner.
    const defaultOffset = {
        x: (node.size ? node.size[0] : 0) + PANEL_GAP,
        y: 0,
    };

    // Create the floating window. The shared helper wires up dragging, resizing,
    // collapsing, node-following, and workflow persistence.
    const win = createFloatingWindow(node, {
        title: $tSync("panel.title"),
        content: body,
        defaultSize: { w: DEFAULT_WIDTH, h: DEFAULT_HEIGHT },
        defaultOffset,
        storageKey: "zyd232StreamFloat",
        // Only show this window while the currently displayed graph is the same
        // graph that contains the node. This keeps the Streaming Text panel
        // attached to the interface where its parent LLM node lives: entering a
        // subgraph hides windows whose parent is on the main graph, and viewing
        // the main graph (or another subgraph) hides windows whose parent is
        // inside a subgraph.
        followGraph: true,
        onCollapse: (collapsed) => {
            st.collapsed = collapsed;
        },
    });

    // Add the Streaming-Text-specific title-bar buttons.
    const btnRow = win.btnRow;
    if (btnRow) {
        // Reasoning toggle button
        const reasoningBtn = makeTitleButton(st.showReasoning ? "🧠" : "🚫", $tSync("tooltip.toggleReasoning"), () => {
            st.showReasoning = !st.showReasoning;
            reasoningBtn.textContent = st.showReasoning ? "🧠" : "🚫";
            renderText(node);
        });

        // Lock / unlock button. The icon reflects the CURRENT lock state: 🔒
        // when locked, 🔓 when unlocked. Locking persists the current
        // content/reasoning into the hidden locked_* widgets so it is saved with
        // the workflow and the backend skips the LLM call on re-run. Unlocking
        // clears that state so the node re-runs the LLM.
        const lockBtn = makeTitleButton("🔓", $tSync("tooltip.lock"), () => {
            if (st.locked) {
                unlockResult(node);
            } else {
                lockResult(node);
            }
        });

        // Clear button. Disabled while the result is locked so the user cannot
        // accidentally wipe a locked result; they must unlock first.
        const clearBtn = makeTitleButton("✕", $tSync("tooltip.clear"), () => {
            st.content = "";
            st.reasoning = "";
            st.lastDone = false;
            st.streaming = false;
            renderText(node);
        });

        // Copy button
        const copyBtn = makeTitleButton("⧉", $tSync("tooltip.copy"), () => {
            const text = (st.showReasoning && st.reasoning ? st.reasoning + "\n\n" : "") + st.content;
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).catch(() => {});
            }
        });

        // Collapse button
        const collapseBtn = makeTitleButton("▼", $tSync("tooltip.collapse"), () => {
            win.toggleCollapsed();
            collapseBtn.textContent = win.isCollapsed() ? "▶" : "▼";
        });

        // Enable/disable the Clear button based on the locked state.
        const updateClearButton = () => {
            clearBtn.disabled = st.locked;
            clearBtn.style.opacity = st.locked ? "0.4" : "1";
            clearBtn.style.cursor = st.locked ? "not-allowed" : "pointer";
            clearBtn.title = st.locked ? $tSync("tooltip.clearLocked") : $tSync("tooltip.clear");
        };

        // Order: lock, reasoning, clear, copy, collapse — the lock button is the
        // first (leftmost) button in the title bar.
        btnRow.append(lockBtn, reasoningBtn, clearBtn, copyBtn, collapseBtn);

        // Store references for later use (onConfigure restore, etc.).
        st.lockBtn = lockBtn;
        st.clearBtn = clearBtn;
        st.updateClearButton = updateClearButton;
    }

    // Store references
    st.win = win;
    st.textEl = textEl;
    st.statusEl = statusEl;

    // Initialize the locked state from the persisted hidden widgets. This covers
    // the case where the panel is created after a workflow with a locked result
    // has already been loaded (the widgets already hold the locked values).
    syncLockedState(node);

    return win;
}

// ============ Locked-state sync ============

// Reflect the persisted hidden-widget state onto the panel UI (button icon,
// Clear-button availability, and the displayed content). Called on panel
// creation and on workflow load (onConfigure).
function syncLockedState(node) {
    const st = getState(node);
    const locked = isNodeLocked(node);
    st.locked = locked;

    if (st.lockBtn) {
        // The icon reflects the CURRENT lock state: 🔒 when locked, 🔓 when
        // unlocked.
        st.lockBtn.textContent = locked ? "🔒" : "🔓";
        st.lockBtn.title = locked ? $tSync("tooltip.unlock") : $tSync("tooltip.lock");
    }
    if (st.updateClearButton) st.updateClearButton();

    // When a locked result is loaded, restore it into the panel display so the
    // user sees exactly what will be returned (and what downstream nodes use).
    if (locked) {
        const w = getLockWidgets(node);
        st.content = (w.lockedText && w.lockedText.value) || "";
        st.reasoning = (w.lockedReasoning && w.lockedReasoning.value) || "";
        st.lastDone = true;
        st.streaming = false;
        renderText(node);
    }
}

// Extract the locked result directly from a node's configure data (the object
// passed to onConfigure, which carries widgets_values / widgets_values_named).
//
// Why not rely on the restored widget values? ComfyUI restores widget values
// from the widgets_values array by iterating node.widgets in order, skipping
// widgets whose serialize === false. But the button widgets added by this node
// (Save/Delete/Refresh/Stop) end up with serialize !== false after a reload,
// which shifts the array indices and prevents use_locked / locked_text /
// locked_reasoning from being restored correctly. Reading the configure data
// directly (by name when possible) is robust against that index shift.
function extractLockedFromConfig(config) {
    if (!config) return null;
    // Prefer widgets_values_named (keyed by widget name) when present.
    const named = config.widgets_values_named;
    if (named && typeof named === "object" && named.use_locked) {
        return {
            locked: true,
            text: named.locked_text || "",
            reasoning: named.locked_reasoning || "",
        };
    }
    // Fall back to widgets_values (array). use_locked / locked_text /
    // locked_reasoning are the last three schema widgets.
    if (Array.isArray(config.widgets_values) && config.widgets_values.length >= 3) {
        const wv = config.widgets_values;
        if (wv[wv.length - 3]) {
            return {
                locked: true,
                text: wv[wv.length - 2] || "",
                reasoning: wv[wv.length - 1] || "",
            };
        }
    }
    return null;
}

// Apply a locked result (from configure data) to the panel UI.
function applyLockedState(node, locked, text, reasoning) {
    const st = getState(node);
    st.locked = locked;
    st.content = text || "";
    st.reasoning = reasoning || "";
    st.lastDone = true;
    st.streaming = false;
    if (st.lockBtn) {
        st.lockBtn.textContent = locked ? "🔒" : "🔓";
        st.lockBtn.title = locked ? $tSync("tooltip.unlock") : $tSync("tooltip.lock");
    }
    if (st.updateClearButton) st.updateClearButton();
    renderText(node);
}

// ============ Rendering ============

function renderText(node) {
    const st = getState(node);
    if (!st.textEl) return;

    // Build the display using DOM nodes and textContent only. This guarantees
    // that any angle brackets or other markup in the streamed text (e.g.
    // "<subject 1>") are rendered literally and never interpreted as HTML,
    // which also prevents injection attacks.
    st.textEl.replaceChildren();

    const hasReasoning = st.showReasoning && st.reasoning;
    const hasContent = !!st.content;

    if (!hasReasoning && !hasContent) {
        const placeholder = document.createElement("div");
        placeholder.style.color = "#666";
        placeholder.textContent = $tSync("status.waiting");
        st.textEl.appendChild(placeholder);
    } else {
        if (hasReasoning) {
            const header = document.createElement("div");
            header.style.color = "#7aa2f7";
            header.style.fontWeight = "bold";
            header.textContent = $tSync("header.reasoning");
            st.textEl.appendChild(header);

            const reasoning = document.createElement("div");
            reasoning.style.color = "#9a9a9a";
            reasoning.textContent = st.reasoning;
            st.textEl.appendChild(reasoning);

            st.textEl.appendChild(document.createElement("br"));
        }
        if (hasContent) {
            const header = document.createElement("div");
            header.style.color = "#7aa2f7";
            header.style.fontWeight = "bold";
            header.textContent = $tSync("header.output");
            st.textEl.appendChild(header);

            const content = document.createElement("div");
            content.textContent = st.content;
            st.textEl.appendChild(content);
        }
    }

    // Auto-scroll to bottom
    if (st.autoScroll) {
        st.textEl.scrollTop = st.textEl.scrollHeight;
    }

    // Update status
    if (st.statusEl) {
        st.statusEl.textContent = st.streaming
            ? $tSync("status.streaming")
            : (st.lastDone ? $tSync("status.done") : $tSync("status.idle"));
        st.statusEl.style.color = st.streaming ? "#4caf50" : "#888";
    }
}

// ============ WebSocket Event Handling ============

// Map of node_id -> node, so events can be routed to the correct instance.
const nodeById = new Map();

// Buffer of stream events that arrived while their target node was not present
// in the frontend (e.g. the node lives in a non-active workflow tab whose graph
// is unloaded by ComfyUI until the tab is activated). When the node is later
// registered (onAdded/onConfigure/recreation), the buffered events are replayed
// so the content that was streamed while the node was absent is not lost.
const pendingEvents = new Map();

// Snapshot of a node's streaming state (content/reasoning/streaming flags)
// captured when the node is removed. ComfyUI destroys nodes that live in a
// non-active workflow tab, which would otherwise wipe the accumulated streaming
// text. When the node is recreated (tab switched back), this snapshot is
// restored onto the new node so previously streamed content is not lost.
const pendingState = new Map();

// Find a node by id across the graphs that are currently loaded in the
// frontend. This is a fallback for when a stream event arrives for a node that
// has not yet been registered in `nodeById` (e.g. an LLM node living in a
// non-active workflow tab whose onAdded/onConfigure have not fired yet).
//
// We search the active graph first (app.graph / app.canvas.graph), then fall
// back to any graph reachable through the node registry we maintain. Because
// ComfyUI's multi-tab graph storage is version-dependent, we defensively scan
// the active graph and any graph objects we can discover.
function findNodeById(id) {
    const key = String(id);
    const seen = new Set();
    // Recursively scan a graph and any subgraphs reachable from it. Subgraph
    // nodes expose their inner graph via `node.subgraph` (or `node.graph` for
    // the top-level graph), so we walk those to find a node that may live
    // inside a subgraph.
    const scan = (graph) => {
        if (!graph || !Array.isArray(graph._nodes) || seen.has(graph)) return null;
        seen.add(graph);
        for (const n of graph._nodes) {
            if (!n) continue;
            if (String(n.id) === key) return n;
            // Recurse into subgraphs.
            const inner = n.subgraph || (n.graph && n.graph !== graph ? n.graph : null);
            if (inner) {
                const found = scan(inner);
                if (found) return found;
            }
        }
        return null;
    };
    // Active graph (both accessors point to the same object in practice).
    const active = app.graph || (app.canvas && app.canvas.graph);
    let node = scan(active);
    if (node) return node;
    // Also scan the canvas graph explicitly in case it differs.
    if (app.canvas && app.canvas.graph && app.canvas.graph !== active) {
        node = scan(app.canvas.graph);
        if (node) return node;
    }
    return null;
}

// Restore a node's streaming state snapshot (captured when the node was removed
// because its workflow tab was deactivated) onto a freshly recreated node. This
// preserves content that was already accumulated before the node was destroyed.
function restorePendingState(node) {
    const key = String(node.id);
    const snap = pendingState.get(key);
    if (!snap) return;
    pendingState.delete(key);
    const st = getState(node);
    st.content = snap.content || "";
    st.reasoning = snap.reasoning || "";
    st.streaming = !!snap.streaming;
    st.lastDone = !!snap.lastDone;
    st.locked = !!snap.locked;
    renderText(node);
}

// Replay buffered stream events for a node that has just been registered. This
// restores content that was streamed while the node was absent from the
// frontend (e.g. its workflow tab was not active). Events are replayed in
// arrival order so the start/chunk/done sequence reconstructs the full result.
function replayPendingEvents(node) {
    const key = String(node.id);
    const events = pendingEvents.get(key);
    if (!events || events.length === 0) return;
    pendingEvents.delete(key);
    for (const ev of events) {
        handleStreamEvent(ev);
    }
}

function handleStreamEvent(data) {
    let node = nodeById.get(String(data.node_id));
    if (!node) {
        // The node is not registered yet. Try to find it in the loaded graphs
        // and register it on the fly so the streamed content is not dropped.
        node = findNodeById(data.node_id);
        if (node) {
            nodeById.set(String(data.node_id), node);
        } else {
            // The node is not present in the frontend at all (its workflow tab
            // is not active and ComfyUI has unloaded that graph). Buffer the
            // event so it can be replayed once the node is registered again.
            const key = String(data.node_id);
            if (!pendingEvents.has(key)) pendingEvents.set(key, []);
            pendingEvents.get(key).push(data);
            return;
        }
    }
    const st = getState(node);

    // When the result is locked, the backend skips LLM generation and does not
    // stream. Ignore any (stale) stream events so they cannot overwrite the
    // locked content shown in the panel.
    if (st.locked) return;

    if (data.done) {
        st.streaming = false;
        st.lastDone = true;
        if (data.stopped) {
            st.lastDone = false;
        }
        // Auto-lock: when the "auto_lock" toggle is enabled and the generation
        // completed successfully (not stopped), automatically lock the result so
        // it is persisted into the workflow and the LLM is skipped on the next
        // run. A stopped (incomplete) generation is never auto-locked.
        if (!data.stopped && !st.locked && isAutoLockEnabled(node)) {
            lockResult(node);
        }
        renderText(node);
        return;
    }

    // A new generation starts: the backend pushes a "start" event before the
    // first chunk so we reliably clear any previous (possibly stale) content.
    // This is deterministic even if the previous generation's "done" event was
    // missed (e.g. after a Stop), which previously left st.streaming stuck true
    // and caused new content to be appended below the old residual text.
    if (data.start) {
        st.streaming = true;
        st.lastDone = false;
        st.content = "";
        st.reasoning = "";
        renderText(node);
        return;
    }

    // Defensive fallback: if a chunk arrives without a preceding "start" event
    // (e.g. an older backend), clear on the first chunk of a new generation.
    if (!st.streaming) {
        st.streaming = true;
        st.content = "";
        st.reasoning = "";
    }

    if (data.content) st.content += data.content;
    if (data.reasoning_content) st.reasoning += data.reasoning_content;

    renderText(node);
}

// ============ Extension Registration ============

export function setupStreamingPanel(node) {
    // Create the floating DOM panel.
    createPanel(node);
    renderText(node);

    // Register this node in the id -> node map for event routing. The node id
    // is not assigned yet during nodeCreated (it is -1), so register it once the
    // node is actually added to the graph (onAdded), when node.id is final.
    // Tracks whether the node's widgets have been restored (onConfigure). Stream
    // events buffered while the node was absent must be replayed only after the
    // widgets are restored, because replayed events (e.g. the "done" event that
    // triggers auto_lock) depend on widget values like auto_lock.
    let configured = false;
    const registerNode = () => {
        if (node.id != null && String(node.id) !== "-1") {
            nodeById.set(String(node.id), node);
            // Restore state and replay buffered events only once the node has
            // been configured (widgets restored). Before that, defer so that
            // widget-dependent logic in the replayed events sees correct values.
            if (configured) {
                restorePendingState(node);
                replayPendingEvents(node);
            } else if (pendingState.has(String(node.id)) || pendingEvents.has(String(node.id))) {
                // The node has pending state/events but has not been configured
                // yet (onConfigure may not have fired). Retry shortly so the
                // content is restored even if onConfigure is delayed or absent.
                setTimeout(() => {
                    if (configured) {
                        restorePendingState(node);
                        replayPendingEvents(node);
                    }
                }, 300);
            }
            return true;
        }
        return false;
    };
    registerNode();
    // If the node id is not assigned yet (node created but not yet added to a
    // graph — which can happen for nodes living in a non-active workflow tab
    // whose onAdded/onConfigure have not fired), keep retrying until the id
    // becomes valid so the node is registered in `nodeById` and stream events
    // can be routed to it. This complements the on-the-fly graph lookup in
    // handleStreamEvent.
    if (node.id == null || String(node.id) === "-1") {
        const retryTimer = setInterval(() => {
            if (registerNode()) {
                clearInterval(retryTimer);
            }
        }, 500);
        // Stop retrying after 30s to avoid leaking a timer for a node that is
        // never added to a graph.
        setTimeout(() => clearInterval(retryTimer), 30000);
    }
    // onAdded fires when the node is added to the graph (id assigned for new
    // nodes). onConfigure fires after a loaded workflow restores the node, by
    // which point the real id is available. Register in both to cover creation
    // and workflow loading.
    const origOnAdded = node.onAdded ? node.onAdded.bind(node) : null;
    node.onAdded = function (...rest) {
        registerNode();
        if (origOnAdded) return origOnAdded(...rest);
    };
    const origOnConfigure = node.onConfigure ? node.onConfigure.bind(node) : null;
    node.onConfigure = function (...rest) {
        // Mark the node as configured (widgets restored) so registerNode() can
        // restore state and replay buffered events with correct widget values.
        configured = true;
        registerNode();
        // After a workflow is loaded/pasted, restore the locked state (button
        // icon, Clear availability, and the locked content display).
        //
        // Prefer reading the locked result directly from the configure data
        // (rest[0]) because ComfyUI's widget-value restore can misalign the
        // widgets_values array indices (button widgets end up serialize !==
        // false after reload), which would otherwise leave use_locked false.
        const lockedInfo = extractLockedFromConfig(rest && rest[0]);
        if (lockedInfo) {
            applyLockedState(node, lockedInfo.locked, lockedInfo.text, lockedInfo.reasoning);
        } else {
            syncLockedState(node);
        }
        if (origOnConfigure) return origOnConfigure(...rest);
    };

    // Clean up the map entry when the node is removed. (The floating-window
    // helper already removes the DOM panel via its own onRemoved hook.)
    const origRemoved = node.onRemoved ? node.onRemoved.bind(node) : null;
    node.onRemoved = function (...rest) {
        // Capture the current streaming state before the node is destroyed.
        // ComfyUI destroys nodes that live in a non-active workflow tab, which
        // would otherwise wipe the accumulated streaming text. Saving it here
        // lets a recreated node restore the content when the tab is switched
        // back. Only save when there is meaningful content or an in-progress
        // stream, so we do not resurrect stale state for a freshly-cleared node.
        const st = getState(node);
        if (st.content || st.reasoning || st.streaming || st.lastDone) {
            pendingState.set(String(node.id), {
                content: st.content,
                reasoning: st.reasoning,
                streaming: st.streaming,
                lastDone: st.lastDone,
                locked: st.locked,
            });
        }
        nodeById.delete(String(node.id));
        // Drop any buffered events for this node so they are not replayed into
        // a stale/recreated instance later.
        pendingEvents.delete(String(node.id));
        if (origRemoved) return origRemoved(...rest);
    };
}

// Register the WebSocket listener once. A global flag is used so that even if
// this module is loaded multiple times (once as a standalone extension and once
// as an ES-module import), the listener is only attached a single time.
function registerStreamListener() {
    if (window.__zyd232StreamListenerRegistered) return;
    window.__zyd232StreamListenerRegistered = true;
    api.addEventListener("zyd232/stream_text", (event) => {
        handleStreamEvent(event.detail);
    });
}

// Register immediately on module load.
registerStreamListener();
