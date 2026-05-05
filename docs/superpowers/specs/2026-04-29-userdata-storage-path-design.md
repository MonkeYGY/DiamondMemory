# 禁止运行时写安装目录（统一落到 userData）设计说明

**目标**：在 macOS `.app` / Windows `Program Files` 等只读安装目录下运行时，后端不会发生任何写入安装目录导致的报错；首次启动无异常；重启后配置仍在；可更改存储路径；保留旧配置读取兼容，但写入迁移到新位置。

## 背景与问题

当前后端 `backend/app/config/settings.py` 在模块 import 阶段就会执行 `settings = Settings()`，并在 `Settings.__init__` 内创建目录、写入配置等。与此同时，默认 `data_directory` 的解析会回退到 `project_root/data`，且 `_write_storage_config()` 会写入 `project_root/storage_config.json`。在打包后的安装场景中，`project_root` 属于安装目录，通常为只读，导致首次启动即可能写入失败。

## 关键原则

1. **所有运行时写入必须落到 `--data-dir` 指定目录**（前端 Electron `userData` 下的后端数据目录）。
2. **安装目录只读**：禁止运行时写入 `project_root` 以及 `project_root/data`。
3. **兼容旧配置读取**：允许读取旧位置的 `storage_config.json` 作为回滚兼容，但一旦确定新位置（`--data-dir`）可用，写入统一迁移到新位置。

## 目录与文件职责（最终态）

以 `data_directory`（`--data-dir`）为根，统一管理“系统写入”：

- `storage_config.json`：运行时配置（系统目录声明 + 用户存储路径声明）
- `memory.db` / `memory.db-wal` / `memory.db-shm`：SQLite 数据库
- `embedding_index.pkl`、`faiss_index.bin`、`faiss_meta.json` 等索引文件
- `qdrant_storage/`：本地 Qdrant 数据目录（或其元数据）
- `temp/`：临时目录
- `backups/`：备份目录

用户可变更的“用户存储路径”（`storage_path`）依然支持自定义（例如知识库/用户文档目录），但**其配置写入**也统一落到 `data_directory/storage_config.json`。

## 参数与解析策略（推荐方案 A）

为避免 `settings` 在 import 阶段就创建/写入默认目录，`settings.py` 必须在解析默认值时就能获取 `--data-dir`：

优先级顺序：
1. 环境变量（例如 `DM_DATA_DIR`，用于兜底）
2. `sys.argv` 中手动扫描得到的 `--data-dir <path>`
3. `data_directory/storage_config.json`（若已存在）
4. 旧位置（只读兼容）：`project_root/storage_config.json`、`project_root/data/storage_config.json`
5. 最终回退：**仍回退到 `--data-dir`（若存在），否则才使用项目内 `data`（仅开发场景）**

说明：在打包场景下，前端会稳定传入 `--data-dir`，因此不会触发写入项目目录；开发场景可继续使用项目内 `data/` 作为默认（可写）。

## 写入策略（关键修复点）

`_write_storage_config(data_dir, storage_path)`：
- 只允许写入 `os.path.join(data_dir, "storage_config.json")`
- **禁止**写入 `project_root/storage_config.json`

## 迁移策略（写入迁移到新位置）

当满足以下条件时触发“迁移写入”：
- 新位置（`data_dir`）不存在 `storage_config.json`
- 旧位置存在可用配置文件

迁移动作：
- 读取旧配置（只读）
- 规范化字段：`system_data_directory=data_dir`，并保留/写入 `storage_path`（若旧配置有）
- 将结果写入新位置 `data_dir/storage_config.json`

## 验收标准映射

- **干净机首次启动无异常**：import 阶段不再触发写安装目录；默认落到 `--data-dir`
- **重启后配置仍在**：`storage_config.json` 位于 `--data-dir` 且可被优先读取
- **可更改存储路径**：`update_storage_path()` 写入 `--data-dir/storage_config.json`，并更新数据库配置项
- **回滚兼容**：仍能读取旧位置配置，但写回迁移到新位置

