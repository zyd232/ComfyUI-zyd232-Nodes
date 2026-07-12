import os
import json
import base64
import re
import requests
import torch
import numpy as np
from io import BytesIO
from PIL import Image
from server import PromptServer
from aiohttp import web

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
        
        v1_url = base_url if (base_url.endswith("/v1") or base_url.endswith("/v1/")) else f"{base_url}/v1"
        models_url = f"{v1_url}/models"
        
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        
        response = requests.get(models_url, headers=headers, timeout=5)
        if response.status_code == 404 and "/v1" not in base_url:
            response = requests.get(f"{base_url}/models", headers=headers, timeout=5)
            
        response.raise_for_status()
        data = response.json()
        
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
                "base_url": ("STRING", {"default": "http://127.0.0.1:8080"}),
                "api_key": ("STRING", {"default": "sk-no-key-required"}),
                "model": (load_cached_models(), ), 
                
                "force_refresh": ("BOOLEAN", {"default": False, "label_on": "🔄 Click to Refresh", "label_off": "🔄 Click to Refresh"}),
                "thinking": ("BOOLEAN", {"default": False, "label_on": "Enable", "label_off": "Disable"}),

                "system_prompt": ("STRING", {"multiline": True, "default": "You are a helpful AI assistant."}),
                "user_prompt": ("STRING", {"multiline": True, "default": "Describe this image or answer my question."}),
                
                "temperature": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 2.0, "step": 0.05}),
                "top_k": ("INT", {"default": 40, "min": 1, "max": 100}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 0xffffffffffffffff}),
                "context_length": ("INT", {"default": 2048, "min": 256, "max": 128000, "step": 256}),
                
                "unload_after_gen": ("BOOLEAN", {"default": False, "label_on": "Enable", "label_off": "Disable"}),
                "llama_cpp_unload": ("BOOLEAN", {"default": False, "label_on": "Enable", "label_off": "Disable"}),
            },
            "optional": {
                "image": ("IMAGE", ),
                "think_start_tag": ("STRING", {"default": "<think>"}),
                "think_end_tag": ("STRING", {"default": "</think>"}),
                # 优化：默认值改为纯路由后缀
                "unload_endpoint": ("STRING", {"default": "/v1/models/unload"}),
                "llama_endpoint": ("STRING", {"default": "/models/unload"}),
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

    def generate_text(self, base_url, api_key, model, force_refresh, thinking, system_prompt, user_prompt, 
                      temperature, top_k, seed, context_length, unload_after_gen, llama_cpp_unload,
                      image=None, think_start_tag="<think>", think_end_tag="</think>", 
                      unload_endpoint="/v1/models/unload", llama_endpoint="/models/unload"):
        
        if not think_start_tag: think_start_tag = "<think>"
        if not think_end_tag: think_end_tag = "</think>"
        
        # 兜底默认后缀
        if not unload_endpoint: unload_endpoint = "/v1/models/unload"
        if not llama_endpoint: llama_endpoint = "/models/unload"
        
        # 格式化基础 URL 移除尾部斜杠
        clean_base_url = base_url.strip().rstrip("/")
        v1_url = clean_base_url if (clean_base_url.endswith("/v1") or clean_base_url.endswith("/v1/")) else f"{clean_base_url}/v1"
        chat_url = f"{v1_url}/chat/completions"
        
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
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

        payload = {
            "model": model, "messages": messages, "temperature": temperature,
            "top_k": top_k, "num_ctx": context_length, "n_ctx": context_length
        }
        
        if not thinking:
            payload["thinking_config"] = {"mode": "none"}

        if seed != -1: payload["seed"] = seed

        full_text = ""
        reasoning = ""
        final_text = ""

        try:
            print(f"[zyd232 LLM] Sending request to {chat_url}...")
            response = requests.post(chat_url, headers=headers, json=payload, timeout=120)
            if response.status_code == 404 and "/v1" not in clean_base_url:
                response = requests.post(f"{clean_base_url}/chat/completions", headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            
            res_json = response.json()
            
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

        # 动态拼接最终的完整物理 URL
        full_unload_url = f"{clean_base_url}/{unload_endpoint.lstrip('/')}"
        full_llama_url = f"{clean_base_url}/{llama_endpoint.lstrip('/')}"

        # 机制1：通用自动卸载
        if unload_after_gen:
            try:
                print(f"[zyd232 LLM] Sending general unload request to: {full_unload_url}")
                unload_resp = requests.delete(full_unload_url, headers=headers, timeout=5)
                if unload_resp.status_code not in [200, 204]:
                    requests.post(full_unload_url, headers=headers, json={"action": "unload", "model": model, "keep_alive": 0}, timeout=5)
            except Exception as e:
                print(f"[zyd232 LLM] General Unload failed: {e}")

        # 机制2：针对 llama.cpp 原生多模型路由的自动显存释放逻辑（带兜底）
        if llama_cpp_unload:
            try:
                print(f"[zyd232 LLM] Sending unload signal to llama.cpp at: {full_llama_url} for model: {model}...")
                
                # 尝试途径 1：标准多模型卸载接口
                llama_resp = requests.post(full_llama_url, headers=headers, json={"model": model}, timeout=5)
                
                # 如果途径 1 返回 502/404，立刻启动途径 2：插槽状态重置释放机制
                if llama_resp.status_code in [404, 502]:
                    print("[zyd232 LLM] Standard unloader met 502/404. Trying slot-0 clearance fallback...")
                    fallback_slot_url = f"{clean_base_url}/slots/0?action=release"
                    llama_resp = requests.post(fallback_slot_url, headers=headers, json={}, timeout=5)
                
                if llama_resp.status_code in [200, 204]:
                    print("[zyd232 LLM] llama.cpp memory cleared successfully.")
                else:
                    print(f"[zyd232 LLM] llama.cpp unload final status: {llama_resp.status_code}")
            except Exception as e:
                print(f"[zyd232 LLM] llama.cpp Unload request failed: {e}")

        return (final_text, reasoning)

NODE_CLASS_MAPPINGS = {"zyd232 LLMGenerator": zyd232_LLMGenerator}
NODE_DISPLAY_NAME_MAPPINGS = {"zyd232 LLMGenerator": "LLM Text Generator"}