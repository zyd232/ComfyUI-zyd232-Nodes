/**
 * Tab-scoped isolation helpers for zyd232 nodes (frontend).
 *
 * Problem this module solves
 * --------------------------
 * ComfyUI node ids are only unique *within one workflow*. Two workflow tabs
 * may contain nodes with the same id. In the current ComfyUI frontend a tab
 * switch serializes the active graph and rebuilds it from the target tab's
 * saved state, so nodes of the previously active tab are destroyed and later
 * recreated. Any per-node-id bookkeeping (event routing buffers, state
 * snapshots) that ignores the workflow tab therefore leaks content from one
 * tab's node into another tab's same-id node.
 *
 * This module provides the shared primitives other zyd232 modules need to
 * keep such bookkeeping isolated per workflow tab:
 *
 *   - getCurrentTabKey()        stable identifier of the active workflow tab
 *   - getPromptOwner(promptId)  the tab a queued prompt was started from
 *   - scopeKey(tabKey, nodeId)  composite map key combining both
 *   - initTabScope()            one-time setup (hooks loadGraphData / queuePrompt)
 *
 * How the tab key is derived
 * --------------------------
 * The frontend rebuilds the graph through `ComfyApp.loadGraphData(data,
 * restoreSettings, resetOutputs, workflow, options)` whenever a different
 * workflow tab is opened; the 4th argument carries the workflow object whose
 * `path` (or `key`) stably identifies that tab. We hook that method and track
 * the active tab key. Before any tab is opened the key is "default".
 *
 * How prompt ownership is derived
 * -------------------------------
 * `api.queuePrompt()` returns `{prompt_id, ...}`. We wrap it so that, at the
 * moment of the call (synchronously, before the async POST), the active tab
 * key is recorded as the owner of the returned prompt id. Stream events
 * carrying that prompt id are then routed/buffered for the owning tab instead
 * of "whichever tab happens to be active". Entries are removed when the
 * prompt finishes (execution_success / execution_error /
 * execution_interrupted) so the map does not grow unbounded.
 *
 * Backwards compatibility
 * -----------------------
 * Events without a prompt_id (older backend) resolve to a null owner and the
 * consuming module falls back to its legacy node-id-only routing. If the
 * frontend version does not expose the hooked APIs, everything degrades to a
 * single "default" tab — i.e. exactly the pre-isolation behaviour.
 *
 * Singleton note
 * --------------
 * ComfyUI may evaluate this file more than once (once as a standalone web
 * extension and once as an ES-module import from another zyd232 module). All
 * state therefore lives on `window.__zyd232TabScope` so the hooks are only
 * ever installed once.
 */

import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

// Identifier used until the first workflow tab key is observed.
export const DEFAULT_TAB_KEY = "default";

// Window-level singleton so double module loading cannot double-hook.
const S = window.__zyd232TabScope || (window.__zyd232TabScope = {
    currentTabKey: DEFAULT_TAB_KEY,
    // prompt_id (string) -> tab key of the tab that queued the prompt.
    promptOwner: new Map(),
    initialized: false,
});

// Counter for temporary tab keys (graphs loaded without a workflow identity).
let tmpKeyCounter = 0;

/**
 * Stable identifier of the currently active workflow tab.
 * @returns {string}
 */
export function getCurrentTabKey() {
    return S.currentTabKey;
}

function setActiveTabKey(key) {
    if (key && key !== S.currentTabKey) {
        S.currentTabKey = String(key);
    }
}

/**
 * The tab a queued prompt was started from, or null when unknown (e.g. the
 * event came from an older backend without prompt_id, or the prompt was
 * queued by another client).
 * @param {string|number|null|undefined} promptId
 * @returns {string|null}
 */
export function getPromptOwner(promptId) {
    if (promptId == null) return null;
    return S.promptOwner.get(String(promptId)) ?? null;
}

/**
 * Composite key that isolates per-node bookkeeping per workflow tab.
 * Use this as the Map key for any per-node state/events buffer so that same-id
 * nodes in different tabs never share entries.
 * @param {string} tabKey
 * @param {string|number} nodeId
 * @returns {string}
 */
export function scopeKey(tabKey, nodeId) {
    return `${tabKey}::${nodeId}`;
}

// ============ Hooks ============

/**
 * Hook ComfyApp.loadGraphData so the active tab key follows tab switches.
 * The workflow object (4th argument) identifies the tab being opened; loads
 * without one (blank/default graph, initial restore) get a fresh temporary key
 * so they never share bookkeeping with a real tab.
 */
function hookLoadGraphData() {
    if (!app || typeof app.loadGraphData !== "function") return false;
    const orig = app.loadGraphData.bind(app);
    app.loadGraphData = function (data, ...rest) {
        // rest[2] === arguments[3] === workflow object OR a workflow name string
        // (may be undefined for blank/default loads).
        const wf = rest[2];
        let key = null;
        if (typeof wf === "string") {
            key = wf;
        } else if (wf) {
            // Prefer `key` (stable across load paths); fall back to `path`.
            key = wf.key || wf.path;
        }
        if (!key) {
            // Loads without a workflow identity (blank/default graph, initial
            // restore) get a fresh temporary key so they never share bookkeeping
            // with a real tab — otherwise same-id nodes in the blank canvas and
            // in a real tab would collide.
            tmpKeyCounter += 1;
            key = `tmp-${tmpKeyCounter}`;
        }
        // Set the key BEFORE the rebuild so nodes created during loadGraphData
        // are attributed to the tab that is being opened.
        setActiveTabKey(key);
        return orig(data, ...rest);
    };
    return true;
}

/**
 * Hook api.queuePrompt to record which tab each prompt id was started from.
 * The tab key is captured synchronously at call time — before the async POST —
 * so a tab switch while the request is in flight cannot misattribute it.
 */
function hookQueuePrompt() {
    if (!api || typeof api.queuePrompt !== "function") return false;
    const orig = api.queuePrompt.bind(api);
    api.queuePrompt = async function (...args) {
        const tabAtQueue = S.currentTabKey;
        const result = await orig(...args);
        try {
            const pid = result && result.prompt_id;
            if (pid != null) {
                S.promptOwner.set(String(pid), tabAtQueue);
            }
        } catch {
            // Never let bookkeeping break queueing.
        }
        return result;
    };
    return true;
}

/**
 * Remove prompt ownership entries once their execution finishes, so the map
 * does not grow unbounded across many runs.
 */
function hookExecutionLifecycle() {
    if (!api || typeof api.addEventListener !== "function") return;
    const cleanup = (event) => {
        const pid = event && event.detail && event.detail.prompt_id;
        if (pid != null) S.promptOwner.delete(String(pid));
    };
    api.addEventListener("execution_success", cleanup);
    api.addEventListener("execution_error", cleanup);
    api.addEventListener("execution_interrupted", cleanup);
}

/**
 * One-time initialization. Idempotent: safe to call from multiple modules and
 * across duplicate loads of this file (guarded by the window singleton).
 * @returns {void}
 */
export function initTabScope() {
    if (S.initialized) return;
    S.initialized = true;
    const hookedGraph = hookLoadGraphData();
    const hookedQueue = hookQueuePrompt();
    hookExecutionLifecycle();
    if (!hookedGraph || !hookedQueue) {
        console.warn(
            "[zyd232 tab_scope] some hooks unavailable " +
            `(loadGraphData=${hookedGraph}, queuePrompt=${hookedQueue}); ` +
            "falling back to single-tab (legacy) behaviour."
        );
    }
}
