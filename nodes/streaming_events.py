"""Reusable streaming-event push helpers for zyd232 nodes.

This module is the single place that knows how to:

1. Resolve the *execution scope* of the currently running node
   (``prompt_id`` + ``node_id``) from ComfyUI's execution context, and
2. Push incremental streaming-text events to the frontend over WebSocket.

Any zyd232 node that streams output should use these helpers instead of
calling ``PromptServer.instance.send_sync`` directly, so that all stream
events carry a consistent payload:

    {
        "node_id": str|None,         # ComfyUI node id (frontend routing)
        "prompt_id": str|None,       # prompt id (workflow-tab isolation)
        "content": str,              # final-text chunk
        "reasoning_content": str,    # reasoning chunk
        "done": bool,                # terminal event
        "stopped": bool,             # generation was stopped by the user
        "start": bool,               # first event of a new generation
    }

Why ``prompt_id`` matters
-------------------------
ComfyUI node ids are only unique *within one workflow*. Two workflow tabs may
contain nodes with the same id. The frontend (web/tab_scope.js) tracks which
workflow tab each queued prompt was started from, and routes stream events to
the owning tab's node instead of "whichever tab is currently active". This is
what keeps Streaming Text panels of same-id nodes in different tabs isolated
from each other.

Backwards compatibility: when the execution context is unavailable (e.g. the
node is invoked outside a normal prompt execution), both ids are ``None`` and
the frontend falls back to its legacy node-id-only routing.
"""

import threading

from server import PromptServer
from comfy_execution.utils import get_executing_context

# WebSocket event name shared with web/tab_scope.js / web/streaming_text.js.
STREAM_EVENT = "zyd232/stream_text"


def get_execution_scope():
    """Resolve the (prompt_id, node_id) of the currently executing node.

    Returns a dict::

        {"prompt_id": str | None, "node_id": str | None}

    Both values are ``None`` when no execution context is available. Callers
    should capture this *once* at the start of ``execute()`` and reuse the
    returned dict for every stream push of that generation (the context is
    bound to the executing thread and stays stable during one node run).
    """
    prompt_id = None
    node_id = None
    try:
        ctx = get_executing_context()
        if ctx is not None:
            prompt_id = getattr(ctx, "prompt_id", None)
            node_id = getattr(ctx, "node_id", None)
    except Exception:
        # Never let scope resolution break generation.
        prompt_id = None
        node_id = None
    return {"prompt_id": prompt_id, "node_id": node_id}


def push_stream_event(scope, content="", reasoning_content="",
                      done=False, stopped=False, start=False):
    """Push one streaming-text chunk to the frontend over WebSocket.

    ``scope`` is the dict returned by :func:`get_execution_scope` (or a plain
    mapping with the same keys). ``None`` scope is tolerated and treated as an
    empty scope (legacy routing on the frontend).

    All other arguments have the same meaning as the individual fields of the
    WS payload described in the module docstring.
    """
    try:
        scope = scope or {}
        PromptServer.instance.send_sync(STREAM_EVENT, {
            "node_id": scope.get("node_id"),
            "prompt_id": scope.get("prompt_id"),
            "content": content or "",
            "reasoning_content": reasoning_content or "",
            "done": bool(done),
            "stopped": bool(stopped),
            "start": bool(start),
        })
    except Exception as e:
        print(f"[zyd232 LLM] Failed to push stream event: {e}")


# ======================= Active Generation Registry (shared) =======================
# Tracks the currently running streaming generation so a Stop button (handled on
# the aiohttp event-loop thread) can interrupt the streaming request that runs on
# ComfyUI's execution thread. During streaming the response object is available,
# so closing it makes the reader raise and return the partial text.
#
# Structure:
#   {
#       "base_url": str,          # cleaned base url of the service
#       "model": str,             # model actually being used
#       "api_key": str,           # resolved api key
#       "response": object,       # the active streaming response (may be None)
#       "stopped": bool,          # set to True once a stop has been requested
#   }
_active_generation = {}
_active_generation_lock = threading.Lock()


def get_active_generation():
    """Return a shallow copy of the active-generation registry (or None)."""
    with _active_generation_lock:
        return dict(_active_generation) if _active_generation else None


def register_active_generation(info):
    """Record metadata of the generation about to start (base_url/model/api_key).

    ``info`` may contain any subset of the registry keys; ``response`` and
    ``stopped`` are always reset for the new generation.
    """
    with _active_generation_lock:
        _active_generation.update({
            "base_url": info.get("base_url"),
            "model": info.get("model"),
            "api_key": info.get("api_key"),
            "response": None,
            "stopped": False,
        })


def set_active_response(response):
    """Attach the live streaming response so Stop can close it."""
    with _active_generation_lock:
        _active_generation["response"] = response


def clear_active_response():
    """Detach the streaming response (generation finished or aborted)."""
    with _active_generation_lock:
        _active_generation["response"] = None


def is_generation_stopped():
    """Whether a stop has been requested for the active generation."""
    with _active_generation_lock:
        return bool(_active_generation.get("stopped"))


def close_active_connection():
    """Close the active streaming response to interrupt the running generation.

    Closing it makes the reader raise, which is caught by the caller and
    reported as a user-initiated stop (partial text is returned).

    Returns True if a connection was actually closed, False otherwise.
    """
    with _active_generation_lock:
        gen = dict(_active_generation) if _active_generation else None
    if not gen:
        return False
    response = gen.get("response")
    # Mark as stopped so the reader can detect the interruption.
    with _active_generation_lock:
        _active_generation["stopped"] = True
    closed = False
    try:
        if response is not None:
            response.close()
            closed = True
    except Exception:
        pass
    return closed


def clear_active_generation():
    """Clear the whole registry once execution finishes."""
    with _active_generation_lock:
        _active_generation.clear()
