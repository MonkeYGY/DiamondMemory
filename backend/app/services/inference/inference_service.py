import os
import subprocess
import json
import requests
import time
import logging
import sys
from typing import Optional
from app.config.settings import settings

logger = logging.getLogger(__name__)


class InferenceService:
    def __init__(self):
        self.model_path = settings.data_directory
        self.context_size = settings.local_llm_max_tokens  # 修复：原代码错误地使用了timeout
        self.temperature = 0.7
        self.ollama_api_url = settings.local_llm_endpoint.rstrip("/")
        self.ollama_generate_url = f"{self.ollama_api_url}/api/generate"
        self.ollama_chat_url = f"{self.ollama_api_url}/api/chat"
        self.ollama_tags_url = f"{self.ollama_api_url}/api/tags"
        self.ollama_psk_url = f"{self.ollama_api_url}/api/ps"
        self.default_model = settings.local_llm_model
        self.fallback_model = settings.local_llm_fallback_model
        self.timeout = settings.local_llm_timeout if settings.local_llm_timeout > 60 else 300
        self.chat_timeout = settings.local_llm_timeout if settings.local_llm_timeout > 60 else 300
        self.models = {
            settings.local_llm_model: settings.local_llm_model,
            settings.local_llm_fallback_model: settings.local_llm_fallback_model,
            "qwen2.5-1.5b": "qwen2.5:1.5b",
            "qwen2.5-4B": "qwen2.5:4b",
            "BGE-M3": "bge-m3"
        }
    
    def _get_keep_alive(self):
        store = self._get_store()
        keep_alive = store.get_config("keep_alive")
        if keep_alive is None or keep_alive == "":
            return -1
        if str(keep_alive).lower() == "false":
            return 0
        if str(keep_alive).strip() == "0":
            return 0
        if keep_alive:
            try:
                return int(keep_alive)
            except (ValueError, TypeError):
                return keep_alive
        return -1
    
    def ensure_ollama_running(self):
        """确保Ollama服务运行"""
        try:
            response = requests.get(self.ollama_tags_url, timeout=2)
            return response.status_code == 200
        except Exception:
            disable_autostart = str(os.environ.get("DM_DISABLE_OLLAMA_AUTOSTART", "")).lower() in ("1", "true", "yes")
            if disable_autostart:
                return False
            try:
                import copy
                env = copy.copy(os.environ)
                
                popen_kwargs = {
                    "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.DEVNULL,
                    "env": env,
                }
                if sys.platform == "win32":
                    popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
                else:
                    popen_kwargs["start_new_session"] = True

                subprocess.Popen(["ollama", "serve"], **popen_kwargs)
                time.sleep(5)
                response = requests.get(self.ollama_tags_url, timeout=2)
                return response.status_code == 200
            except Exception:
                return False
    
    def warmup_model(self):
        """预热模型：将模型加载到内存并常驻，避免首次请求超时"""
        if not self.ensure_ollama_running():
            logger.warning("[Warmup] Ollama服务未运行，跳过预热")
            return False
        
        try:
            loaded_models = requests.get(self.ollama_psk_url, timeout=3)
            if loaded_models.status_code == 200:
                for m in loaded_models.json().get("models", []):
                    if self.default_model in m.get("name", ""):
                        logger.info(f"[Warmup] 模型 {self.default_model} 已在内存中，无需预热")
                        return True
        except Exception:
            pass
        
        model_name = self.resolve_model_name()
        if not model_name:
            logger.warning("[Warmup] 未找到可用模型，跳过预热")
            return False
        
        try:
            logger.info(f"[Warmup] 开始预热模型 {model_name}...")
            payload = {
                "model": model_name,
                "prompt": "hi",
                "stream": False,
                "keep_alive": self._get_keep_alive(),
                "options": {
                    "num_predict": 1,
                    "num_ctx": 2048,
                    "temperature": 0.1
                }
            }
            response = requests.post(
                self.ollama_generate_url,
                json=payload,
                timeout=120
            )
            if response.status_code == 200:
                logger.info(f"[Warmup] 模型 {model_name} 预热完成，已常驻内存")
                return True
            else:
                logger.warning(f"[Warmup] 模型预热失败: HTTP {response.status_code}")
                return False
        except requests.exceptions.Timeout:
            logger.warning("[Warmup] 模型预热超时（模型文件较大，加载需要时间）")
            return False
        except Exception as e:
            logger.warning(f"[Warmup] 模型预热异常: {e}")
            return False

    def _normalize_ollama_stream_line(self, line: bytes) -> bytes:
        try:
            if not line:
                return line
            s = line.decode("utf-8", errors="ignore").strip()
            if not s:
                return line
            data = json.loads(s)
            msg = data.get("message") if isinstance(data, dict) else None
            if isinstance(msg, dict):
                content = msg.get("content") or ""
                thinking = msg.get("thinking") or ""
                if not content and thinking:
                    msg["content"] = thinking
                    data["message"] = msg
                    return (json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8")
            return (s + "\n").encode("utf-8")
        except Exception:
            try:
                return line + (b"\n" if not line.endswith(b"\n") else b"")
            except Exception:
                return line
    
    def check_gpu_info(self):
        """检查GPU信息和Ollama运行状态"""
        try:
            response = requests.get(self.ollama_psk_url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                logger.info("GPU信息:")
                for model in data.get("models", []):
                    logger.info(f"  模型: {model.get('name')}")
                    logger.info(f"  处理器: {model.get('processor')}")
                    logger.info(f"  内存: {model.get('size')} bytes")
                return data
            else:
                logger.warning("无法获取GPU信息")
                return None
        except Exception as e:
            logger.error(f"获取GPU信息失败: {e}")
            return None
    
    def get_available_models(self):
        """获取Ollama中已安装的模型列表"""
        try:
            response = requests.get(self.ollama_tags_url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                models = [model["name"] for model in data.get("models", [])]
                return models
        except Exception as e:
            logger.error(f"获取模型列表失败: {e}")
        return []
    
    def resolve_model_name(self, requested_model=None):
        """解析模型名称，优先使用已安装的模型"""
        available_models = self.get_available_models()
        
        if requested_model and requested_model in available_models:
            return requested_model
        
        for alias, ollama_name in self.models.items():
            if ollama_name in available_models:
                return ollama_name
        
        if available_models:
            return available_models[0]
        
        return self.default_model
    
    def _detect_gpu_info(self):
        """自动检测GPU硬件信息，返回(可用VRAM_GB, GPU型号)"""
        try:
            response = requests.get(self.ollama_psk_url, timeout=3)
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                for m in models:
                    processor = m.get("processor", {})
                    gpu_info = processor.get("GPUs", [])
                    if gpu_info:
                        gpu = gpu_info[0]
                        vram = gpu.get("memory", 0)
                        vram_gb = vram / (1024 * 1024 * 1024)
                        gpu_name = gpu.get("name", "Unknown")
                        return vram_gb, gpu_name
        except Exception:
            pass
        return 0, "Unknown"
    
    def _get_optimal_context_tier(self, total_tokens_needed: int, max_ctx_cap: Optional[int] = None) -> int:
        """
        根据硬件配置和数据量智能选择上下文档位
        返回最优的num_ctx值
        
        档位选择逻辑：
        1. 先检测GPU VRAM
        2. 根据VRAM大小确定最大可用上下文
        3. 根据实际数据量选择最小可用档位
        """
        vram_gb, gpu_name = self._detect_gpu_info()
        
        if max_ctx_cap is not None:
            try:
                max_ctx_cap = int(max_ctx_cap)
            except Exception:
                max_ctx_cap = None
        if max_ctx_cap is not None and max_ctx_cap <= 0:
            max_ctx_cap = None

        if vram_gb <= 0:
            max_ctx = max_ctx_cap or 8192
        else:
            # 根据VRAM确定最大可用上下文（qwen3.5:4b模型约占4GB，剩余给上下文）
            if vram_gb >= 12:  # 12GB+ (如RTX 3060/4070)
                max_ctx = 32768
            elif vram_gb >= 8:  # 8GB (如RTX 3050/2080)
                max_ctx = 16384
            elif vram_gb >= 4:  # 4GB
                max_ctx = 8192
            else:
                max_ctx = 4096
            if max_ctx_cap is not None:
                max_ctx = min(max_ctx, max_ctx_cap)
        
        # 智能档位：2K, 4K, 8K, 16K, 32K
        tiers = [2048, 4096, 8192, 16384, 32768]
        
        # 选择最小可用档位（节省内存，提高速度）
        for tier in tiers:
            if total_tokens_needed <= tier and tier <= max_ctx:
                return tier
        
        # 如果超出所有档位，返回硬件允许的最大值
        return max_ctx
    
    def _calculate_dynamic_context(self, input_text: str, default_max: int) -> int:
        """
        智能动态计算上下文窗口大小，根据数据量和硬件自动匹配最优档位。
        
        优化逻辑：
        1. 计算输入数据的实际token数
        2. 加上输出预留空间
        3. 调用_get_optimal_context_tier选择最优档位
        4. 避免一刀切使用128K，节省内存，提升速度
        """
        char_count = len(input_text)
        try:
            cfg_max = int(settings.local_llm_max_tokens)
        except Exception:
            cfg_max = 8192
        if cfg_max <= 0:
            cfg_max = 8192

        if default_max <= 2048:
            estimated_input_tokens = int(char_count * 1.2)
            reserved_output = max(256, min(default_max, 768))
            total_needed = estimated_input_tokens + reserved_output

            if total_needed <= 2048:
                return 2048
            return self._get_optimal_context_tier(total_needed, max_ctx_cap=4096)

        vram_gb, _ = self._detect_gpu_info()
        if vram_gb >= 8:
            desired = 16384
        elif vram_gb >= 4:
            desired = 8192
        else:
            desired = 4096
        return self._get_optimal_context_tier(desired, max_ctx_cap=desired)
    
    def _get_store(self):
        from app.storage.sqlite_store import SQLiteStore
        if not hasattr(self, '_store') or self._store is None:
            self._store = SQLiteStore()
        return self._store

    def _record_token_usage(self, tokens: int):
        store = self._get_store()
        try:
            current = store.get_config("external_llm_token_usage")
            current_val = int(current) if current else 0
            store.set_config("external_llm_token_usage", str(current_val + tokens), "外部大模型消耗的Token总数")
        except Exception as e:
            logger.warning(f"记录Token失败: {e}")

    def _fallback_to_local(self, reason: str):
        store = self._get_store()
        logger.warning(f"[Fallback] 外部大模型异常 ({reason})，自动切换回本地大模型")
        store.set_config("llm_provider", "ollama", "自动降级为本地模型")
        settings.llm_provider = "ollama"
        
    def _fallback_to_none(self, reason: str):
        store = self._get_store()
        logger.warning(f"[Fallback] 本地大模型异常 ({reason})，自动关闭大模型处理")
        store.set_config("llm_enabled", "false", "自动关闭大模型")
        settings.llm_enabled = False

    def generate_text(self, prompt, model_path=None, max_tokens=100, format=None):
        store = self._get_store()
        llm_enabled = store.get_config("llm_enabled")
        llm_enabled = llm_enabled.lower() == "true" if llm_enabled else getattr(settings, "llm_enabled", True)
        
        if not llm_enabled:
            return {"success": False, "error": "大模型处理已禁用"}
            
        provider = store.get_config("llm_provider") or settings.llm_provider
        
        if provider == "external":
            ext_endpoint = store.get_config("external_llm_endpoint") or settings.external_llm_endpoint
            ext_api_key = store.get_config("external_llm_api_key") or settings.external_llm_api_key
            ext_model = store.get_config("external_llm_model") or settings.external_llm_model
            
            try:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {ext_api_key}"
                }
                payload = {
                    "model": ext_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": self.temperature
                }
                
                if format == "json":
                    payload["response_format"] = {"type": "json_object"}
                
                response = requests.post(f"{ext_endpoint.rstrip('/')}/chat/completions", headers=headers, json=payload, timeout=self.timeout)
                if response.status_code == 200:
                    data = response.json()
                    content = data.get("choices", [])[0].get("message", {}).get("content", "")
                    usage = data.get("usage", {}).get("total_tokens", 0)
                    self._record_token_usage(usage)
                    
                    return {
                        "success": True,
                        "generated_text": content,
                        "model": ext_model,
                        "prompt_tokens": data.get("usage", {}).get("prompt_tokens", 0),
                        "completion_tokens": data.get("usage", {}).get("completion_tokens", 0)
                    }
                else:
                    self._fallback_to_local(f"HTTP {response.status_code}")
                    return {"success": False, "error": f"外部大模型API错误 ({response.status_code})，已自动切换为本地模型"}
            except Exception as e:
                self._fallback_to_local(str(e))
                return {"success": False, "error": f"外部大模型请求异常: {str(e)}，已自动切换为本地模型"}
                
        # 否则使用本地Ollama
        if not self.ensure_ollama_running():
            self._fallback_to_none("Ollama服务未运行")
            return {
                "success": False, 
                "error": "Ollama服务未运行，已自动关闭大模型功能"
            }
        
        model_name = self.resolve_model_name(model_path)
        if not model_name:
            self._fallback_to_none("未找到本地模型")
            return {"success": False, "error": "本地大模型未下载，已自动关闭大模型功能"}
        
        try:
            # 动态计算所需的上下文大小
            dynamic_ctx = self._calculate_dynamic_context(prompt, max_tokens)
            
            payload = {
                "model": model_name,
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": self.temperature,
                "stream": False,
                "keep_alive": self._get_keep_alive(),
                "options": {
                    "num_predict": max_tokens,
                    "num_ctx": dynamic_ctx,
                    "temperature": self.temperature
                }
            }
            
            if format == "json":
                payload["format"] = "json"
            
            response = requests.post(
                self.ollama_generate_url, 
                json=payload, 
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                output = response.json()
                
                # Check for "thinking" if "response" is empty (for reasoning models with format="json")
                response_text = output.get("response", "")
                if not response_text and output.get("thinking"):
                    response_text = output.get("thinking")
                    
                return {
                    "success": True,
                    "generated_text": response_text,
                    "model": model_name,
                    "prompt_tokens": len(prompt.split()),
                    "completion_tokens": len(response_text.split())
                }
            else:
                error_detail = response.text
                if "model not found" in error_detail.lower():
                    error_detail = f"模型'{model_name}'未安装，请运行: ollama pull {model_name}"
                return {
                    "success": False, 
                    "error": f"Ollama API错误 ({response.status_code}): {error_detail}"
                }
        except requests.exceptions.Timeout:
            return {
                "success": False, 
                "error": f"请求超时（{self.timeout}秒）。可能原因：1)模型未加载 2)显存不足 3)提示词过长。请尝试减小max_tokens或检查Ollama日志"
            }
        except requests.exceptions.ConnectionError:
            return {
                "success": False, 
                "error": "无法连接到Ollama服务，请确保Ollama正在运行"
            }
        except Exception as e:
            return {"success": False, "error": f"生成文本失败: {str(e)}"}
    
    def chat_stream(self, messages, model_path=None, max_tokens=2048):
        import json
        import datetime
        
        store = self._get_store()
        llm_enabled = store.get_config("llm_enabled")
        llm_enabled = llm_enabled.lower() == "true" if llm_enabled else getattr(settings, "llm_enabled", True)
        
        if not llm_enabled:
            error_msg = {"message": {"content": "\n[系统提示：大模型处理已禁用，目前处于纯向量检索模式，无法生成对话。请在设置中开启大模型处理。]"}, "done": True}
            yield json.dumps(error_msg).encode("utf-8") + b"\n"
            return
            
        provider = store.get_config("llm_provider") or settings.llm_provider
        
        # 组装完整的全量文本用于动态计算上下文
        full_text = " ".join([m.get("content", "") for m in messages])
        
        if provider == "external":
            ext_endpoint = store.get_config("external_llm_endpoint") or settings.external_llm_endpoint
            ext_api_key = store.get_config("external_llm_api_key") or settings.external_llm_api_key
            ext_model = store.get_config("external_llm_model") or settings.external_llm_model
            
            try:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {ext_api_key}"
                }
                
                # 强制约束外部模型的 max_tokens，避免超出 API 限制（如阿里 qwen3.6-plus 限制 max_tokens <= 8192）
                ext_max_tokens = int(store.get_config("external_llm_max_tokens") or settings.external_llm_max_tokens)
                safe_max_tokens = min(max_tokens, ext_max_tokens)
                
                payload = {
                    "model": ext_model,
                    "messages": messages,
                    "max_tokens": safe_max_tokens,
                    "temperature": self.temperature,
                    "stream": True
                }
                
                # 发起流式请求
                with requests.post(f"{ext_endpoint.rstrip('/')}/chat/completions", headers=headers, json=payload, timeout=self.chat_timeout, stream=True) as response:
                    if response.status_code != 200:
                        self._fallback_to_local(f"HTTP {response.status_code}")
                        error_msg = {"message": {"content": f"\n[外部大模型连接失败 ({response.status_code})，已自动切换回本地模型。请再次提问]"}, "done": True}
                        yield json.dumps(error_msg).encode("utf-8") + b"\n"
                        return
                        
                    total_content = ""
                    for line in response.iter_lines():
                        if line:
                            decoded_line = line.decode('utf-8')
                            if decoded_line.startswith("data: "):
                                data_str = decoded_line[6:]
                                if data_str == "[DONE]":
                                    break
                                try:
                                    data_json = json.loads(data_str)
                                    choices = data_json.get("choices", [])
                                    if choices:
                                        delta = choices[0].get("delta", {})
                                        content_chunk = delta.get("content", "")
                                        if content_chunk:
                                            total_content += content_chunk
                                            # 转换为Ollama兼容格式返回给前端
                                            ollama_chunk = {
                                                "model": ext_model,
                                                "created_at": datetime.datetime.now().isoformat(),
                                                "message": {
                                                    "role": "assistant",
                                                    "content": content_chunk
                                                },
                                                "done": False
                                            }
                                            yield json.dumps(ollama_chunk).encode("utf-8") + b"\n"
                                except Exception as e:
                                    continue
                                    
                    # 结束标记，包含usage信息（OpenAI流式返回可能在最后一个chunk的usage中）
                    # 简单估算：直接记录字数作为token，因为流式不一定返回准确的usage
                    # 此处可结合 _record_token_usage 估算消耗
                    estimated_tokens = len(total_content) + len(full_text)
                    self._record_token_usage(estimated_tokens)
                    
                    done_chunk = {
                        "model": ext_model,
                        "created_at": datetime.datetime.now().isoformat(),
                        "message": {"role": "assistant", "content": ""},
                        "done": True
                    }
                    yield json.dumps(done_chunk).encode("utf-8") + b"\n"
            except Exception as e:
                self._fallback_to_local(str(e))
                error_msg = {"message": {"content": f"\n[外部大模型连接异常，已自动切换回本地模型。错误信息: {str(e)}]"}, "done": True}
                yield json.dumps(error_msg).encode("utf-8") + b"\n"
                
        else:
            # 本地Ollama 流式生成
            if not self.ensure_ollama_running():
                self._fallback_to_none("Ollama服务未运行")
                error_msg = {"message": {"content": "\n[系统提示：Ollama服务未运行。为避免影响使用，大模型处理功能已自动关闭。目前处于纯向量检索模式，请在设置中启动并重新开启大模型]"}, "done": True}
                yield json.dumps(error_msg).encode("utf-8") + b"\n"
                return
                
            model_name = self.resolve_model_name(model_path)
            if not model_name:
                self._fallback_to_none("没有找到可用的本地模型")
                error_msg = {"message": {"content": "\n[系统提示：本地大模型未下载。大模型处理功能已自动关闭。目前处于纯向量检索模式，请在设置中下载模型后重新开启]"}, "done": True}
                yield json.dumps(error_msg).encode("utf-8") + b"\n"
                return
                
            dynamic_ctx = self._calculate_dynamic_context(full_text, max_tokens)
            
            try:
                payload = {
                    "model": model_name,
                    "messages": messages,
                    "stream": True,
                    "keep_alive": self._get_keep_alive(),
                    "options": {
                        "num_predict": max_tokens,
                        "num_ctx": dynamic_ctx,
                        "temperature": self.temperature
                    }
                }
                
                with requests.post(self.ollama_chat_url, json=payload, timeout=self.chat_timeout, stream=True) as response:
                    if response.status_code != 200:
                        self._fallback_to_none(f"API错误 {response.status_code}")
                        error_msg = {"message": {"content": f"\n[系统提示：Ollama请求失败 ({response.status_code})。大模型功能已自动关闭。请在设置中检查模型状态]"}, "done": True}
                        yield json.dumps(error_msg).encode("utf-8") + b"\n"
                        return
                        
                    for line in response.iter_lines():
                        if line:
                            yield self._normalize_ollama_stream_line(line)
            except Exception as e:
                self._fallback_to_none(str(e))
                error_msg = {"message": {"content": f"\n[系统提示：本地大模型异常 ({str(e)})。大模型处理功能已自动关闭。]"}, "done": True}
                yield json.dumps(error_msg).encode("utf-8") + b"\n"

    def chat_completion(self, messages, model_path=None, max_tokens=2048):
        store = self._get_store()
        llm_enabled = store.get_config("llm_enabled")
        llm_enabled = llm_enabled.lower() == "true" if llm_enabled else getattr(settings, "llm_enabled", True)
        
        if not llm_enabled:
            return {"success": False, "error": "大模型处理已禁用"}
            
        provider = store.get_config("llm_provider") or settings.llm_provider
        
        if provider == "external":
            ext_endpoint = store.get_config("external_llm_endpoint") or settings.external_llm_endpoint
            ext_api_key = store.get_config("external_llm_api_key") or settings.external_llm_api_key
            ext_model = store.get_config("external_llm_model") or settings.external_llm_model
            
            try:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {ext_api_key}"
                }
                payload = {
                    "model": ext_model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": self.temperature
                }
                
                response = requests.post(f"{ext_endpoint.rstrip('/')}/chat/completions", headers=headers, json=payload, timeout=self.chat_timeout)
                if response.status_code == 200:
                    data = response.json()
                    content = data.get("choices", [])[0].get("message", {}).get("content", "")
                    usage = data.get("usage", {}).get("total_tokens", 0)
                    self._record_token_usage(usage)
                    
                    return {
                        "success": True,
                        "generated_text": content,
                        "model": ext_model,
                        "prompt_tokens": data.get("usage", {}).get("prompt_tokens", 0),
                        "completion_tokens": data.get("usage", {}).get("completion_tokens", 0)
                    }
                else:
                    self._fallback_to_local(f"HTTP {response.status_code}")
                    return {"success": False, "error": f"外部大模型API错误 ({response.status_code})，已自动切换为本地模型"}
            except Exception as e:
                self._fallback_to_local(str(e))
                return {"success": False, "error": f"外部大模型请求异常: {str(e)}，已自动切换为本地模型"}
        
        # 否则使用本地Ollama
        if not self.ensure_ollama_running():
            self._fallback_to_none("Ollama服务未运行")
            return {
                "success": False, 
                "error": "Ollama服务未运行，已自动关闭大模型功能"
            }
        
        model_name = self.resolve_model_name(model_path)
        if not model_name:
            self._fallback_to_none("未找到本地模型")
            return {"success": False, "error": "本地大模型未下载，已自动关闭大模型功能"}
        
        try:
            # 计算总长度来动态分配上下文
            full_text = " ".join([m.get("content", "") for m in messages])
            dynamic_ctx = self._calculate_dynamic_context(full_text, max_tokens)
            
            payload = {
                "model": model_name,
                "messages": messages,
                "stream": False,
                "keep_alive": self._get_keep_alive(),
                "options": {
                    "num_predict": max_tokens,
                    "num_ctx": dynamic_ctx,
                    "temperature": self.temperature
                }
            }
            logger.debug(f"CHAT PAYLOAD: model={model_name}, ctx={dynamic_ctx}")
            
            response = requests.post(
                self.ollama_chat_url, 
                json=payload, 
                timeout=self.chat_timeout
            )
            
            if response.status_code == 200:
                output = response.json()
                msg = output.get("message", {}) or {}
                message_content = msg.get("content", "") or ""
                if not message_content and msg.get("thinking"):
                    message_content = msg.get("thinking") or ""
                return {
                    "success": True,
                    "generated_text": message_content,
                    "model": model_name,
                    "prompt_tokens": sum(len(msg.get("content", "").split()) for msg in messages),
                    "completion_tokens": len(message_content.split())
                }
            else:
                error_detail = response.text
                if "model not found" in error_detail.lower():
                    error_detail = f"模型'{model_name}'未安装，请运行: ollama pull {model_name}"
                return {
                    "success": False, 
                    "error": f"Ollama API错误 ({response.status_code}): {error_detail}"
                }
        except requests.exceptions.Timeout:
            return {
                "success": False, 
                "error": f"请求超时（{self.chat_timeout}秒）。可能原因：1)模型未加载 2)显存不足 3)提示词过长。请尝试减小max_tokens或检查Ollama日志"
            }
        except requests.exceptions.ConnectionError:
            return {
                "success": False, 
                "error": "无法连接到Ollama服务，请确保Ollama正在运行"
            }
        except Exception as e:
            return {"success": False, "error": f"聊天完成失败: {str(e)}"}
            
    def generate(self, prompt: str, model: str = None, max_tokens: int = 2048) -> str:
        """为 memory_service 提供的简化生成接口，使用 chat_completion 提高指令遵循能力"""
        messages = [{"role": "user", "content": prompt}]
        result = self.chat_completion(messages=messages, model_path=model, max_tokens=max_tokens)
        if result.get("success"):
            return result.get("generated_text", "")
        else:
            raise Exception(result.get("error", "未知错误"))

# 全局推理服务实例
inference_service = InferenceService()
