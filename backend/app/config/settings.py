"""钻石记忆系统配置管理"""
import os
import json
import logging
from pydantic_settings import BaseSettings
from typing import Optional, List

logger = logging.getLogger(__name__)


def _get_data_dir_from_env_or_argv() -> Optional[str]:
    """从环境变量或命令行参数中解析 data-dir。

    设计目标：在模块 import 阶段即可得到 --data-dir，避免 Settings 初始化时写入安装目录。
    """
    # 环境变量兜底（便于调试/特殊启动器）
    env_dir = os.environ.get("DM_DATA_DIR") or os.environ.get("DIAMOND_MEMORY_DATA_DIR")
    if env_dir:
        return env_dir

    # 避免依赖 argparse（argparse 在 backend/main.py 的 lifespan 中才解析，时机太晚）
    try:
        import sys

        argv = list(getattr(sys, "argv", []) or [])
        for i, item in enumerate(argv):
            if item == "--data-dir" and i + 1 < len(argv):
                return argv[i + 1]
    except Exception:
        pass

    return None


def _read_json_if_exists(file_path: str) -> Optional[dict]:
    if not file_path or not os.path.exists(file_path):
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _migrate_legacy_storage_config_if_needed(data_dir: str, project_root: str) -> None:
    """将旧位置的 storage_config.json 迁移写入到新位置（仅写新位置）。

    兼容策略：
    - 允许读取旧位置（project_root、project_root/data 等）
    - 但一旦确定 data_dir（通常来自 Electron userData），写入必须落在 data_dir 下
    """
    if not data_dir:
        return

    new_config_file = os.path.join(data_dir, "storage_config.json")
    if os.path.exists(new_config_file):
        return

    legacy_candidates = [
        os.path.join(project_root, "storage_config.json"),
        os.path.join(project_root, "data", "storage_config.json"),
        os.path.join(project_root, "test_new_storage", "storage_config.json"),
    ]

    legacy_config = None
    for fp in legacy_candidates:
        legacy_config = _read_json_if_exists(fp)
        if legacy_config:
            break

    if not legacy_config:
        return

    # 迁移时强制声明 system_data_directory 为新 data_dir；storage_path 仅做透传
    storage_path = legacy_config.get("storage_path")
    _write_storage_config(data_dir, storage_path)


def _resolve_data_dir() -> str:
    """解析系统数据目录路径（数据库、向量库等系统文件存放位置）
    
    生产环境下，系统数据目录必须落到 `--data-dir`（Electron userData）指定目录，
    以避免在 macOS `.app` / Windows `Program Files` 等只读安装目录下写入报错。
    优先级：
    1) env / argv 的 --data-dir
    2) 兼容读取旧位置（只读）
    3) 开发环境回退到项目目录下的 data/
    """
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    forced_data_dir = _get_data_dir_from_env_or_argv()
    if forced_data_dir:
        return forced_data_dir
    
    project_config_file = os.path.join(project_root, "storage_config.json")
    if os.path.exists(project_config_file):
        try:
            with open(project_config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
                if config.get("system_data_directory"):
                    path = config["system_data_directory"]
                    if os.path.exists(path):
                        return path
                if config.get("configured") and config.get("data_directory"):
                    path = config["data_directory"]
                    if os.path.exists(path):
                        return path
        except Exception:
            pass

    candidate_dirs = [
        os.path.join(project_root, "test_new_storage"),
        os.path.join(project_root, "data"),
    ]
    
    for candidate in candidate_dirs:
        config_file = os.path.join(candidate, "storage_config.json")
        if os.path.exists(config_file):
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    if config.get("system_data_directory"):
                        path = config["system_data_directory"]
                        if os.path.exists(path):
                            return path
                    if config.get("configured") and config.get("data_directory"):
                        path = config["data_directory"]
                        if os.path.exists(path):
                            return path
            except Exception:
                pass
    
    return candidate_dirs[-1]


def _resolve_storage_path(data_dir: str) -> str:
    """解析用户存储路径（知识库、用户文档等用户数据存放位置）
    
    用户存储路径可以随时变更，与系统数据路径分离。
    优先从数据库配置中读取 storage_path，其次从 storage_config.json 读取，
    最后回退到 data_directory（向后兼容）。
    """
    config_file = os.path.join(data_dir, "storage_config.json")
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
                if config.get("storage_path"):
                    path = config["storage_path"]
                    if os.path.exists(path):
                        return path
        except Exception:
            pass

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    project_config_file = os.path.join(project_root, "storage_config.json")
    if os.path.exists(project_config_file):
        try:
            with open(project_config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
                if config.get("storage_path"):
                    path = config["storage_path"]
                    if os.path.exists(path):
                        return path
        except Exception:
            pass

    return data_dir


class Settings(BaseSettings):
    """系统配置"""
    # 服务器配置
    server_host: str = "127.0.0.1"
    server_port: int = 15920
    server_debug: bool = False
    # 调试/管理开关：允许通过接口查询历史版本（include_history、版本链等）
    allow_history_query: bool = False

    # CORS 配置
    # - 开发环境：Vite DevServer（默认 5173）
    # - 生产环境：Electron file:// 场景通常会携带 Origin: null
    #   （因此需要显式允许 "null"，或通过 allow_origin_regex 匹配）
    cors_allow_origins_dev: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    cors_allow_origins_prod: List[str] = ["null"]
    cors_allow_origin_regex_prod: str = r"^(null|file://.*|app://.*)$"
    
    # 数据库配置
    database_path: Optional[str] = None
    backup_path: Optional[str] = None
    
    # 嵌入配置
    embedding_provider: str = "bge-m3"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimensions: int = 1024
    embedding_max_length: int = 512
    embedding_device: str = "auto"
    embedding_batch_size: int = 32
    enable_bge_m3: bool = True
    
    # 检索配置
    retrieval_strategy: str = "hybrid"
    retrieval_top_k: int = 10
    vector_weight: float = 0.5
    bm25_weight: float = 0.3
    entity_weight: float = 0.2
    mmr_lambda: float = 0.5
    min_relevance_score: float = 0.3
    enable_dynamic_weight: bool = True
    enable_spreading_activation: bool = True
    enable_rrf: bool = True
    enable_bm25: bool = True
    enable_cross_encoder: bool = True
    cross_encoder_top_k: int = 20
    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    enable_bge_reranker: bool = True
    bge_reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_top_k: int = 20
    enable_graph_rag: bool = True
    graph_rag_max_hops: int = 2
    graph_rag_top_k: int = 5
    enable_self_rag: bool = True
    self_rag_relevance_threshold: float = 0.6
    self_rag_confidence_threshold: float = 0.7
    enable_multimodal: bool = True
    enable_hyde: bool = True
    enable_query_rewrite: bool = True
    enable_faiss: bool = True
    enable_hnsw: bool = True
    faiss_index_type: str = "hnsw"
    faiss_ef_search: int = 64
    hnsw_ef_construction: int = 200
    hnsw_m: int = 16
    
    # Qdrant配置
    qdrant_enabled: bool = True
    qdrant_mode: str = "local"
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_grpc_port: int = 6334
    qdrant_api_key: Optional[str] = None
    qdrant_use_grpc: bool = True
    qdrant_prefer_grpc: bool = True
    qdrant_collection_name: str = "diamond_memory"
    qdrant_path: Optional[str] = None
    
    # 记忆配置
    short_term_days: int = 7
    dedup_threshold: float = 0.85
    conflict_threshold: float = 0.3
    decay_rate: float = 0.1
    max_tokens_per_query: int = 500
    max_content_length: int = 10000
    max_tags: int = 5
    raw_record_retention_days: int = -1

    chat_memory_limit_greeting: int = 3
    chat_memory_limit_normal: int = 6
    chat_greeting_recent_n: int = 30
    chat_greeting_min_score: float = 0.55
    chat_auto_summary_enabled: bool = True
    chat_auto_summary_trigger_token: int = 300
    chat_auto_summary_max_tokens: int = 600

    # OpenClaw 偏好召回兜底（P0）
    # - categories=preference 查询时启用分层兜底（L4/L6 → L2 → 最近 N 条 L1）
    # - embedding 不可用/返回空时，强制走关键词检索并做中文偏好词扩展
    openclaw_preference_enable_l1_fallback: bool = True
    openclaw_preference_l1_recent_n: int = 30
    openclaw_preference_disable_cache: bool = True
    openclaw_preference_keyword_expands: List[str] = ["喜欢", "偏好", "爱", "最爱", "不喜欢", "讨厌", "习惯", "风格", "格式"]

    # L6 技能产品化：自动升级触发阈值（MVP 默认值）
    skill_auto_upgrade_min_invokes: int = 3
    skill_auto_upgrade_min_negative_feedbacks: int = 1
    skill_negative_rating_threshold: int = 2  # <=2 视为负反馈
    
    # 记忆层配置
    l0_retention_days: int = 30
    l0_max_size: int = 10000
    l1_retention_days: int = 365
    l1_max_size: int = 5000
    l2_retention_days: int = 730
    l2_max_size: int = 2000
    l3_max_children: int = 100
    l4_max_children: int = 50
    l5_retention_days: int = -1
    
    # 整合配置
    consolidation_enabled: bool = True
    consolidation_interval_hours: int = 24
    consolidation_batch_size: int = 50
    llm_summarize: bool = True
    llm_model: str = "qwen3.5:4b"
    trigger_mode: str = "time"
    count_threshold: int = 100
    idle_hours: int = 4
    repeated_query_threshold: int = 3
    repeated_query_window_minutes: int = 60
    
    # 本地LLM配置
    local_llm_enabled: bool = True
    llm_provider: str = "ollama"
    local_llm_endpoint: str = "http://127.0.0.1:11434"
    local_llm_model: str = "qwen3.5:4b"
    local_llm_fallback_model: str = "llama3.2"
    local_llm_auto_pull: bool = True
    local_llm_timeout: int = 30
    local_llm_max_tokens: int = 8192
    local_llm_temperature: float = 0.7
    local_llm_top_p: float = 0.9
    
    # 大模型整体开关
    llm_enabled: bool = True
    
    # 外部商用大模型配置
    external_llm_endpoint: str = "https://api.openai.com/v1"
    external_llm_api_key: Optional[str] = None
    external_llm_model: str = "gpt-4o-mini"
    external_llm_max_tokens: int = 8192

    # 打包配置
    l1_to_l2_max_chars: int = 3000
    l2_to_l4_max_chars: int = 4000
    l4_to_l6_max_chars: int = 3000

    # 异步配置
    async_processing_enabled: bool = True
    async_max_workers: int = 1

    # 深度整理低功耗配置
    deep_organize_low_power_enabled: bool = True
    deep_organize_stage_pause_ms: int = 1200
    deep_organize_cleanup_memory_limit: int = 12
    deep_organize_cleanup_directory_limit: int = 6
    deep_organize_dedup_limit: int = 8
    deep_organize_reclassify_limit: int = 6
    deep_organize_l1_batches_per_run: int = 1
    deep_organize_l2_batches_per_run: int = 1
    deep_organize_l4_batches_per_run: int = 1

    # 去重/合并阈值配置（对齐OpenClaw标准：保真写入、保守合并、检索时智能过滤）
    l4_dedup_threshold: float = 0.85
    l6_dedup_threshold: float = 0.85
    l2_to_l4_similarity_threshold: float = 0.85
    l4_to_l6_similarity_threshold: float = 0.85
    merge_output_ratio: float = 1.5
    category_fuzzy_similarity_threshold: float = 0.85

    # 缓存配置
    cache_enabled: bool = True
    cache_max_entries: int = 1000
    cache_default_ttl_seconds: int = 3600
    retrieval_cache_enabled: bool = True
    retrieval_cache_max_size: int = 500
    retrieval_cache_ttl_seconds: int = 300
    embedding_cache_max_size: int = 2000

    # 记忆衰变配置（艾宾浩斯遗忘曲线）
    decay_model: str = "ebbinghaus"
    ebbinghaus_base_retention: float = 0.68
    ebbinghaus_decay_exponent: float = -0.25
    ebbinghaus_review_bonus: float = 0.15
    ebbinghaus_max_review_count: int = 10
    ebbinghaus_importance_factor: float = 0.5

    # GraphRAG增强检索配置
    graph_rag_enabled: bool = True
    graph_rag_spreading_decay: float = 0.5
    graph_rag_max_hops_enhanced: int = 3
    graph_rag_weight: float = 0.3
    graph_rag_min_activation: float = 0.1
    graph_rag_auto_rebuild: bool = True
    graph_rag_rebuild_interval_minutes: int = 30

    # 统一记忆类型配置
    memory_type_enabled: bool = True
    memory_type_default: str = "episodic"
    memory_type_auto_classify: bool = True

    # 矛盾检测配置
    contradiction_detection_enabled: bool = True
    contradiction_similarity_threshold: float = 0.6
    contradiction_llm_verify: bool = True

    # 记忆压缩配置
    memory_compression_enabled: bool = True
    compression_max_chunk_size: int = 3500
    compression_overlap: int = 300
    compression_tree_depth: int = 2

    # 自适应低功耗配置
    adaptive_organize_enabled: bool = True
    adaptive_cpu_threshold: float = 0.8
    adaptive_memory_threshold: float = 0.85
    adaptive_check_interval_seconds: int = 60
    adaptive_min_pause_ms: int = 500
    adaptive_max_pause_ms: int = 3000

    # 实体提取增强配置
    entity_extraction_enhanced: bool = True
    entity_extraction_llm_fallback: bool = True
    entity_extraction_max_entities: int = 20

    # 向量存储引擎选择
    vector_store_engine: str = "qdrant"
    vector_store_auto_migrate: bool = True
    
    # 系统数据目录（数据库、向量库、备份等系统文件，始终在应用安装路径下）
    data_directory: Optional[str] = None
    
    # 用户存储路径（知识库、用户文档等用户数据，可随时变更）
    storage_path: Optional[str] = None
    
    # 自动备份配置
    auto_backup_enabled: bool = False
    auto_backup_interval_hours: int = 24
    auto_backup_max_copies: int = 5
    
    # OpenClaw配置
    openclaw_enabled: bool = True
    openclaw_endpoint: str = "http://localhost:8080"
    openclaw_api_key: Optional[str] = None
    
    # 联网搜索配置
    web_search_enabled: bool = True
    web_search_max_results: int = 5
    web_search_max_content_length: int = 2000
    web_search_timeout: int = 8

    # Hermes Agent配置
    hermes_enabled: bool = True
    hermes_endpoint: str = "http://localhost:18789"
    hermes_api_key: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        resolved_dir = _resolve_data_dir() if self.data_directory is None else self.data_directory
        self.data_directory = resolved_dir
        os.makedirs(self.data_directory, exist_ok=True)
        self._update_paths(resolved_dir)
        _migrate_legacy_storage_config_if_needed(resolved_dir, project_root)
        self.storage_path = _resolve_storage_path(resolved_dir) if self.storage_path is None else self.storage_path
        os.makedirs(self.storage_path, exist_ok=True)
        self._migrate_system_files_if_needed()
    
    def _update_paths(self, data_dir: str):
        """更新系统数据相关路径（数据库、向量库、备份等）"""
        self.database_path = os.path.join(data_dir, "memory.db")
        self.backup_path = os.path.join(data_dir, "backups")
        self.qdrant_path = os.path.join(data_dir, "qdrant_storage")

    def _migrate_system_files_if_needed(self):
        """检测并迁移旧版本系统文件到当前 data_directory。

        历史版本可能将系统文件放在 project_root/data 或 test_new_storage 下。
        新版本要求：运行时写入统一落到 --data-dir（userData）指定目录。
        因此这里仅做“从旧位置搬到新位置”的迁移，绝不写入/创建 project_root 下的新文件。
        """
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

        # 当前 data_directory 已经有数据库，说明无需迁移
        if os.path.exists(os.path.join(self.data_directory, "memory.db")):
            return

        migration_marker = os.path.join(self.data_directory, ".system_migrated")
        if os.path.exists(migration_marker):
            return

        legacy_dirs = [
            os.path.join(project_root, "data"),
            os.path.join(project_root, "test_new_storage"),
        ]

        legacy_dir = None
        for d in legacy_dirs:
            if os.path.abspath(d) == os.path.abspath(self.data_directory):
                continue
            if os.path.exists(os.path.join(d, "memory.db")):
                legacy_dir = d
                break

        if not legacy_dir:
            return

        logger.info(f"[Migration] 检测到旧系统文件，开始迁移到 data_directory: {legacy_dir} -> {self.data_directory}")

        try:
            os.makedirs(self.data_directory, exist_ok=True)
            
            system_items = [
                "memory.db", "memory.db-wal", "memory.db-shm",
                "embedding_index.pkl", "embeddings.pkl",
                "faiss_index.bin", "faiss_meta.json", "qdrant_meta.json",
                ".qdrant_migrated",
                "backups", "qdrant_storage", "temp",
            ]
            
            import shutil
            for item in system_items:
                src = os.path.join(legacy_dir, item)
                dst = os.path.join(self.data_directory, item)
                if os.path.exists(src) and not os.path.exists(dst):
                    try:
                        if os.path.isdir(src):
                            shutil.move(src, dst)
                        else:
                            shutil.move(src, dst)
                        logger.info(f"[Migration] 已迁移: {item}")
                    except Exception as e:
                        logger.warning(f"[Migration] 迁移 {item} 失败: {e}")
                        try:
                            if os.path.isfile(src):
                                shutil.copy2(src, dst)
                        except Exception:
                            pass
            
            with open(migration_marker, "w", encoding="utf-8") as f:
                f.write("migrated")

            logger.info(f"[Migration] 迁移完成: data_directory={self.data_directory}")
        except Exception as e:
            logger.error(f"[Migration] 系统文件迁移失败: {e}")


def _set_hidden(path: str):
    try:
        import sys
        import subprocess
        if sys.platform == 'win32':
            subprocess.run(['attrib', '+h', path], capture_output=True, timeout=10)
        elif sys.platform == 'darwin':
            subprocess.run(['chflags', 'hidden', path], capture_output=True, timeout=10)
    except Exception:
        pass


def _write_storage_config(data_dir: str, storage_path: str = None):
    """写入存储配置文件（系统数据目录 + 用户存储路径）"""
    config_data = {
        "system_data_directory": data_dir,
        "data_directory": data_dir,
        "configured": True
    }
    if storage_path and storage_path != data_dir:
        config_data["storage_path"] = storage_path

    config_file = os.path.join(data_dir, "storage_config.json")
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f, ensure_ascii=False, indent=2)
    _set_hidden(config_file)


def update_data_directory(new_path: str):
    """动态更新系统数据目录（运行时调用）
    
    仅用于初始化或系统数据目录迁移，不影响用户存储路径。
    """
    os.makedirs(new_path, exist_ok=True)

    backups_dir = os.path.join(new_path, "backups")
    qdrant_dir = os.path.join(new_path, "qdrant_storage")
    temp_dir = os.path.join(new_path, "temp")
    
    os.makedirs(backups_dir, exist_ok=True)
    os.makedirs(qdrant_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)
    
    _set_hidden(backups_dir)
    _set_hidden(qdrant_dir)
    _set_hidden(temp_dir)
    
    settings.data_directory = new_path
    settings._update_paths(new_path)
    
    _write_storage_config(new_path, settings.storage_path)
    
    from app.storage import SQLiteStore
    SQLiteStore._instance = None
    store = SQLiteStore()
    store.set_config('knowledge_base_path', settings.storage_path, '知识库存储路径')
    _set_hidden(os.path.join(new_path, "memory.db"))
    _set_hidden(os.path.join(new_path, "memory.db-wal"))
    _set_hidden(os.path.join(new_path, "memory.db-shm"))
    _set_hidden(os.path.join(new_path, "embedding_index.pkl"))
    _set_hidden(os.path.join(new_path, "embeddings.pkl"))

    try:
        from app.services.memory_service import memory_service
        from app.services.retrieval_service import retrieval_service
        from app.services.knowledge_service import knowledge_service
        from app.services.md_export_service import md_export_service
        from app.services.embedding_service import embedding_service
        from app.storage import VectorStore
        from app.api import config_routes
        import app.storage.vector_store as vs_module
        
        new_sqlite_store = SQLiteStore()
        new_vector_store = VectorStore()
        
        vs_module._vector_store_instance = new_vector_store
        
        memory_service.store = new_sqlite_store
        memory_service.vector_store = new_vector_store
        
        retrieval_service.store = new_sqlite_store
        retrieval_service.vector_store = new_vector_store
        
        knowledge_service.store = new_sqlite_store
        
        md_export_service.store = new_sqlite_store
        
        config_routes.store = new_sqlite_store
        
        embedding_service._index_file = os.path.join(new_path, "embedding_index.pkl")
        embedding_service._load_index()
    except Exception as e:
        logger.warning(f"重新加载服务实例失败: {e}")


def update_storage_path(new_storage_path: str):
    """动态更新用户存储路径（运行时调用）
    
    仅变更用户文档/知识库的存放位置，不影响系统数据目录。
    不需要重启后端服务。
    """
    os.makedirs(new_storage_path, exist_ok=True)

    user_dirs = [
        os.path.join(new_storage_path, "总结经验"),
        os.path.join(new_storage_path, "技能"),
        os.path.join(new_storage_path, "用户文档"),
    ]
    for d in user_dirs:
        os.makedirs(d, exist_ok=True)

    old_storage_path = settings.storage_path
    settings.storage_path = new_storage_path

    _write_storage_config(settings.data_directory, new_storage_path)

    try:
        from app.storage import SQLiteStore
        store = SQLiteStore()
        store.set_config('knowledge_base_path', new_storage_path, '知识库存储路径')
        store.set_config('storage_path', new_storage_path, '用户存储路径')
    except Exception as e:
        logger.warning(f"更新存储路径配置失败: {e}")

    logger.info(f"用户存储路径已更新: {old_storage_path} -> {new_storage_path}")


settings = Settings()
