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
        st.lockBtn.title = "Click to unlock the result: allow the node to call the LLM again on the next run";
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
        st.lockBtn.title = "Click to lock the result: save the current output into the workflow and skip LLM generation on the next run";
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
    statusEl.textContent = "○ Idle";

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
        title: "Streaming Text",
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
        const reasoningBtn = makeTitleButton(st.showReasoning ? "🧠" : "🚫", "Click to toggle reasoning", () => {
            st.showReasoning = !st.showReasoning;
            reasoningBtn.textContent = st.showReasoning ? "🧠" : "🚫";
            renderText(node);
        });

        // Lock / unlock button. The icon reflects the CURRENT lock state: 🔒
        // when locked, 🔓 when unlocked. Locking persists the current
        // content/reasoning into the hidden locked_* widgets so it is saved with
        // the workflow and the backend skips the LLM call on re-run. Unlocking
        // clears that state so the node re-runs the LLM.
        const lockBtn = makeTitleButton("🔓", "Click to lock the result: save the current output into the workflow and skip LLM generation on the next run", () => {
            if (st.locked) {
                unlockResult(node);
            } else {
                lockResult(node);
            }
        });

        // Clear button. Disabled while the result is locked so the user cannot
        // accidentally wipe a locked result; they must unlock first.
        const clearBtn = makeTitleButton("✕", "Clear", () => {
            st.content = "";
            st.reasoning = "";
            st.lastDone = false;
            st.streaming = false;
            renderText(node);
        });

        // Copy button
        const copyBtn = makeTitleButton("⧉", "Copy", () => {
            const text = (st.showReasoning && st.reasoning ? st.reasoning + "\n\n" : "") + st.content;
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).catch(() => {});
            }
        });

        // Collapse button
        const collapseBtn = makeTitleButton("▼", "Collapse", () => {
            win.toggleCollapsed();
            collapseBtn.textContent = win.isCollapsed() ? "▶" : "▼";
        });

        // Enable/disable the Clear button based on the locked state.
        const updateClearButton = () => {
            clearBtn.disabled = st.locked;
            clearBtn.style.opacity = st.locked ? "0.4" : "1";
            clearBtn.style.cursor = st.locked ? "not-allowed" : "pointer";
            clearBtn.title = st.locked ? "Unlock the result before clearing" : "Clear";
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
        st.lockBtn.title = locked
            ? "Click to unlock the result: allow the node to call the LLM again on the next run"
            : "Click to lock the result: save the current output into the workflow and skip LLM generation on the next run";
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
        placeholder.textContent = "Waiting for output...";
        st.textEl.appendChild(placeholder);
    } else {
        if (hasReasoning) {
            const header = document.createElement("div");
            header.style.color = "#7aa2f7";
            header.style.fontWeight = "bold";
            header.textContent = "── Reasoning ──";
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
            header.textContent = "── Output ──";
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
            ? "● Streaming..."
            : (st.lastDone ? "● Done" : "○ Idle");
        st.statusEl.style.color = st.streaming ? "#4caf50" : "#888";
    }
}

// ============ WebSocket Event Handling ============

// Map of node_id -> node, so events can be routed to the correct instance.
const nodeById = new Map();

function handleStreamEvent(data) {
    const node = nodeById.get(String(data.node_id));
    if (!node) {
        console.log("[zyd232 Stream] no node found for id:", data.node_id, "registered ids:", [...nodeById.keys()]);
        return;
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

    // A new generation starts: clear previous content on the first chunk.
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
    const registerNode = () => {
        if (node.id != null && String(node.id) !== "-1") {
            nodeById.set(String(node.id), node);
        }
    };
    registerNode();
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
        registerNode();
        // After a workflow is loaded/pasted, restore the locked state (button
        // icon, Clear availability, and the locked content display) from the
        // persisted hidden widgets.
        syncLockedState(node);
        if (origOnConfigure) return origOnConfigure(...rest);
    };

    // Clean up the map entry when the node is removed. (The floating-window
    // helper already removes the DOM panel via its own onRemoved hook.)
    const origRemoved = node.onRemoved ? node.onRemoved.bind(node) : null;
    node.onRemoved = function (...rest) {
        nodeById.delete(String(node.id));
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
