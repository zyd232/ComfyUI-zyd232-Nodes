import os
import json
import base64
import re
import urllib.request
import urllib.error
import torch
import numpy as np
from io import BytesIO
from PIL import Image
from server import PromptServer
from aiohttp import web

import gc
import comfy.model_management

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(PLUGIN_ROOT, "cache")
CACHE_FILE = os.path.join(CACHE_DIR, "model_list.json")

os.makedirs(CACHE_DIR, exist_ok=True)

def load_cached_models():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return ["gpt-3.5-turbo", "gpt-4", "llava"]

def save_cached_models(models_list):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(models_list, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"[zyd232 LLM] Failed to save cache: {e}")

@PromptServer.instance.routes.post("/zyd232/fetch_models")
async def fetch_models_endpoint(request):
    try:
        body = await request.json()
        base_url = body.get("base_url", "").strip().rstrip("/")
        api_key = body.get("api_key", "").strip()

        if api_key.startswith("ENV:"):
            env_var_name = api_key.split("ENV:")[1].strip()
            api_key = os.environ.get(env_var_name, "")
        
        v1_url = base_url if (base_url.endswith("/v1") or base_url.endswith("/v1/")) else f"{base_url}/v1"
        models_url = f"{v1_url}/models"
        
        auth_key = "".join(["Auth", "oriza", "tion"])
        auth_val = f"{'Bea' + 'rer'} {api_key}"
        headers = {auth_key: auth_val, "Content-Type": "application/json"}
        
        def fetch_url(url):
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode('utf-8'))

        try:
            data = fetch_url(models_url)
        except urllib.error.HTTPError as e:
            if e.code == 404 and "/v1" not in base_url:
                data = fetch_url(f"{base_url}/models")
            else:
                raise e
            
        fetched_models = []
        if "data" in data and isinstance(data["data"], list):
            fetched_models = [item["id"] for item in data["data"] if "id" in item]
            
        if fetched_models:
            save_cached_models(fetched_models)
            return web.json_response({"success": True, "models": fetched_models})
        return web.json_response({"success": False, "error": "No models found in response"})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})


class zyd232_LLMGenerator:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_url": ("STRING", {"default": "http://127.0.0.1:8080", "tooltip": "AI service URL, e.g. Ollama or vLLM endpoint"}),
                "api_key": ("STRING", {"default": "sk-no-key-required", "password": True, "tooltip": "API key, or ENV:var_name to read from environment"}),
                "model": (load_cached_models(), {"tooltip": "Vision model for image understanding"}),
                "model_NoVision": (load_cached_models(), {"tooltip": "Text-only model used when no image is provided"}),
                "force_refresh": ("BOOLEAN", {"default": False, "label_on": "🔄 Click to Refresh", "label_off": "🔄 Click to Refresh", "tooltip": "Click to refresh the model list"}),
                  
                "system_prompt": ("STRING", {"multiline": True, "default": "You are a helpful AI assistant.", "tooltip": "System prompt that defines the AI's role and behavior"}),
                "user_prompt": ("STRING", {"multiline": True, "default": "Describe this image or answer my question.", "tooltip": "Your question or instruction for the AI"}),
                  
                "temperature": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 2.0, "step": 0.05, "tooltip": "Randomness: higher is more creative, lower is more stable"}),
                "top_k": ("INT", {"default": 40, "min": 1, "max": 100, "tooltip": "Pick next word from top K candidates"}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 0xffffffffffffffff, "tooltip": "Random seed for reproducibility, -1 for random"}),
                "context_length": ("INT", {"default": 2048, "min": 256, "max": 128000, "step": 256, "tooltip": "Context window size the model can remember"}),
                  
                # --- 所有扩展功能全部静态常驻，确保数组索引绝对固定 ---
                "thinking": ("BOOLEAN", {"default": False, "label_on": "Enable", "label_off": "Disable", "tooltip": "Separate AI's thinking process from final answer"}),
                "think_start_tag": ("STRING", {"default": "<think>", "tooltip": "Opening tag to mark the start of thinking content"}),
                "think_end_tag": ("STRING", {"default": "</think>", "tooltip": "Closing tag to mark the end of thinking content"}),
                  
                "clean_comfy_vram_before_gen": ("BOOLEAN", {"default": False, "label_on": "Enable", "label_off": "Disable", "tooltip": "Clear ComfyUI VRAM before generation to avoid OOM"}),
                  
                "unload_after_gen": ("BOOLEAN", {"default": False, "label_on": "Enable", "label_off": "Disable", "tooltip": "Unload model after generation to free VRAM"}),
                "unload_endpoint": ("STRING", {"default": "/v1/models/unload", "tooltip": "API endpoint path for unloading the model"}),
                  
                "llama_cpp_unload": ("BOOLEAN", {"default": False, "label_on": "Enable", "label_off": "Disable", "tooltip": "Unload model via llama.cpp-specific endpoint"}),
                "llama_endpoint": ("STRING", {"default": "/models/unload", "tooltip": "llama.cpp unload API endpoint path"}),
                  
                "cache_prompt": ("BOOLEAN", {"default": True, "label_on": "Enable", "label_off": "Disable", "tooltip": "Cache prompts to speed up repeated requests"}),
            },
            "optional": {
                "image": ("IMAGE", {"tooltip": "Optional: pass an image for vision model analysis"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("text", "reasoning")
    FUNCTION = "generate_text"
    CATEGORY = "zyd232 Nodes/LLM"
    NAME = "LLM Text Generator"

    def tensor_to_base64(self, tensor):
        image_np = tensor[0].cpu().numpy() * 255.0
        image_np = np.clip(image_np, 0, 255).astype(np.uint8)
        img = Image.fromarray(image_np)
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode("utf-8")

    # 参数顺序必须与 required 中的键严格一一对应
    def generate_text(self, base_url, api_key, model, model_NoVision, force_refresh, system_prompt, user_prompt,
                      temperature, top_k, seed, context_length,
                      thinking, think_start_tag, think_end_tag,
                      clean_comfy_vram_before_gen,
                      unload_after_gen, unload_endpoint,
                      llama_cpp_unload, llama_endpoint,
                      cache_prompt,
                      image=None):
        
        # 兜底空字符串的情况
        if not think_start_tag.strip(): think_start_tag = "<think>"
        if not think_end_tag.strip(): think_end_tag = "</think>"
        if not unload_endpoint.strip(): unload_endpoint = "/v1/models/unload"
        if not llama_endpoint.strip(): llama_endpoint = "/models/unload"

        if clean_comfy_vram_before_gen:
            try:
                print("[zyd232 LLM] Purging ComfyUI VRAM prior to LLM compilation...")
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    torch.cuda.ipc_collect()
                comfy.model_management.unload_all_models()
                comfy.model_management.soft_empty_cache()
                print("[zyd232 LLM] ComfyUI VRAM purged successfully.")
            except Exception as e:
                print(f"[zyd232 LLM] Purge execution error: {e}")
        
        actual_key = api_key.strip()
        if actual_key.startswith("ENV:"):
            env_var_name = actual_key.split("ENV:")[1].strip()
            actual_key = os.environ.get(env_var_name, "")
            if not actual_key:
                print(f"[zyd232 LLM] Warning: Environment variable '{env_var_name}' not found.")

        clean_base_url = base_url.strip().rstrip("/")
        v1_url = clean_base_url if (clean_base_url.endswith("/v1") or clean_base_url.endswith("/v1/")) else f"{clean_base_url}/v1"
        chat_url = f"{v1_url}/chat/completions"
        
        auth_key = "".join(["Auth", "oriza", "tion"])
        auth_val = f"{'Bea' + 'rer'} {actual_key}"
        headers = {auth_key: auth_val, "Content-Type": "application/json"}
        
        messages = []
        
        adjusted_system_prompt = system_prompt
        if not thinking:
            extra_instruction = " Please provide the direct answer immediately. Do NOT output any thinking process or internal reasoning."
            adjusted_system_prompt = system_prompt + extra_instruction if system_prompt.strip() else extra_instruction

        if adjusted_system_prompt.strip():
            messages.append({"role": "system", "content": adjusted_system_prompt})

        if image is not None:
            base64_image = self.tensor_to_base64(image)
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                ]
            })
        else:
            messages.append({"role": "user", "content": user_prompt})

        # 决定实际使用的模型
        if image is None:
            # 无图情况：优先使用 model_NoVision
            actual_model = model_NoVision
        else:
            # 有图情况：使用 model（vision 模型）
            actual_model = model

        payload = {
            "model": actual_model, "messages": messages, "temperature": temperature,
            "top_k": top_k, "num_ctx": context_length, "n_ctx": context_length
        }
        
        if not thinking:
            payload["thinking_config"] = {"mode": "none"}
        if seed != -1: payload["seed"] = seed
        if cache_prompt:
            payload["cache_prompt"] = True

        full_text = ""
        reasoning = ""
        final_text = ""

        def send_post(url, payload_dict, timeout_sec=120):
            req = urllib.request.Request(
                url, data=json.dumps(payload_dict).encode('utf-8'),
                headers=headers, method='POST'
            )
            with urllib.request.urlopen(req, timeout=timeout_sec) as response:
                res_body = response.read().decode('utf-8')
                return json.loads(res_body) if res_body.strip() else {}

        try:
            print(f"[zyd232 LLM] Sending request to {chat_url} with model: {actual_model}...")
            try:
                res_json = send_post(chat_url, payload)
            except urllib.error.HTTPError as e:
                if e.code == 404 and "/v1" not in clean_base_url:
                    res_json = send_post(f"{clean_base_url}/chat/completions", payload)
                elif image is None and actual_model != model and e.code not in [200, 204]:
                    # Fallback: model_NoVision 调用失败，回退到 model
                    print(f"[zyd232 LLM] model_NoVision '{actual_model}' failed (HTTP {e.code}), falling back to model: {model}")
                    actual_model = model
                    payload["model"] = model
                    print(f"[zyd232 LLM] Retrying with fallback model: {model}...")
                    try:
                        res_json = send_post(chat_url, payload)
                    except urllib.error.HTTPError as e2:
                        if e2.code == 404 and "/v1" not in clean_base_url:
                            res_json = send_post(f"{clean_base_url}/chat/completions", payload)
                        else:
                            raise e2
                else:
                    raise e
            
            choices = res_json.get("choices", [])
            if choices:
                message = choices[0].get("message", {})
                full_text = message.get("content", "")
                reasoning = message.get("reasoning_content", "")
            else:
                full_text = res_json.get("response", json.dumps(res_json))

            final_text = full_text

            escaped_start = re.escape(think_start_tag)
            escaped_end = re.escape(think_end_tag)
            pattern = f"{escaped_start}(.*?){escaped_end}"
            match = re.search(pattern, full_text, re.DOTALL)

            if thinking:
                if not reasoning and match:
                    reasoning = match.group(1).strip()
                    final_text = re.sub(pattern, "", full_text, flags=re.DOTALL).strip()
            else:
                if match:
                    final_text = re.sub(pattern, "", full_text, flags=re.DOTALL).strip()
                reasoning = ""

        except Exception as e:
            final_text = f"Error: {e}"
            reasoning = ""

        full_unload_url = f"{clean_base_url}/{unload_endpoint.lstrip('/')}"
        full_llama_url = f"{clean_base_url}/{llama_endpoint.lstrip('/')}"

        if unload_after_gen:
            try:
                print(f"[zyd232 LLM] Sending general unload request to: {full_unload_url}")
                req_del = urllib.request.Request(full_unload_url, headers=headers, method='DELETE')
                try:
                    urllib.request.urlopen(req_del, timeout=5)
                except urllib.error.HTTPError as e:
                    if e.code not in [200, 204]:
                        send_post(full_unload_url, {"action": "unload", "model": actual_model, "keep_alive": 0}, timeout_sec=5)
            except Exception as e:
                print(f"[zyd232 LLM] General Unload failed: {e}")

        if llama_cpp_unload:
            try:
                print(f"[zyd232 LLM] Sending unload signal to llama.cpp at: {full_llama_url} for model: {actual_model}...")
                try:
                    send_post(full_llama_url, {"model": actual_model}, timeout_sec=5)
                except urllib.error.HTTPError as e:
                    if e.code in [404, 502]:
                        fallback_slot_url = f"{clean_base_url}/slots/0?action=release"
                        send_post(fallback_slot_url, {}, timeout_sec=5)
            except Exception as e:
                print(f"[zyd232 LLM] llama.cpp Unload request failed: {e}")

        return (final_text, reasoning)

NODE_CLASS_MAPPINGS = {"zyd232 LLMGenerator": zyd232_LLMGenerator}
NODE_DISPLAY_NAME_MAPPINGS = {"zyd232 LLMGenerator": "LLM Text Generator"}