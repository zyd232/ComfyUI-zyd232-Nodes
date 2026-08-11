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
            win: null,            // the floating-window controller
            textEl: null,         // the text content element
            statusEl: null,       // the status element
        };
    }
    return node.__zyd232Stream;
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
        overflowY: "auto",
        padding: "6px 8px",
        fontSize: "11px",
        fontFamily: "monospace",
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
        lineHeight: "1.4",
        color: "#e0e0e0",
    });

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
        onCollapse: (collapsed) => {
            st.collapsed = collapsed;
        },
    });

    // Add the Streaming-Text-specific title-bar buttons.
    const btnRow = win.btnRow;
    if (btnRow) {
        // Reasoning toggle button
        const reasoningBtn = makeTitleButton(st.showReasoning ? "🧠" : "🚫", "Toggle reasoning", () => {
            st.showReasoning = !st.showReasoning;
            reasoningBtn.textContent = st.showReasoning ? "🧠" : "🚫";
            renderText(node);
        });

        // Clear button
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

        btnRow.append(reasoningBtn, clearBtn, copyBtn, collapseBtn);
    }

    // Store references
    st.win = win;
    st.textEl = textEl;
    st.statusEl = statusEl;

    return win;
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
    console.log("[zyd232 Stream] event received: node_id =", data.node_id, "done =", data.done, "content_len =", (data.content || "").length);
    const node = nodeById.get(String(data.node_id));
    if (!node) {
        console.log("[zyd232 Stream] no node found for id:", data.node_id, "registered ids:", [...nodeById.keys()]);
        return;
    }
    const st = getState(node);

    if (data.done) {
        st.streaming = false;
        st.lastDone = true;
        if (data.stopped) {
            st.lastDone = false;
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
