# 设置页移除外部 API 连接设置设计

## 目标

在 `SettingsView` 中去掉“外部API”连接相关设置，仅保留本地模型配置入口。

## 范围

- 修改前端文件：`frontend/src/renderer/views/SettingsView.vue`
- 移除设置页中的“模型来源”里 `外部API` 选项
- 移除设置页中的外部 API 配置表单
- 移除 `SettingsView` 内仅用于外部 API 表单的状态与方法

## 不在本次范围内

- 不修改 `frontend/src/renderer/views/ModelView.vue`
- 不删除后端 `external_llm_*` 配置项
- 不删除后端 `/api/config/test-external` 等接口
- 不清理历史已保存的外部 API 配置数据

## 设计方案

### UI 调整

模型管理区域仅展示“本地模型”视图，不再允许从设置页切换到“外部API”。

### 代码调整

删除以下仅服务于外部 API 配置的前端代码：

- `isSaving`
- `isTesting`
- `testResult`
- `saveExternalConfig()`
- `testExternalConnection()`
- `modelConfig.external`
- `modelConfig.provider` 中与 `external` 相关的切换逻辑

保留以下本地模型相关能力：

- 当前模型显示
- 本地模型列表
- 模型切换
- 模型下载
- 常驻内存开关

## 数据与兼容性

- 后端接口保持不变，避免影响其他页面或后续需求
- 已存在的外部 API 配置不会被删除，只是不再从设置页暴露
- 若其他页面仍依赖外部 API 配置，本次改动不会破坏其功能

## 风险与处理

- 风险：`SettingsView` 仍有代码依赖 `provider === 'external'`
- 处理：同步清理模板条件渲染和脚本中的相关状态，避免死代码和类型问题

- 风险：`/api/config/llm-model` 仍返回 `external` 结构
- 处理：前端继续兼容该返回值，但设置页不再渲染相关内容

## 验证

- 打开设置页，确认不再显示“外部API”按钮和配置表单
- 验证本地模型区域仍可正常展示、切换和下载模型
- 检查 `SettingsView.vue` 的 TypeScript/Vue 诊断，确保无新增错误
