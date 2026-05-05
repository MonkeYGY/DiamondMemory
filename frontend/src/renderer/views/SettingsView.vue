<template>
  <div class="view-container">
    <h2>设置</h2>
    <div class="settings-grid">
      <section class="settings-section full-width">
        <h3>外观</h3>
        <div class="setting-row">
          <span class="setting-label">主题模式</span>
          <div class="theme-switcher">
            <button class="theme-option" :class="{ active: currentTheme === 'light' }" @click="setTheme('light')">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
              浅色
            </button>
            <button class="theme-option" :class="{ active: currentTheme === 'dark' }" @click="setTheme('dark')">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
              深色
            </button>
          </div>
        </div>
        <p class="storage-hint">切换应用的浅色/深色外观模式，设置会自动保存。</p>
      </section>

      <section class="settings-section full-width">
        <h3>数据管理</h3>
        <div class="setting-row">
          <span class="setting-label">存储路径</span>
          <span class="setting-value path-value" :title="storagePath">{{ storagePath || '加载中...' }}</span>
        </div>
        <div class="storage-actions">
          <button @click="handleSelectStoragePath" class="btn-secondary" :disabled="storagePathChanging">{{ storagePathChanging ? '切换中...' : '更改存储位置' }}</button>
          <button @click="handleSyncKnowledge" class="btn-primary" :disabled="storagePathChanging || syncingKnowledge">
            {{ syncingKnowledge ? '同步中...' : '🔄 同步知识库（扫描并入库）' }}
          </button>
        </div>
        <p class="storage-hint">存储路径表示当前工作区根目录。切换后会同步切换记忆数据库、知识库文档、图谱数据和用户文档，设置会在重启后继续生效。</p>
        <div class="setting-row mt-4">
          <span class="setting-label">备份路径</span>
          <span class="setting-value path-value" :title="backupPath">{{ backupPath || '桌面/钻石记忆系统' }}</span>
        </div>
        <div class="storage-actions">
          <button @click="handleSelectBackupPath" class="btn-secondary">更改备份路径</button>
          <button @click="handleBackupData" class="btn-primary" :disabled="isBackingUp">{{ isBackingUp ? '备份中...' : '立即备份' }}</button>
        </div>
        <p class="storage-hint">点击备份将存储文件夹打包为压缩包保存到备份路径下。</p>
        <div class="sub-title mt-4">数据库自动备份</div>
        <div class="setting-row">
          <span class="setting-label">启用自动备份</span>
          <label class="switch"><input type="checkbox" v-model="autoBackupEnabled" @change="saveAutoBackupConfig" /><span class="slider round"></span></label>
          <span class="keep-alive-hint">{{ autoBackupEnabled ? '开启：按设定间隔自动备份数据库' : '关闭：需手动备份' }}</span>
        </div>
        <div class="setting-row" v-if="autoBackupEnabled">
          <span class="setting-label">备份间隔</span>
          <select v-model="autoBackupInterval" @change="saveAutoBackupConfig" class="interval-select">
            <option value="1">每1小时</option>
            <option value="4">每4小时</option>
            <option value="8">每8小时</option>
            <option value="12">每12小时</option>
            <option value="24">每24小时</option>
            <option value="48">每48小时</option>
            <option value="168">每7天</option>
          </select>
        </div>
        <div class="setting-row" v-if="autoBackupEnabled">
          <span class="setting-label">最大备份份数</span>
          <select v-model="autoBackupMaxCopies" @change="saveAutoBackupConfig" class="interval-select">
            <option value="3">3份</option>
            <option value="5">5份</option>
            <option value="10">10份</option>
            <option value="20">20份</option>
          </select>
        </div>
        <div class="storage-actions" v-if="autoBackupEnabled">
          <button @click="handleBackupNow" class="btn-secondary" :disabled="isBackingUp">{{ isBackingUp ? '备份中...' : '立即执行一次备份' }}</button>
        </div>
        <p class="storage-hint" v-if="autoBackupEnabled">自动备份将数据库文件复制到系统数据目录的 backups 文件夹下，超出最大份数时自动删除最旧的备份。</p>
      </section>

      <section class="settings-section full-width">
        <h3>记忆整理</h3>
        <div class="setting-row">
          <span class="setting-label">自动整理</span>
          <label class="switch"><input type="checkbox" v-model="autoOrganizeEnabled" @change="saveAutoOrganize" /><span class="slider round"></span></label>
          <span class="keep-alive-hint">{{ autoOrganizeEnabled ? '开启：根据内容量(约4000字)自动触发整理' : '关闭：需手动点击整理按钮' }}</span>
        </div>
        <p class="storage-hint">整理流程：L1→L2（去重合并）→ L3/L4（LLM归纳分类）→ L5/L6（LLM技能提炼）</p>
      </section>

      <section class="settings-section full-width">
        <h3>高级 / 调试</h3>
        <div class="setting-row">
          <span class="setting-label">允许查询历史版本</span>
          <label class="switch">
            <input type="checkbox" v-model="allowHistoryQuery" @change="saveAllowHistoryQuery" />
            <span class="slider round"></span>
          </label>
          <span class="keep-alive-hint">
            {{ allowHistoryQuery ? '开启：接口可通过 include_history=true 召回历史版本（仅建议排障/管理使用）' : '关闭：默认只召回有效版本（推荐）' }}
          </span>
        </div>
        <p class="storage-hint">说明：开启后将放行 <code>/memory/query?include_history=true</code> 与版本链/状态切换接口（仍不影响默认召回）。</p>
      </section>

      <section class="settings-section full-width">
        <h3>AI软件集成</h3>
        <p class="storage-hint mb-4">配置AI软件与钻石记忆系统的集成，开启后AI软件将自动将对话全量记录到钻石记忆系统。</p>
        <div class="ai-software-grid">
          <div v-for="sw in aiSoftwareList" :key="sw.id" class="ai-software-card" :class="{ configured: sw.configured, 'not-installed': !sw.installed && sw.id !== 'trae' }">
            <span class="ai-card-icon">{{ sw.icon }}</span>
            <div class="ai-card-info">
              <span class="ai-card-name">{{ sw.name }}</span>
              <span class="ai-card-desc">
                <template v-if="sw.id === 'trae'">通过 MCP 协议接入，支持读写记忆</template>
                <template v-else-if="!sw.installed">请先安装 {{ sw.name }}</template>
                <template v-else>
                  <template v-if="sw.version">{{ sw.version }}</template>
                  <template v-if="sw.gatewayRunning"> · Gateway 运行中</template>
                  <template v-if="sw.agentsStatus && sw.agentsStatus.length > 0"> · {{ sw.agentsStatus.map(a => a.name || a.id).join('、') }}</template>
                </template>
              </span>
            </div>
            <div class="ai-card-spacer"></div>
            <span class="ai-card-status">
              <template v-if="sw.id === 'trae'">MCP 手动配置</template>
              <template v-else-if="!sw.installed">未安装</template>
              <template v-else-if="sw.configuring">配置中...</template>
              <template v-else-if="sw.configured">✅ 已配置</template>
              <template v-else>未配置</template>
            </span>
            <div v-if="sw.id === 'trae'" class="ai-card-actions">
              <button class="btn-secondary btn-sm" @click="copyMcpConfigQuick">一键复制配置</button>
              <button class="btn-secondary btn-sm" @click="runMcpSelfCheck">一键自检</button>
              <button class="btn-primary btn-sm" @click="openTraeTutorial">配置教程</button>
            </div>
            <button v-else-if="sw.installed && !sw.configured" class="btn-primary btn-sm" @click="configureAISoftware(sw)" :disabled="sw.configuring">{{ sw.configuring ? '配置中...' : '一键配置' }}</button>
            <label class="switch switch-sm" v-if="sw.installed && sw.id !== 'trae'">
              <input type="checkbox" :checked="sw.configured" @change="toggleAISoftware(sw)" :disabled="sw.configuring" />
              <span class="slider round"></span>
            </label>
            <div class="ai-agent-switches" v-if="sw.installed && sw.id !== 'trae' && sw.agentsStatus && sw.agentsStatus.length > 0">
              <div class="ai-agent-switch" v-for="agent in sw.agentsStatus" :key="agent.id">
                <span class="ai-agent-name">{{ agent.name || agent.id }}</span>
                <label class="switch switch-xs">
                  <input type="checkbox" :checked="agent.integrated" @change="toggleAISoftware(sw, agent.id)" :disabled="agent.configuring" />
                  <span class="slider round"></span>
                </label>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="settings-section full-width">
        <h3>模型管理</h3>
        <div class="model-provider-row">
          <span class="setting-label">模型来源</span>
          <span class="setting-value">🏠 本地模型</span>
        </div>
        <div class="model-keep-alive-row">
          <span class="setting-label">模型常驻内存</span>
          <label class="switch"><input type="checkbox" v-model="keepAliveEnabled" @change="saveKeepAlive" /><span class="slider round"></span></label>
          <span class="keep-alive-hint">{{ keepAliveEnabled ? '开启：模型加载后常驻内存，响应更快' : '关闭：模型闲置后自动卸载，节省资源' }}</span>
        </div>

        <div class="local-model-section">
          <div v-if="setupPhase === 'need_ollama'" class="setup-wizard">
            <div class="wizard-step active">
              <div class="step-header">
                <span class="step-number">1</span>
                <div class="step-info">
                  <h4>下载 AI 引擎 (Ollama)</h4>
                  <p class="step-desc">Ollama 是本地 AI 推理引擎，首次使用需要下载（约 100 MB）</p>
                </div>
              </div>
              <div class="step-body" v-if="!ollamaDownloadStarted">
                <button class="btn-primary btn-download-ollama" @click="startOllamaDownload" :disabled="ollamaDownloading">
                  {{ ollamaDownloading ? '下载中...' : '开始下载 Ollama' }}
                </button>
              </div>
              <div class="step-body" v-else>
                <div v-if="ollamaDownloadStatus.status === 'downloading'" class="progress-section">
                  <div class="progress-bar"><div class="progress-fill" :style="{ width: ollamaDownloadStatus.progress + '%' }"></div></div>
                  <div class="progress-meta">
                    <span>{{ formatSize(ollamaDownloadStatus.downloaded) }} / {{ formatSize(ollamaDownloadStatus.total || 0) }}</span>
                    <span>{{ ollamaDownloadStatus.speed }}</span>
                  </div>
                  <button class="btn-cancel" @click="cancelOllamaDownload">取消</button>
                </div>
                <div v-else-if="ollamaDownloadStatus.status === 'completed'" class="step-success">
                  <span class="success-icon">✅</span>
                  <span>Ollama 下载完成，正在自动启动...</span>
                </div>
                <div v-else-if="ollamaDownloadStatus.status === 'failed'" class="step-error">
                  <span>❌ 下载失败：{{ ollamaDownloadStatus.error || '未知错误' }}</span>
                  <button class="btn-retry" @click="startOllamaDownload">重试</button>
                </div>
              </div>
            </div>

            <div class="wizard-step disabled">
              <div class="step-header">
                <span class="step-number">2</span>
                <div class="step-info">
                  <h4>下载大模型</h4>
                  <p class="step-desc">下载完成后在此处安装 LLM 和 Embedding 模型</p>
                </div>
              </div>
            </div>

            <div class="wizard-step disabled">
              <div class="step-header">
                <span class="step-number">3</span>
                <div class="step-info">
                  <h4>重启并启用</h4>
                  <p class="step-desc">所有组件就绪后重启软件以激活大模型功能</p>
                </div>
              </div>
            </div>
          </div>

          <div v-else-if="setupPhase === 'need_models'" class="setup-wizard">
            <div class="wizard-step active">
              <div class="step-header">
                <span class="step-number">1</span>
                <div class="step-info">
                  <h4>下载大模型</h4>
                  <p class="step-desc">嵌入模型 bge-m3 为必选，主模型可选（推荐 qwen3.5:4b 多模态）</p>
                </div>
              </div>
              <div class="step-body">
                <div class="model-rows">
                  <div v-for="rec in visibleDefaultModels" :key="rec.name" class="model-row download-row" :class="{ installed: isModelInstalled(rec.name) }">
                    <span class="model-row-icon">{{ rec.icon }}</span>
                    <span class="model-row-name">{{ rec.name }}</span>
                    <span v-if="rec.required" class="badge badge-required">必选</span>
                    <span v-else-if="rec.recommended" class="badge badge-recommended">推荐</span>
                    <span class="model-row-desc">{{ rec.description }}</span>
                    <span class="model-row-size">{{ rec.sizeHint }}</span>
                    <div v-if="isModelInstalled(rec.name)" class="rec-status installed">✅ 已安装</div>
                    <div v-else-if="getPullStatus(rec.name)?.status === 'pulling'" class="rec-status pulling">
                      <div class="progress-bar"><div class="progress-fill" :style="{ width: getPullStatus(rec.name).progress + '%' }"></div></div>
                      <span class="progress-text">{{ getPullStatus(rec.name).progress }}%</span>
                      <button class="btn-cancel" @click="cancelPull(rec.name)">取消</button>
                    </div>
                    <div v-else-if="getPullStatus(rec.name)?.status === 'failed'" class="rec-status failed">
                      ❌ 失败 <button class="btn-retry" @click="pullModel(rec.name)">重试</button>
                    </div>
                    <button v-else class="btn-download" @click="pullModel(rec.name)" :disabled="getPullStatus(rec.name)?.status === 'pulling'">下载</button>
                  </div>
                </div>
                <button class="btn-more-models" @click="showModelLibrary = true">🔍 更多下载模型</button>
              </div>
            </div>
          </div>

          <div v-else-if="setupPhase === 'need_restart'" class="setup-wizard">
            <div v-if="ollamaStatus.model_details.length > 0" class="model-section">
              <div class="sub-title">已安装模型</div>
              <div class="model-rows">
                <div v-for="model in ollamaStatus.model_details" :key="model.name" class="model-item-wrapper">
                  <div class="model-row" :class="{ active: selectedModel === model.name }" @click="selectModel(model.name)">
                    <span class="model-row-icon">📦</span>
                    <span class="model-row-name">{{ model.name }}</span>
                    <span v-if="model.size" class="model-row-size">{{ formatSize(model.size) }}</span>
                    <span v-if="isCurrentModel(model.name)" class="badge current">当前使用</span>
                    <span v-if="model.name.includes('bge-m3')" class="badge embedding">嵌入模型</span>
                    <span class="model-row-spacer"></span>
                    <button v-if="!isCurrentModel(model.name) && !model.name.includes('bge-m3')" class="btn-switch" @click.stop="switchLocalModel(model.name)" :disabled="switchingModel === model.name">{{ switchingModel === model.name ? '切换中...' : '切换' }}</button>
                    <button v-if="!model.name.includes('bge-m3')" class="btn-delete-text" @click.stop="confirmDeleteModel(model.name)">删除</button>
                    <span v-if="model.name.includes('bge-m3')" class="badge required" @click.stop="showEmbeddingInfo = !showEmbeddingInfo">核心依赖 ❓</span>
                  </div>
                  <transition name="info-expand">
                    <div v-if="showEmbeddingInfo && model.name.includes('bge-m3')" class="embedding-info-panel" @click.stop>
                      <div class="info-header">
                        <span class="info-icon">🔢</span>
                        <span class="info-title">为什么 bge-m3 不可删除？</span>
                        <button class="info-close" @click.stop="showEmbeddingInfo = false">✕</button>
                      </div>
                      <div class="info-body">
                        <p><strong>bge-m3 是语义嵌入模型，不是大语言模型（LLM）。</strong>它不能用于对话生成，而是负责将文本转化为 1024 维高精度语义向量，供数据库进行语义检索和相似度匹配。</p>
                        <ul>
                          <li><strong>核心功能</strong>：为记忆数据生成语义向量，支撑"按语义搜索记忆"的核心能力</li>
                          <li><strong>删除后果</strong>：系统将降级为 TF-IDF（仅 384 维，基于词频统计），检索精度和语义理解能力严重下降</li>
                          <li><strong>自动恢复</strong>：即使删除，下次启动时系统会自动重新下载，删除无实际意义</li>
                        </ul>
                      </div>
                    </div>
                  </transition>
                </div>
              </div>
            </div>

            <div class="model-section">
              <div class="sub-title">可选模型</div>
              <div class="model-rows">
                <div v-for="rec in visibleDefaultModels" :key="rec.name" class="model-row download-row" :class="{ installed: isModelInstalled(rec.name) }">
                  <span class="model-row-icon">{{ rec.icon }}</span>
                  <span class="model-row-name">{{ rec.name }}</span>
                  <span v-if="rec.required" class="badge badge-required">必选</span>
                  <span v-else-if="rec.recommended" class="badge badge-recommended">推荐</span>
                  <span class="model-row-desc">{{ rec.description }}</span>
                  <span class="model-row-size">{{ rec.sizeHint }}</span>
                  <div v-if="isModelInstalled(rec.name)" class="rec-status installed">✅ 已安装</div>
                  <div v-else-if="getPullStatus(rec.name)?.status === 'pulling'" class="rec-status pulling">
                    <div class="progress-bar"><div class="progress-fill" :style="{ width: getPullStatus(rec.name).progress + '%' }"></div></div>
                    <span class="progress-text">{{ getPullStatus(rec.name).progress }}%</span>
                    <button class="btn-cancel" @click="cancelPull(rec.name)">取消</button>
                  </div>
                  <div v-else-if="getPullStatus(rec.name)?.status === 'failed'" class="rec-status failed">
                    ❌ 失败 <button class="btn-retry" @click="pullModel(rec.name)">重试</button>
                  </div>
                  <button v-else class="btn-download" @click="pullModel(rec.name)" :disabled="getPullStatus(rec.name)?.status === 'pulling'">下载</button>
                </div>
              </div>
              <button class="btn-more-models" @click="showModelLibrary = true">🔍 更多下载模型</button>
            </div>
          </div>

          <div v-else-if="ollamaStatus.running">
            <div class="sub-title">已安装模型</div>
            <div v-if="ollamaStatus.model_details.length === 0" class="empty-hint">暂无已安装模型</div>
            <div v-else class="model-rows">
              <div v-for="model in ollamaStatus.model_details" :key="model.name" class="model-item-wrapper">
                <div class="model-row" :class="{ active: selectedModel === model.name }" @click="selectModel(model.name)">
                  <span class="model-row-icon">📦</span>
                  <span class="model-row-name">{{ model.name }}</span>
                  <span v-if="model.size" class="model-row-size">{{ formatSize(model.size) }}</span>
                  <span v-if="isCurrentModel(model.name)" class="badge current">当前使用</span>
                  <span v-if="model.name.includes('bge-m3')" class="badge embedding">嵌入模型</span>
                  <span class="model-row-spacer"></span>
                  <button v-if="!isCurrentModel(model.name) && !model.name.includes('bge-m3')" class="btn-switch" @click.stop="switchLocalModel(model.name)" :disabled="switchingModel === model.name">{{ switchingModel === model.name ? '切换中...' : '切换' }}</button>
                  <button v-if="!model.name.includes('bge-m3')" class="btn-delete-text" @click.stop="confirmDeleteModel(model.name)">删除</button>
                  <span v-if="model.name.includes('bge-m3')" class="badge required" @click.stop="showEmbeddingInfo = !showEmbeddingInfo">核心依赖 ❓</span>
                </div>
                <transition name="info-expand">
                  <div v-if="showEmbeddingInfo && model.name.includes('bge-m3')" class="embedding-info-panel" @click.stop>
                    <div class="info-header">
                      <span class="info-icon">🔢</span>
                      <span class="info-title">为什么 bge-m3 不可删除？</span>
                      <button class="info-close" @click.stop="showEmbeddingInfo = false">✕</button>
                    </div>
                    <div class="info-body">
                      <p><strong>bge-m3 是语义嵌入模型，不是大语言模型（LLM）。</strong>它不能用于对话生成，而是负责将文本转化为 1024 维高精度语义向量，供数据库进行语义检索和相似度匹配。</p>
                      <ul>
                        <li><strong>核心功能</strong>：为记忆数据生成语义向量，支撑"按语义搜索记忆"的核心能力</li>
                        <li><strong>删除后果</strong>：系统将降级为 TF-IDF（仅 384 维，基于词频统计），检索精度和语义理解能力严重下降</li>
                        <li><strong>自动恢复</strong>：即使删除，下次启动时系统会自动重新下载，删除无实际意义</li>
                      </ul>
                    </div>
                  </div>
                </transition>
              </div>
            </div>

            <div class="sub-title mt-4">可选模型</div>
            <div class="model-rows">
              <div v-for="rec in visibleDefaultModels" :key="rec.name" class="model-row download-row" :class="{ installed: isModelInstalled(rec.name) }">
                <span class="model-row-icon">{{ rec.icon }}</span>
                <span class="model-row-name">{{ rec.name }}</span>
                <span v-if="rec.required" class="badge badge-required">必选</span>
                <span v-else-if="rec.recommended" class="badge badge-recommended">推荐</span>
                <span class="model-row-desc">{{ rec.description }}</span>
                <span class="model-row-size">{{ rec.sizeHint }}</span>
                <div v-if="isModelInstalled(rec.name)" class="rec-status installed">✅ 已安装</div>
                <div v-else-if="getPullStatus(rec.name)?.status === 'pulling'" class="rec-status pulling">
                  <div class="progress-bar"><div class="progress-fill" :style="{ width: getPullStatus(rec.name).progress + '%' }"></div></div>
                  <span class="progress-text">{{ getPullStatus(rec.name).progress }}%</span>
                  <button class="btn-cancel" @click="cancelPull(rec.name)">取消</button>
                </div>
                <div v-else-if="getPullStatus(rec.name)?.status === 'failed'" class="rec-status failed">
                  ❌ 失败 <button class="btn-retry" @click="pullModel(rec.name)">重试</button>
                </div>
                <button v-else class="btn-download" @click="pullModel(rec.name)" :disabled="getPullStatus(rec.name)?.status === 'pulling'">下载</button>
              </div>
            </div>

            <button class="btn-more-models" @click="showModelLibrary = true">🔍 更多下载模型</button>
          </div>
          <div v-else class="ollama-offline">
            <div class="empty-icon">🔌</div>
            <p>Ollama 服务未启动</p>
            <p class="hint">请重启软件以自动启动内嵌的 Ollama 服务</p>
          </div>
        </div>
      </section>

      <section class="settings-section full-width">
        <h3>数据与卸载</h3>
        <div class="setting-row">
          <span class="setting-label">数据目录</span>
          <span class="setting-value path-value" :title="storageInfo.userDataPath">{{ storageInfo.userDataPath || '加载中...' }}</span>
        </div>
        <p class="storage-hint">所有应用数据（数据库、模型、Ollama、配置等）均存储在此目录下。删除应用后，此目录仍会保留。</p>
        <div class="setting-row mt-4">
          <span class="setting-label">完全卸载</span>
          <button class="btn-uninstall" @click="showUninstallConfirm = true; uninstallKeepData = false; uninstallConfirmText = ''" :disabled="isUninstalling">
            🗑️ 完全卸载并清理数据
          </button>
        </div>
        <p class="storage-hint uninstall-warning">⚠️ 完全卸载将删除应用的所有数据，包括：记忆数据库、向量索引、下载的模型、Ollama 程序、配置文件等。此操作不可恢复，请先备份重要数据。</p>
      </section>

      <section class="settings-section full-width">
        <h3>关于</h3>
        <div class="setting-row"><span class="setting-label">版本</span><span class="setting-value">{{ appInfo.version }}</span></div>
        <div class="setting-row"><span class="setting-label">平台</span><span class="setting-value">{{ platformName }}</span></div>
        <div class="setting-row"><span class="setting-label">环境</span><span class="setting-value">{{ appInfo.isPackaged ? '生产' : '开发' }}</span></div>
        <div class="setting-row"><span class="setting-label">核心服务</span><span class="setting-value"><span class="status-dot" :class="{ online: backendStatus.isRunning }"></span>{{ backendStatus.isRunning ? '运行中' : '已停止' }}</span></div>
        <div class="setting-row"><span class="setting-label">Ollama</span><span class="setting-value"><span class="status-dot" :class="{ online: ollamaRunning }"></span>{{ ollamaRunning ? '已连接' : '未连接' }}</span></div>
        <div class="setting-row"><span class="setting-label">当前模型</span><span class="setting-value">{{ currentModelName || '未配置' }}</span></div>
        <div class="setting-row">
          <span class="setting-label">检查更新</span>
          <button class="btn-check-update" @click="handleCheckForUpdates" :disabled="isCheckingUpdate">
            {{ isCheckingUpdate ? '检查中...' : '立即检查' }}
          </button>
        </div>
        <p class="about-text mt-4">钻石记忆系统 V0.4 - 跨平台智能记忆管理系统</p>
        <p class="about-text">基于Electron + Vue3构建，支持Mac和Windows双平台</p>
      </section>
    </div>

    <transition name="modal-fade">
      <div v-if="showDeleteConfirm" class="modal-overlay" @click.self="showDeleteConfirm = false">
        <div class="modal modal-small">
          <h3>确认删除模型</h3>
          <p class="confirm-text">确定要删除模型 <strong>{{ deletingModel }}</strong> 吗？此操作将删除模型文件，不可恢复。</p>
          <div class="modal-actions">
            <button @click="showDeleteConfirm = false" class="btn-secondary">取消</button>
            <button @click="deleteModel" class="btn-danger" :disabled="isDeleting">{{ isDeleting ? '删除中...' : '确认删除' }}</button>
          </div>
        </div>
      </div>
    </transition>

    <transition name="modal-fade">
      <div v-if="showModelLibrary" class="modal-overlay" @click.self="showModelLibrary = false">
        <div class="modal modal-large">
          <div class="modal-header-row">
            <h3>模型库</h3>
            <button class="close-btn" @click="showModelLibrary = false">✕</button>
          </div>
          <div class="library-search">
            <input v-model="librarySearch" type="text" placeholder="搜索模型..." class="input-field" />
          </div>
          <div class="library-grid">
            <div v-for="model in filteredLibrary" :key="model.name" class="library-row">
              <span class="model-row-icon">📦</span>
              <span class="library-name">{{ model.name }}</span>
              <span class="library-desc">{{ model.description }}</span>
              <span class="library-size">{{ model.sizeHint }}</span>
              <div v-if="isModelInstalled(model.name)" class="rec-status installed">✅ 已安装</div>
              <div v-else-if="getPullStatus(model.name)?.status === 'pulling'" class="rec-status pulling">
                <div class="progress-bar"><div class="progress-fill" :style="{ width: getPullStatus(model.name).progress + '%' }"></div></div>
                <span class="progress-text">{{ getPullStatus(model.name).progress }}%</span>
                <button class="btn-cancel" @click="cancelPull(model.name)">取消</button>
              </div>
              <button v-else class="btn-download" @click="pullModel(model.name)" :disabled="getPullStatus(model.name)?.status === 'pulling'">下载</button>
            </div>
          </div>
        </div>
      </div>
    </transition>

    <transition name="modal-fade">
      <div v-if="showUninstallConfirm" class="modal-overlay" @click.self="showUninstallConfirm = false">
        <div class="modal modal-small">
          <h3>⚠️ 确认完全卸载</h3>
          <p class="confirm-text">此操作将卸载钻石记忆系统应用，请选择数据处理方式：</p>
          <div class="uninstall-options">
            <label class="uninstall-option" :class="{ active: !uninstallKeepData }" @click="uninstallKeepData = false">
              <span class="option-radio">{{ !uninstallKeepData ? '◉' : '○' }}</span>
              <span class="option-content">
                <strong>删除所有数据</strong>
                <span class="option-desc">永久删除记忆数据库、向量索引、Ollama 程序和模型、配置文件等，不可恢复</span>
              </span>
            </label>
            <label class="uninstall-option" :class="{ active: uninstallKeepData }" @click="uninstallKeepData = true">
              <span class="option-radio">{{ uninstallKeepData ? '◉' : '○' }}</span>
              <span class="option-content">
                <strong>保留数据文件夹</strong>
                <span class="option-desc">仅卸载应用，系统数据目录（数据库/模型/配置等）将保留；你设置的工作区目录不会被删除</span>
              </span>
            </label>
          </div>
          <p v-if="!uninstallKeepData" class="confirm-text" style="color: var(--color-error);">⚠️ 删除的数据不可恢复，建议先点击"立即备份"保存重要数据。</p>
          <p v-if="uninstallKeepData" class="confirm-text" style="color: var(--color-success);">
            📁 系统数据目录将保留在：{{ storageInfo.userDataPath }}
            <br />
            📁 工作区（你设置的存储路径）不受影响：{{ storagePath || '未设置' }}
          </p>
          <div class="uninstall-confirm-input">
            <label>请输入 <strong>确认卸载</strong> 以继续：</label>
            <input v-model="uninstallConfirmText" type="text" class="input-field" placeholder="确认卸载" />
          </div>
          <div class="modal-actions">
            <button @click="showUninstallConfirm = false" class="btn-secondary">取消</button>
            <button @click="handleUninstall" class="btn-danger" :disabled="uninstallConfirmText !== '确认卸载' || isUninstalling">{{ isUninstalling ? '卸载中...' : '确认卸载' }}</button>
          </div>
        </div>
      </div>
    </transition>

    <transition name="modal-fade">
      <div v-if="showTraeTutorial" class="modal-overlay" @click.self="showTraeTutorial = false">
        <div class="modal modal-tutorial">
          <div class="modal-header-row">
            <h3>💎 Trae 接入钻石记忆系统 — MCP 配置教程</h3>
            <button class="close-btn" @click="showTraeTutorial = false">✕</button>
          </div>

          <div class="tutorial-content">
            <div class="tutorial-section">
              <div class="tutorial-section-title">📌 什么是 MCP？</div>
              <p class="tutorial-text">MCP (Model Context Protocol) 是一种标准化协议，让 AI 编程工具能够调用外部系统的能力。配置后，Trae 将获得钻石记忆系统的以下能力：</p>
              <ul class="tutorial-list">
                  <li>🔍 搜索记忆库（search_memories）</li>
                  <li>➕ 写入记忆（create_memory）</li>
                  <li>🧪 一键自检（get_startup_status）</li>
              </ul>
            </div>

            <div class="tutorial-section">
              <div class="tutorial-section-title">📋 前提条件</div>
              <div class="tutorial-checklist">
                <div class="tutorial-check" :class="{ checked: backendStatus.isRunning }">
                  <span class="check-icon">{{ backendStatus.isRunning ? '✅' : '⬜' }}</span>
                  <span>钻石记忆系统后端服务正在运行</span>
                </div>
                <div class="tutorial-check" :class="{ checked: mcpConfigInfo?.mcp_package_installed }">
                  <span class="check-icon">{{ mcpConfigInfo?.mcp_package_installed ? '✅' : '⬜' }}</span>
                  <span>mcp Python 包已安装{{ mcpConfigInfo && !mcpConfigInfo.mcp_package_installed ? '（需执行 pip install mcp）' : '' }}</span>
                </div>
                <div class="tutorial-check" :class="{ checked: mcpConfigInfo?.mcp_server_exists }">
                  <span class="check-icon">{{ mcpConfigInfo?.mcp_server_exists ? '✅' : '⬜' }}</span>
                  <span>MCP Server 脚本存在{{ mcpConfigInfo && !mcpConfigInfo.mcp_server_exists ? '（未找到 mcp_server.py）' : '' }}</span>
                </div>
              </div>
            </div>

            <div class="tutorial-section">
              <div class="tutorial-section-title">📝 配置步骤</div>

              <div class="tutorial-step">
                <div class="step-number">1</div>
                <div class="step-content">
                  <div class="step-title">打开 Trae 的 MCP 设置</div>
                  <ol class="step-ol">
                    <li>打开 Trae IDE</li>
                    <li>点击右上角 <strong>「设置」</strong> 图标（齿轮 ⚙️）</li>
                    <li>在左侧导航栏选择 <strong>「MCP」</strong></li>
                    <li>点击右上角 <strong>「添加」→「手动添加」</strong></li>
                  </ol>
                </div>
              </div>

              <div class="tutorial-step">
                <div class="step-number">2</div>
                <div class="step-content">
                  <div class="step-title">填写 MCP Server 配置</div>
                  <p class="tutorial-text">在配置表单中填写以下信息：</p>
                  <div class="tutorial-form-info">
                    <div class="form-field"><span class="field-label">名称：</span><span class="field-value">diamond-memory</span></div>
                    <div class="form-field"><span class="field-label">类型：</span><span class="field-value">STDIO</span></div>
                  </div>
                  <p class="tutorial-text mt-2">或直接将以下 JSON 配置写入配置文件：</p>
                  <div class="tutorial-code-block">
                    <div class="code-header">
                      <span class="code-lang">JSON</span>
                      <button class="btn-copy" @click="copyMcpConfig">{{ mcpConfigCopied ? '✅ 已复制' : '📋 复制' }}</button>
                    </div>
                    <pre class="code-content">{{ mcpConfigJson }}</pre>
                  </div>
                  <div class="tutorial-tip mt-2">
                    💡 <strong>配置文件位置：</strong>
                    <ul class="tutorial-list" style="margin-top: 4px;">
                      <li><strong>全局配置</strong>：<code>~/.trae/mcp.json</code>（所有项目共享）</li>
                      <li><strong>项目级配置</strong>：<code>项目根目录/.trae/mcp.json</code>（仅当前项目）</li>
                    </ul>
                  </div>
                  <div class="tutorial-tip mt-2" v-if="mcpConfigInfo">
                    🔧 <strong>检测到的路径信息：</strong>
                    <ul class="tutorial-list" style="margin-top: 4px;">
                      <li v-if="mcpConfigInfo.mcp_schema_version">Schema 版本：<code>{{ mcpConfigInfo.mcp_schema_version }}</code></li>
                      <li>Python 路径：<code>{{ mcpConfigInfo.python_path }}</code></li>
                      <li>MCP Server 路径：<code>{{ mcpConfigInfo.mcp_server_path }}</code></li>
                    </ul>
                  </div>
                </div>
              </div>

              <div class="tutorial-step">
                <div class="step-number">3</div>
                <div class="step-content">
                  <div class="step-title">保存并验证</div>
                  <ol class="step-ol">
                    <li>点击 <strong>「保存」</strong> 按钮</li>
                    <li>如 Trae 提示需要重启，请重启 Trae IDE</li>
                    <li>在 MCP 设置页面确认 <strong>diamond-memory</strong> 状态为已连接</li>
                  </ol>
                </div>
              </div>

              <div class="tutorial-step">
                <div class="step-number">4</div>
                <div class="step-content">
                  <div class="step-title">一键自检（推荐第一步）</div>
                  <p class="tutorial-text">配置完成后，优先调用 <code>get_startup_status()</code>，它会检查端口、数据库、向量库、知识库路径、Ollama 状态，并给出可操作的修复建议。</p>
                  <div class="storage-actions">
                    <button class="btn-secondary" @click="runMcpSelfCheck" :disabled="mcpSelfCheckLoading">{{ mcpSelfCheckLoading ? '自检中...' : '运行一键自检' }}</button>
                  </div>
                </div>
              </div>
            </div>

            <div class="tutorial-section">
              <div class="tutorial-section-title">🔧 可用工具</div>
              <p class="tutorial-text">配置成功后，Trae 的 AI 助手将自动获得以下工具：</p>
              <div class="tutorial-tools">
                <div class="tutorial-tool" v-for="tool in (mcpConfigInfo?.tools || [
                  { name: 'search_memories', description: '搜索记忆库', params: 'query、limit、filters' },
                  { name: 'create_memory', description: '写入一条记忆', params: 'content、category、tags、source、layer、metadata' },
                  { name: 'get_startup_status', description: '一键自检（含修复建议）', params: '无' },
                  { name: 'search_knowledge', description: '搜索知识库', params: 'query' },
                  { name: 'get_stats', description: '系统统计信息', params: '无' }
                ])" :key="tool.name">
                  <div class="tool-name">{{ tool.name }}</div>
                  <div class="tool-desc">{{ tool.description }}</div>
                  <div class="tool-params">参数：{{ tool.params }}</div>
                </div>
              </div>
            </div>

            <div class="tutorial-section">
              <div class="tutorial-section-title">✅ 验证配置</div>
              <p class="tutorial-text">在 Trae 的 AI 对话中尝试以下提示词：</p>
              <div class="tutorial-examples">
                <div class="example-item">💬 "先执行一键自检，告诉我有哪些问题要修复"</div>
                <div class="example-item">💬 "请搜索我的记忆：XXX"</div>
                <div class="example-item">💬 "帮我记住：今天完成了XXX功能（source=trae）"</div>
              </div>
              <p class="tutorial-text mt-2">如果 AI 能够调用钻石记忆系统的工具并返回结果，说明配置成功！🎉</p>
            </div>

            <div class="tutorial-section">
              <div class="tutorial-section-title">📜 设置个人规则与项目规则</div>
              <p class="tutorial-text">Trae 支持通过规则文件约束 AI 助手的行为，确保每次交互都遵循你的开发规范。规则分为两级：</p>

              <div class="tutorial-step">
                <div class="step-number">1</div>
                <div class="step-content">
                  <div class="step-title">个人规则（全局生效）</div>
                  <p class="tutorial-text">个人规则对所有项目生效，用于定义通用开发准则。文件位置：</p>
                  <div class="tutorial-code-block">
                    <div class="code-header">
                      <span class="code-lang">路径</span>
                    </div>
                    <pre class="code-content">~/.trae/rules/personal_rules.md</pre>
                  </div>
                  <p class="tutorial-text mt-2">推荐内容模板：</p>
                  <div class="tutorial-code-block">
                    <div class="code-header">
                      <span class="code-lang">Markdown</span>
                    </div>
                    <pre class="code-content"># 个人开发规则

## 核心原则
- 每次任务完成后必须全量记录，禁止延迟或批量补录
- 优先检索历史记忆，避免重复劳动
- 所有配置值禁止硬编码，必须从配置层读取

## 编码规范
- 分层架构：表现层/业务逻辑层/数据模型层，禁止跨层调用
- 命名原则：见名知意，禁止模糊缩写或拼音
- 组件复用：100%复用项目组件库，禁止重复造轮子

## 任务记录
- 每次任务完成后，按规定格式将总结全量记录到钻石记忆系统L1层
- 记录分类：user_profile / project / workflow / knowledge / decision / issue

## 交付要求
- 无编译错误、无冗余代码、无硬编码、符合分层原则
- 每次执行完任务后用中文回答总结内容</pre>
                  </div>
                </div>
              </div>

              <div class="tutorial-step">
                <div class="step-number">2</div>
                <div class="step-content">
                  <div class="step-title">项目规则（项目级生效）</div>
                  <p class="tutorial-text">项目规则仅对当前项目生效，用于定义项目专属规范。文件位置：</p>
                  <div class="tutorial-code-block">
                    <div class="code-header">
                      <span class="code-lang">路径</span>
                    </div>
                    <pre class="code-content">项目根目录/.trae/rules/project_rules.md</pre>
                  </div>
                  <p class="tutorial-text mt-2">推荐内容模板：</p>
                  <div class="tutorial-code-block">
                    <div class="code-header">
                      <span class="code-lang">Markdown</span>
                    </div>
                    <pre class="code-content"># 项目规则

## 技术栈
- 前端：Electron + Vue3 + TypeScript
- 后端：Python/FastAPI
- 模型：Ollama + bge-m3 + qwen系列

## 项目结构
- frontend/ - Electron前端
- backend/ - Python后端

## 编码规范
- 禁止硬编码，所有配置从配置层读取
- 分层架构：表现层/业务逻辑层/数据模型层
- 组件复用，禁止重复造轮子
- 代码无冗余注释

## 任务记录规范
- 每次任务完成后，按规定格式将总结全量记录到钻石记忆系统L1层
- 使用 create_memory 工具，layer=1，category="任务记录"</pre>
                  </div>
                </div>
              </div>

              <div class="tutorial-tip mt-2">
                💡 <strong>规则优先级：</strong>项目规则 > 个人规则。当两者冲突时，以项目规则为准。
              </div>
            </div>

            <div class="tutorial-section">
              <div class="tutorial-section-title">💎 任务总结全量记录到钻石系统L1层</div>
              <p class="tutorial-text">每次任务完成后，AI 助手应将任务总结通过 <code>create_memory</code> 工具写入钻石记忆系统 L1 层（原始数据层），确保所有操作可追溯、可检索。</p>

              <div class="tutorial-step">
                <div class="step-number">1</div>
                <div class="step-content">
                  <div class="step-title">记录格式规范</div>
                  <p class="tutorial-text">content 字段必须按以下结构化格式填写：</p>
                  <div class="tutorial-code-block">
                    <div class="code-header">
                      <span class="code-lang">格式模板</span>
                    </div>
                    <pre class="code-content">【任务记录】
时间：YYYY-MM-DD HH:mm:ss
项目：项目标识
类型：需求/方案/开发/修复/优化/重构/测试/交付
标签：tag1, tag2, tag3
内容：任务详细描述（含用户指令、技术方案、决策过程）
涉及文件：文件路径列表（逗号分隔）
验证情况：测试结果与自测情况</pre>
                  </div>
                </div>
              </div>

              <div class="tutorial-step">
                <div class="step-number">2</div>
                <div class="step-content">
                  <div class="step-title">调用示例</div>
                  <p class="tutorial-text">在 Trae 对话中，AI 助手完成任务后应自动调用：</p>
                  <div class="tutorial-code-block">
                    <div class="code-header">
                      <span class="code-lang">create_memory 调用</span>
                    </div>
                    <pre class="code-content">工具：create_memory
参数：
  content: |
    【任务记录】
    时间：2026-04-29 14:30:00
    项目：DiamondMemory
    类型：开发
    标签：前端, 配置教程, MCP
    内容：在Trae配置教程弹窗中新增个人规则与项目规则设置指南，
          以及任务总结全量记录到L1层的格式规范
    涉及文件：frontend/src/renderer/views/SettingsView.vue
    验证情况：功能自测通过，弹窗正常显示新增内容
  category: "任务记录"
  layer: 1
  tags: ["任务记录", "DiamondMemory", "开发"]
  source: "Trae"</pre>
                  </div>
                </div>
              </div>

              <div class="tutorial-step">
                <div class="step-number">3</div>
                <div class="step-content">
                  <div class="step-title">标签分类规范</div>
                  <p class="tutorial-text">tags 字段应包含以下分类标签（可多选）：</p>
                  <div class="tutorial-tools">
                    <div class="tutorial-tool">
                      <div class="tool-name">user_profile</div>
                      <div class="tool-desc">用户偏好与习惯记录</div>
                    </div>
                    <div class="tutorial-tool">
                      <div class="tool-name">project</div>
                      <div class="tool-desc">项目信息与架构决策</div>
                    </div>
                    <div class="tutorial-tool">
                      <div class="tool-name">workflow</div>
                      <div class="tool-desc">工作流程与操作步骤</div>
                    </div>
                    <div class="tutorial-tool">
                      <div class="tool-name">knowledge</div>
                      <div class="tool-desc">技术知识与经验总结</div>
                    </div>
                    <div class="tutorial-tool">
                      <div class="tool-name">decision</div>
                      <div class="tool-desc">技术决策与选型依据</div>
                    </div>
                    <div class="tutorial-tool">
                      <div class="tool-name">issue</div>
                      <div class="tool-desc">问题记录与解决方案</div>
                    </div>
                  </div>
                </div>
              </div>

              <div class="tutorial-tip mt-2">
                💡 <strong>L1 层特性：</strong>全量写入、不去重、processed_status 默认为 pending。后续系统会自动将 L1 记忆整理到 L2 层（去重合并），再逐层沉淀为结构化知识。你只需确保每次任务都完整记录即可。
              </div>
            </div>
          </div>
        </div>
      </div>
    </transition>

    <transition name="modal-fade">
      <div v-if="showMcpSelfCheck" class="modal-overlay" @click.self="showMcpSelfCheck = false">
        <div class="modal modal-tutorial">
          <div class="modal-header-row">
            <h3>🧪 MCP 一键自检</h3>
            <div class="modal-header-actions">
              <button class="btn-copy" @click="copyMcpSelfCheckResult" :disabled="!mcpSelfCheckResult">{{ mcpSelfCheckCopied ? '✅ 已复制' : '📋 复制结果' }}</button>
              <button class="close-btn" @click="showMcpSelfCheck = false">✕</button>
            </div>
          </div>

          <div class="tutorial-content">
            <div v-if="mcpSelfCheckLoading" class="empty-hint">自检中...</div>
            <div v-else-if="!mcpSelfCheckResult" class="empty-hint">暂无自检结果</div>
            <div v-else>
              <div class="tutorial-section">
                <div class="tutorial-section-title">总体状态</div>
                <p class="tutorial-text">
                  <strong>{{ mcpSelfCheckResult.overall_status }}</strong>
                  <span v-if="mcpSelfCheckResult.mcp_schema_version"> · schema={{ mcpSelfCheckResult.mcp_schema_version }}</span>
                </p>
              </div>

              <div class="tutorial-section">
                <div class="tutorial-section-title">检查项</div>
                <div class="tutorial-tools">
                  <div class="tutorial-tool" v-for="c in mcpSelfCheckResult.checks" :key="c.name">
                    <div class="tool-name">
                      {{ c.name }}
                      <span style="margin-left: 6px;">
                        {{ c.status === 'pass' ? '✅' : c.status === 'degraded' ? '🟡' : '❌' }}
                      </span>
                    </div>
                    <div class="tool-desc">{{ c.message || '' }}</div>
                    <div class="tool-params" v-if="c.suggestion">修复建议：{{ c.suggestion }}</div>
                  </div>
                </div>
              </div>

              <div class="tutorial-section">
                <div class="tutorial-section-title">原始输出（JSON）</div>
                <div class="tutorial-code-block">
                  <div class="code-header">
                    <span class="code-lang">JSON</span>
                  </div>
                  <pre class="code-content">{{ mcpSelfCheckRaw }}</pre>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, inject, type Ref } from 'vue'
import { getBackendStatus, getAppInfo, apiRequest, syncKnowledgeBase, rebuildKnowledgeMemoryExports, restartBackend } from '../api/backend'
import { useInterval } from '../composables/useTimer'
import { APP_CONFIG } from '../config/constants'
import { useToast } from '../composables/useToast'
import { useTheme } from '../composables/useTheme'
import { useTasksStore } from '../stores/tasks'
import { syncKnowledgeTree } from '../utils/knowledge-tree-events'

const toast = useToast()
const tasks = useTasksStore()
const { currentTheme, setTheme } = useTheme()
const startupStatus = inject<Ref<{
  ollama_ready: boolean
  llm_installed: boolean
  llm_loaded: boolean
  embedding_installed: boolean
  embedding_loaded: boolean
  warmup_phase: string
  llm_model_name: string
}>>('startupStatus', ref({
  ollama_ready: false,
  llm_installed: false,
  llm_loaded: false,
  embedding_installed: false,
  embedding_loaded: false,
  warmup_phase: 'idle',
  llm_model_name: '',
}))
const refreshKnowledgeBaseState = inject<(force?: boolean, newPath?: string) => Promise<void>>('refreshKnowledgeBaseState', async () => {})
const restartAutoOrganizeTimer = inject<() => void>('restartAutoOrganizeTimer', () => {})
const setStoragePathChanging = inject<(val: boolean) => void>('setStoragePathChanging', () => {})
const checkForUpdates = inject<(() => void) | undefined>('checkForUpdates', undefined)
const backendStatus = ref<{ isRunning: boolean; port: number }>({ isRunning: false, port: APP_CONFIG.BACKEND_DEFAULT_PORT })
const appInfo = ref({ platform: '', version: '0.4.0', isPackaged: false })
const ollamaRunning = ref(false)
const storagePath = ref('')
const storagePathChanging = ref(false)
const currentModelName = ref('')
const selectedModel = ref('')
const switchingModel = ref('')
const keepAliveEnabled = ref(true)
const allowHistoryQuery = ref(false)
const pullProgress = ref<Record<string, any>>({})
const showDeleteConfirm = ref(false)
const deletingModel = ref('')
const isDeleting = ref(false)
const showModelLibrary = ref(false)
const showEmbeddingInfo = ref(false)
const librarySearch = ref('')
const isBackingUp = ref(false)
const backupPath = ref(localStorage.getItem('dm-backup-path') || '')
const autoOrganizeEnabled = ref(localStorage.getItem('dm-auto-organize') !== 'false')
const autoOrganizeInterval = ref(localStorage.getItem('dm-auto-organize-interval') || '60')
const autoBackupEnabled = ref(false)
const autoBackupInterval = ref('24')
const autoBackupMaxCopies = ref('5')
const isCheckingUpdate = ref(false)
const showUninstallConfirm = ref(false)
const isUninstalling = ref(false)
const uninstallConfirmText = ref('')
const uninstallKeepData = ref(false)
const storageInfo = ref<{ userDataPath: string; ollamaPath: string; ollamaModelPath: string; backendDataPath: string }>({ userDataPath: '', ollamaPath: '', ollamaModelPath: '', backendDataPath: '' })
const showTraeTutorial = ref(false)
const mcpConfigInfo = ref<{ mcp_schema_version?: string; python_path: string; mcp_server_path: string; mcp_server_exists: boolean; mcp_package_installed: boolean; tools: Array<{ name: string; description: string; params: string }> } | null>(null)
const mcpConfigCopied = ref(false)
const showMcpSelfCheck = ref(false)
const mcpSelfCheckLoading = ref(false)
const mcpSelfCheckCopied = ref(false)
const mcpSelfCheckResult = ref<{ overall_status: string; checks: Array<{ name: string; status: string; message?: string; suggestion?: string }>; mcp_schema_version?: string } | null>(null)

function handleCheckForUpdates() {
  isCheckingUpdate.value = true
  if (checkForUpdates) {
    checkForUpdates()
  }
  setTimeout(() => {
    isCheckingUpdate.value = false
  }, 5000)
}

interface AgentInfo {
  id: string
  name: string
  integrated: boolean
  configuring: boolean
}

interface AISoftware {
  id: string
  name: string
  icon: string
  installed: boolean
  configured: boolean
  configuring: boolean
  version: string
  gatewayRunning: boolean
  agents: Array<{ id: string; name: string }>
  agentsStatus: Array<AgentInfo>
}

const aiSoftwareList = ref<AISoftware[]>([
  { id: 'openclaw', name: 'OpenClaw', icon: '🤖', installed: false, configured: false, configuring: false, version: '', gatewayRunning: false, agents: [], agentsStatus: [] },
  { id: 'qclaw', name: 'Qclaw', icon: '🐉', installed: false, configured: false, configuring: false, version: '', gatewayRunning: false, agents: [], agentsStatus: [] },
  { id: 'hermes-agent', name: 'Hermes Agent', icon: '⚡', installed: false, configured: false, configuring: false, version: '', gatewayRunning: false, agents: [], agentsStatus: [] },
  { id: 'trae', name: 'Trae', icon: '💻', installed: true, configured: false, configuring: false, version: '', gatewayRunning: false, agents: [], agentsStatus: [] }
])

const modelConfig = ref({
  model: '', provider: 'local' as 'local' | 'external', llm_enabled: true,
  local: { model: '', endpoint: '' },
  external: { endpoint: '', api_key: '', model: '' }
})

const ollamaStatus = ref({
  running: false, models: [] as string[],
  model_details: [] as Array<{ name: string; size: number; modified_at: string; details: any }>,
  has_model: false, has_embedding_model: false
})

const ollamaInstalled = ref(false)
const ollamaDownloadStarted = ref(false)
const ollamaDownloading = ref(false)
const ollamaDownloadStatus = ref({ status: 'idle', progress: 0, downloaded: 0, total: 0, speed: '', error: '' })
let ollamaProgressTimer: ReturnType<typeof setInterval> | null = null

const defaultModels = [
  { name: 'bge-m3', icon: '🔢', description: '语义嵌入模型，用于高质量向量检索（必装）', sizeHint: '约 1.2 GB', required: true },
  { name: 'qwen3.5:4b', icon: '🧠', description: '推荐多模态 LLM，4B 参数量，支持图片理解与存储，适合日常对话和智能推理', sizeHint: '约 2.5 GB', recommended: true },
  { name: 'qwen3.5:1.7b', icon: '⚡', description: '轻量 LLM 模型，1.7B 参数量，低资源占用快速响应', sizeHint: '约 1.1 GB' },
  { name: 'qwen3.5:14b', icon: '🚀', description: '增强 LLM 模型，14B 参数量，更强的推理和创作能力', sizeHint: '约 9 GB' }
]

const ollamaLibrary = [
  { name: 'qwen2.5:7b', icon: '💬', description: '7B 参数量，更强的推理和创作能力', sizeHint: '约 4.7 GB' },
  { name: 'qwen2.5:1.5b', icon: '⚡', description: '1.5B 轻量模型，低配置设备首选', sizeHint: '约 1.1 GB' },
  { name: 'qwen2.5:14b', icon: '🚀', description: '14B 参数量，专业级推理能力', sizeHint: '约 9 GB' },
  { name: 'llama3.1:8b', icon: '🦙', description: 'Meta Llama 3.1 8B，通用大语言模型', sizeHint: '约 4.7 GB' },
  { name: 'mistral:7b', icon: '🌊', description: 'Mistral 7B，高效开源模型', sizeHint: '约 4.1 GB' },
  { name: 'gemma2:9b', icon: '💎', description: 'Google Gemma 2 9B，高质量对话模型', sizeHint: '约 5.4 GB' },
  { name: 'phi3:3.8b', icon: '🔬', description: 'Microsoft Phi-3 Mini，小型高效模型', sizeHint: '约 2.3 GB' },
  { name: 'deepseek-coder:6.7b', icon: '💻', description: 'DeepSeek Coder，代码生成专用模型', sizeHint: '约 3.8 GB' },
  { name: 'nomic-embed-text', icon: '📄', description: '文本嵌入模型，轻量级替代方案', sizeHint: '约 274 MB' },
  { name: 'mxbai-embed-large', icon: '📊', description: 'Mixed Bread 大型嵌入模型', sizeHint: '约 670 MB' }
]

const setupPhase = computed((): 'need_ollama' | 'need_models' | 'need_restart' | 'normal' => {
  if (ollamaInstalled.value && ollamaStatus.value.running) {
    const hasEmbedding = ollamaStatus.value.has_embedding_model
    const hasLLM = ollamaStatus.value.has_model
    const hasAnyModel = ollamaStatus.value.models.length > 0
    if (hasEmbedding && hasLLM) {
      if (!startupStatus.value.llm_loaded || !startupStatus.value.embedding_loaded) return 'need_restart'
      return 'normal'
    }
    if (!hasAnyModel) return 'need_models'
    return 'need_models'
  }
  if (ollamaInstalled.value) return 'need_models'
  return 'need_ollama'
})

const visibleDefaultModels = computed(() => {
  return defaultModels.slice(0, 2)
})

const filteredLibrary = computed(() => {
  if (!librarySearch.value) return ollamaLibrary
  const q = librarySearch.value.toLowerCase()
  return ollamaLibrary.filter(m => m.name.toLowerCase().includes(q) || m.description.toLowerCase().includes(q))
})

const platformName = computed(() => {
  const platforms: Record<string, string> = { darwin: 'macOS', win32: 'Windows', linux: 'Linux' }
  return platforms[appInfo.value.platform] || appInfo.value.platform
})

let progressTimer: ReturnType<typeof setInterval> | null = null
const { start: startStatusPoll, stop: stopStatusPoll } = useInterval(refreshStatus, APP_CONFIG.SETTINGS_STATUS_INTERVAL)

onMounted(async () => {
  loadStoragePath()
  refreshStatus().then(async () => {
    await loadStoragePath()
    await Promise.all([
      loadModelConfig(),
      checkOllamaStatus(),
      checkAISoftwareStatus(),
      loadStorageInfo(),
      loadAutoBackupConfig(),
      loadAllowHistoryQueryConfig(),
    ])
  })
  startStatusPoll(); startProgressPolling()
})
onUnmounted(() => { stopStatusPoll(); stopProgressPolling(); stopOllamaPolling() })

function startProgressPolling() { progressTimer = setInterval(async () => { await fetchPullProgress() }, 2000) }
function stopProgressPolling() { if (progressTimer) { clearInterval(progressTimer); progressTimer = null } }

async function refreshStatus() {
  try { backendStatus.value = await getBackendStatus() } catch { backendStatus.value = { isRunning: false, port: APP_CONFIG.BACKEND_DEFAULT_PORT } }
  try { appInfo.value = await getAppInfo() } catch { appInfo.value = { platform: '', version: '0.4.0', isPackaged: false } }
  try { if (backendStatus.value.isRunning) { const c = await apiRequest<{ local?: { model?: string } }>('/api/config/llm-model'); if (c?.local?.model) currentModelName.value = c.local.model } } catch {}
  await checkOllamaStatus()
}

async function loadAllowHistoryQueryConfig() {
  // 该开关仅用于管理/调试：默认关闭；后端未落库时可能返回 404，需兜底为 false
  try {
    const res = await apiRequest<{ key: string; value: string }>('/api/config/get?key=allow_history_query')
    allowHistoryQuery.value = String(res?.value || '').toLowerCase() === 'true'
  } catch {
    allowHistoryQuery.value = false
  }
}

async function saveAllowHistoryQuery() {
  const next = allowHistoryQuery.value
  try {
    await apiRequest('/api/config/set', {
      method: 'POST',
      body: JSON.stringify({
        key: 'allow_history_query',
        value: next ? 'true' : 'false',
        description: '允许查询历史版本（管理/调试）',
      }),
    })
    toast.success(next ? '已开启历史版本查询' : '已关闭历史版本查询')
  } catch (error: any) {
    // 回滚 UI
    allowHistoryQuery.value = !next
    toast.error('更新失败: ' + (error?.message || '未知错误'))
  }
}

async function loadStoragePath() {
  try {
    if (backendStatus.value.isRunning) {
      try {
        const d = await apiRequest<{ path: string; storage_path: string }>('/api/config/storage-path')
        if (d.path || d.storage_path) {
          storagePath.value = d.path || d.storage_path
          return
        }
      } catch {}
    }
    if (window.electronAPI?.getStoragePath) {
      const p = await window.electronAPI.getStoragePath()
      if (p) { storagePath.value = p; return }
    }
  } catch {}
}

async function handleSelectStoragePath() {
  const p = await window.electronAPI?.selectDirectory(); if (!p) return

  // 产品策略（更稳）：切换存储路径必须重启应用，确保后端/模型/端口/数据目录完全按新工作区重新初始化，
  // 避免“部分面板仍显示旧数据/统计数残留/服务断开后重连不一致”等串库与时序问题。
  const confirmed = window.confirm('切换存储路径需要重启应用以确保新工作区完全生效。是否立即重启？')
  if (!confirmed) return

  storagePathChanging.value = true
  setStoragePathChanging(true)
  try {
    // 1) 先更新 Electron 侧 storage-path.json（影响 IPC 允许范围）
    if (window.electronAPI?.setStoragePath) await window.electronAPI.setStoragePath(p)
    if (window.electronAPI?.initStorageDir) await window.electronAPI.initStorageDir(p)
    storagePath.value = p

    // 2) 直接全量重启应用（最稳）：关闭旧服务并按新路径重启所有服务
    if (window.electronAPI?.relaunchApp) {
      toast.info('正在重启应用以切换到新工作区...')
      await window.electronAPI.relaunchApp()
      return
    }

    // 极端兜底：若没有 relaunch 能力（理论上不应发生），回退为仅重启后端
    const restarted = await Promise.race<boolean>([
      restartBackend(),
      new Promise<boolean>((_resolve, reject) => setTimeout(() => reject(new Error('后端重启超时')), 60_000))
    ])
    if (!restarted) throw new Error('后端重启失败')

    // 3) 若未触发 relaunch，则做一次刷新（兼容兜底路径）
    await refreshKnowledgeBaseState(true, p)
    await Promise.all([checkAISoftwareStatus(), loadStorageInfo()])
    toast.success('存储路径已更新并保存，新工作区已生效（未重启应用）')
  } catch (error: any) { toast.error('切换存储路径失败: ' + error.message) }
  finally {
    setStoragePathChanging(false)
    storagePathChanging.value = false
  }
}

const syncingKnowledge = ref(false)

async function handleSyncKnowledge() {
  if (syncingKnowledge.value) return
  syncingKnowledge.value = true
  try {
    const { id } = await syncKnowledgeBase()
    toast.success('已加入任务队列：知识库同步')

    // 让任务面板尽快显示
    await tasks.refresh()
    tasks.startPolling()

    // 轮询直到任务结束（最多 10 分钟）
    const deadline = Date.now() + 10 * 60 * 1000
    while (Date.now() < deadline) {
      const t: any = await apiRequest(`/api/tasks/${id}`)
      if (t.status === 'completed') break
      if (t.status === 'failed' || t.status === 'cancelled') throw new Error(t.error || t.message || '同步失败')
      await new Promise(r => setTimeout(r, 800))
    }

    await syncKnowledgeTree(rebuildKnowledgeMemoryExports)
    toast.success('知识库同步完成')
  } catch (error: any) {
    toast.error('知识库同步失败: ' + (error?.message || '未知错误'))
  } finally {
    syncingKnowledge.value = false
  }
}

async function loadModelConfig() {
  try { modelConfig.value = await apiRequest('/api/config/llm-model'); selectedModel.value = modelConfig.value.local?.model || '' } catch {}
  try {
    const res = await apiRequest<{ key: string; value: string }>('/api/config/get?key=keep_alive')
    keepAliveEnabled.value = String(res.value).trim() === '-1'
  } catch {
    const saved = localStorage.getItem('dm-keep-alive'); keepAliveEnabled.value = saved !== null ? saved === 'true' : true
  }
}

async function checkOllamaStatus() {
  try { ollamaStatus.value = await apiRequest('/api/config/ollama-status') } catch { ollamaStatus.value = { running: false, models: [], model_details: [], has_model: false, has_embedding_model: false } }
  ollamaRunning.value = !!ollamaStatus.value.running
  try {
    const installData: any = await apiRequest('/api/ollama/install-status')
    ollamaInstalled.value = installData.installed
  } catch {}
}

async function fetchPullProgress() {
  try {
    const data = await apiRequest<{ pulls: Record<string, any> }>('/api/config/pull-progress'); pullProgress.value = data.pulls || {}
    const hasActivePull = Object.values(pullProgress.value).some((p: any) => p.status === 'pulling')
    if (!hasActivePull) { const hadCompleted = Object.values(pullProgress.value).some((p: any) => p.status === 'completed'); if (hadCompleted) await checkOllamaStatus() }
  } catch {}
}

function getPullStatus(n: string) { return pullProgress.value[n] || null }
function isModelInstalled(n: string): boolean { return ollamaStatus.value.models.some(m => m === n || m === n + ':latest' || m.replace(':latest', '') === n) }
function isCurrentModel(n: string): boolean { return modelConfig.value.local?.model === n || modelConfig.value.local?.model === n.replace(':latest', '') }
function selectModel(n: string) { selectedModel.value = n }
function formatSize(b: number): string { if (b === 0) return ''; const u = ['B', 'KB', 'MB', 'GB']; let i = 0, s = b; while (s >= 1024 && i < u.length - 1) { s /= 1024; i++ } return s.toFixed(1) + ' ' + u[i] }

async function startOllamaDownload() {
  ollamaDownloadStarted.value = true
  ollamaDownloading.value = true
  ollamaDownloadStatus.value = { status: 'downloading', progress: 0, downloaded: 0, total: 0, speed: '', error: '' }
  try {
    const result = await apiRequest<{ status?: string; message?: string }>('/api/ollama/download', { method: 'POST' })
    if (result?.status === 'already_installed') {
      ollamaDownloadStatus.value.status = 'completed'
      ollamaDownloadStatus.value.progress = 100
      ollamaDownloading.value = false
      stopOllamaPolling()
      toast.success(result?.message || 'Ollama 已就绪')
      setTimeout(async () => { await checkOllamaStatus(); await refreshStatus() }, 500)
      return
    }
    pollOllamaProgress()
  } catch (error: any) {
    ollamaDownloadStatus.value.status = 'failed'
    ollamaDownloadStatus.value.error = error.message || '启动下载失败'
    ollamaDownloading.value = false
  }
}

async function cancelOllamaDownload() {
  try { await apiRequest('/api/ollama/cancel-download', { method: 'POST' }) } catch {}
  stopOllamaPolling()
  ollamaDownloading.value = false
  ollamaDownloadStatus.value.status = 'cancelled'
}

function pollOllamaProgress() {
  stopOllamaPolling()
  ollamaProgressTimer = setInterval(async () => {
    try {
      const data = await apiRequest<any>('/api/ollama/download-progress')
      ollamaDownloadStatus.value = data
      if (data.status === 'idle') {
        await checkOllamaStatus()
        if (ollamaInstalled.value) {
          ollamaDownloadStatus.value = { ...ollamaDownloadStatus.value, status: 'completed', progress: 100 }
          ollamaDownloading.value = false
          stopOllamaPolling()
          setTimeout(async () => { await refreshStatus() }, 500)
          return
        }
      }
      if (data.status === 'completed') {
        ollamaDownloading.value = false
        stopOllamaPolling()
        toast.success('Ollama 下载完成，正在启动服务...')
        setTimeout(async () => { await checkOllamaStatus(); await refreshStatus() }, 2000)
      } else if (data.status === 'failed' || data.status === 'cancelled') {
        ollamaDownloading.value = false
        stopOllamaPolling()
      }
    } catch {}
  }, 1000)
}

function stopOllamaPolling() {
  if (ollamaProgressTimer) { clearInterval(ollamaProgressTimer); ollamaProgressTimer = null }
}

async function switchLocalModel(n: string) {
  switchingModel.value = n
  try {
    await apiRequest('/api/config/switch-model', { method: 'POST', body: JSON.stringify({ model_name: n }) })
    toast.success(`正在切换模型到 ${n}，重启应用后生效...`)
    await new Promise(resolve => setTimeout(resolve, 1500))
    if (window.electronAPI?.relaunchApp) {
      await window.electronAPI.relaunchApp()
    } else {
      toast.error('重启功能不可用，请手动关闭并重新打开软件')
    }
    switchingModel.value = ''
  } catch (error: any) {
    toast.error('切换模型失败: ' + error.message)
    switchingModel.value = ''
  }
}

async function pullModel(n: string) {
  try { const res: any = await apiRequest('/api/config/pull-model', { method: 'POST', body: JSON.stringify({ model_name: n }) }); toast.info(res.status === 'already_pulling' ? `模型 ${n} 正在下载中` : `开始下载模型: ${n}`) } catch (error: any) { toast.error('下载请求失败: ' + error.message) }
}

async function cancelPull(n: string) {
  const name = (n || '').trim()
  if (!name) return
  try {
    await apiRequest('/api/config/cancel-pull', { method: 'POST', body: JSON.stringify({ model_name: name }) })
    toast.info(`已取消下载: ${name}`)
  } catch (error: any) {
    toast.error('取消下载失败: ' + error.message)
  }
}

function confirmDeleteModel(n: string) {
  if (n.includes('bge-m3')) { toast.warning('bge-m3 是核心嵌入模型，不可删除。它负责数据库的语义向量检索，删除将导致检索精度严重下降。'); return }
  deletingModel.value = n; showDeleteConfirm.value = true
}

async function deleteModel() {
  isDeleting.value = true
  try {
    if (window.electronAPI?.deleteModel) {
      const result = await window.electronAPI.deleteModel(deletingModel.value)
      if (result.success) { toast.success(`模型 ${deletingModel.value} 已删除`); showDeleteConfirm.value = false; await checkOllamaStatus() }
      else { toast.error('删除失败: ' + result.error) }
    } else { toast.error('删除模型功能不可用') }
  } catch (error: any) { toast.error('删除异常: ' + error.message) }
  finally { isDeleting.value = false }
}

async function saveKeepAlive() {
  localStorage.setItem('dm-keep-alive', String(keepAliveEnabled.value))
  try {
    await apiRequest('/api/config/set', {
      method: 'POST',
      body: JSON.stringify({ key: 'keep_alive', value: keepAliveEnabled.value ? '-1' : '5m', description: '模型常驻内存策略' })
    })
    if (!keepAliveEnabled.value) {
      await apiRequest('/api/config/unload-models', { method: 'POST' })
    }
    toast.success(keepAliveEnabled.value ? '已开启模型常驻内存' : '已关闭模型常驻内存，模型将在闲置后卸载')
  } catch {
    toast.success(keepAliveEnabled.value ? '已开启模型常驻内存' : '已关闭模型常驻内存')
  }
}

function saveAutoOrganize() {
  localStorage.setItem('dm-auto-organize', String(autoOrganizeEnabled.value))
  localStorage.setItem('dm-auto-organize-interval', autoOrganizeInterval.value)
  restartAutoOrganizeTimer()
  toast.success(autoOrganizeEnabled.value ? `已开启自动整理（间隔${autoOrganizeInterval.value}分钟）` : '已关闭自动整理')
}

async function handleSelectBackupPath() {
  const p = await window.electronAPI?.selectDirectory({ title: '选择备份路径' })
  if (p) { backupPath.value = p; localStorage.setItem('dm-backup-path', p) }
}

async function handleBackupData() {
  isBackingUp.value = true
  try {
    if (window.electronAPI?.backupUserData) {
      const result = await window.electronAPI.backupUserData(backupPath.value, storagePath.value)
      if (result.success) toast.success(`用户数据备份成功！保存至: ${result.path}`)
      else toast.error(`备份失败: ${result.error}`)
    } else if (window.electronAPI?.backupProject) {
      const result = await window.electronAPI.backupProject()
      if (result.success) toast.success(`备份成功！保存至: ${result.path}`)
      else toast.error(`备份失败: ${result.error}`)
    }
  } catch (error: any) { toast.error('备份异常: ' + error.message) }
  finally { isBackingUp.value = false }
}

async function loadStorageInfo() {
  try {
    if (window.electronAPI?.getStorageInfo) {
      storageInfo.value = await window.electronAPI.getStorageInfo()
    }
  } catch {}
}

async function loadAutoBackupConfig() {
  try {
    if (backendStatus.value.isRunning) {
      const d = await apiRequest<{ enabled: boolean; interval_hours: number; max_copies: number }>('/api/config/auto-backup')
      autoBackupEnabled.value = d.enabled
      autoBackupInterval.value = String(d.interval_hours)
      autoBackupMaxCopies.value = String(d.max_copies)
    }
  } catch {}
}

async function saveAutoBackupConfig() {
  try {
    if (backendStatus.value.isRunning) {
      await apiRequest('/api/config/auto-backup', {
        method: 'POST',
        body: JSON.stringify({
          enabled: autoBackupEnabled.value,
          interval_hours: Number(autoBackupInterval.value),
          max_copies: Number(autoBackupMaxCopies.value)
        })
      })
    }
    toast.success(autoBackupEnabled.value ? `已开启自动备份（间隔${autoBackupInterval.value}小时）` : '已关闭自动备份')
  } catch (error: any) {
    toast.error('保存自动备份配置失败: ' + error.message)
  }
}

async function handleBackupNow() {
  isBackingUp.value = true
  try {
    if (backendStatus.value.isRunning) {
      const result = await apiRequest<{ message: string; path: string }>('/api/config/backup-now', { method: 'POST' })
      toast.success(`数据库备份成功！保存至: ${result.path}`)
    } else {
      toast.error('后端服务未运行，无法执行备份')
    }
  } catch (error: any) {
    toast.error('备份失败: ' + error.message)
  } finally {
    isBackingUp.value = false
  }
}

async function handleUninstall() {
  isUninstalling.value = true
  try {
    if (window.electronAPI?.uninstallApp) {
      const result = await window.electronAPI.uninstallApp(uninstallKeepData.value)
      if (result.success) {
        if (uninstallKeepData.value) {
          toast.success('应用将退出，数据文件夹已保留')
        } else {
          toast.success('卸载指令已执行，应用将自动退出并在后台完成数据清理')
        }
      } else {
        const failedPaths = result.details?.filter((d: any) => !d.success).map((d: any) => d.path).join('、') || ''
        if (failedPaths) {
          toast.warning(`部分数据清理失败: ${failedPaths}，应用将退出。主数据目录将在应用退出后自动清理`)
        } else {
          toast.warning('卸载指令已执行，应用将退出')
        }
      }
      showUninstallConfirm.value = false
    } else {
      toast.error('卸载功能不可用')
    }
  } catch (error: any) {
    toast.error('卸载异常: ' + error.message)
  } finally {
    isUninstalling.value = false
  }
}

async function openTraeTutorial() {
  showTraeTutorial.value = true
  mcpConfigCopied.value = false
  if (backendStatus.value.isRunning) {
    try {
      mcpConfigInfo.value = await apiRequest('/api/mcp/config-info')
    } catch {
      mcpConfigInfo.value = null
    }
  } else {
    mcpConfigInfo.value = null
  }
}

async function ensureMcpConfigInfoLoaded() {
  if (!backendStatus.value.isRunning) {
    toast.error('后端未启动，无法获取 MCP 配置')
    return false
  }
  if (mcpConfigInfo.value) return true
  try {
    mcpConfigInfo.value = await apiRequest('/api/mcp/config-info')
    return true
  } catch {
    toast.error('获取 MCP 配置失败，请稍后重试')
    mcpConfigInfo.value = null
    return false
  }
}

const mcpConfigJson = computed(() => {
  const pythonPath = mcpConfigInfo.value?.python_path || '/usr/bin/python3'
  const mcpServerPath = mcpConfigInfo.value?.mcp_server_path || '/path/to/DiamondMemory/backend/mcp_server.py'
  return JSON.stringify({
    mcpServers: {
      'diamond-memory': {
        command: pythonPath,
        args: [mcpServerPath],
        env: {
          DIAMOND_MCP_SOURCE: 'trae'
        }
      }
    }
  }, null, 2)
})

async function copyMcpConfig() {
  try {
    await navigator.clipboard.writeText(mcpConfigJson.value)
    mcpConfigCopied.value = true
    toast.success('配置已复制到剪贴板')
    setTimeout(() => { mcpConfigCopied.value = false }, 2000)
  } catch {
    toast.error('复制失败，请手动复制')
  }
}

async function copyMcpConfigQuick() {
  const ok = await ensureMcpConfigInfoLoaded()
  if (!ok) return
  await copyMcpConfig()
}

const mcpSelfCheckRaw = computed(() => {
  if (!mcpSelfCheckResult.value) return ''
  return JSON.stringify(mcpSelfCheckResult.value, null, 2)
})

async function runMcpSelfCheck() {
  if (!backendStatus.value.isRunning) {
    toast.error('后端未启动，无法自检')
    return
  }
  showMcpSelfCheck.value = true
  mcpSelfCheckCopied.value = false
  mcpSelfCheckLoading.value = true
  try {
    const result = await apiRequest<any>('/api/mcp/self-check')
    mcpSelfCheckResult.value = result as any
    if (result?.overall_status === 'pass') toast.success('自检通过')
    else if (result?.overall_status === 'degraded') toast.info('自检降级可用（可按建议修复）')
    else toast.error('自检失败（请按建议修复）')
  } catch (e: any) {
    mcpSelfCheckResult.value = null
    toast.error('自检失败: ' + (e?.message || '未知错误'))
  } finally {
    mcpSelfCheckLoading.value = false
  }
}

async function copyMcpSelfCheckResult() {
  if (!mcpSelfCheckResult.value) return
  try {
    await navigator.clipboard.writeText(mcpSelfCheckRaw.value)
    mcpSelfCheckCopied.value = true
    toast.success('自检结果已复制到剪贴板')
    setTimeout(() => { mcpSelfCheckCopied.value = false }, 2000)
  } catch {
    toast.error('复制失败，请手动复制')
  }
}

async function checkAISoftwareStatus() {
  try {
    const [openclawResult, qclawResult, hermesResult] = await Promise.all([
      apiRequest<any>('/api/openclaw/check-installation').catch(() => null),
      apiRequest<any>('/api/qclaw/check-installation').catch(() => null),
      apiRequest<any>('/api/hermes/check-installation').catch(() => null)
    ])
    if (openclawResult) {
      const openclaw = aiSoftwareList.value.find(s => s.id === 'openclaw')
      if (openclaw) {
        openclaw.installed = openclawResult.installed || false
        openclaw.version = openclawResult.version || ''
        openclaw.gatewayRunning = openclawResult.gateway_running || false
        openclaw.agents = openclawResult.agents || []
        openclaw.configured = openclawResult.diamond_memory_integrated || false
        openclaw.agentsStatus = (openclawResult.agents_status || []).map((a: any) => ({
          id: a.id || '', name: a.name || '', integrated: a.integrated || false, configuring: false
        }))
      }
    }
    if (qclawResult) {
      const qclaw = aiSoftwareList.value.find(s => s.id === 'qclaw')
      if (qclaw) {
        qclaw.installed = qclawResult.installed || false
        qclaw.version = qclawResult.version || ''
        qclaw.gatewayRunning = qclawResult.gateway_running || false
        qclaw.agents = qclawResult.agents || []
        qclaw.configured = qclawResult.diamond_memory_integrated || false
        qclaw.agentsStatus = (qclawResult.agents_status || []).map((a: any) => ({
          id: a.id || '', name: a.name || '', integrated: a.integrated || false, configuring: false
        }))
      }
    }
    if (hermesResult) {
      const hermes = aiSoftwareList.value.find(s => s.id === 'hermes-agent')
      if (hermes) {
        hermes.installed = hermesResult.installed || false
        hermes.version = hermesResult.version || ''
        hermes.gatewayRunning = hermesResult.gateway_running || false
        hermes.agents = hermesResult.agents || []
        hermes.configured = hermesResult.diamond_memory_integrated || false
        hermes.agentsStatus = (hermesResult.agents_status || []).map((a: any) => ({
          id: a.id || '', name: a.name || '', integrated: a.integrated || false, configuring: false
        }))
      }
    }
  } catch (e) {
    console.error('checkAISoftwareStatus error:', e)
  }
}

async function configureAISoftware(sw: AISoftware, agentId?: string) {
  const apiBase = sw.id === 'openclaw' ? '/api/openclaw' : sw.id === 'qclaw' ? '/api/qclaw' : sw.id === 'hermes-agent' ? '/api/hermes' : null
  if (!apiBase) {
    toast.info(`${sw.name} 一键配置功能开发中，敬请期待`)
    return
  }
  const configuringTarget = agentId
    ? sw.agentsStatus.find(a => a.id === agentId)
    : sw
  if (configuringTarget) configuringTarget.configuring = true
  sw.configuring = true
  try {
    const body = agentId ? JSON.stringify({ agent_id: agentId }) : undefined
    const result = await apiRequest<{ success: boolean; message?: string; error?: string }>(
      `${apiBase}/configure-diamond-memory`,
      { method: 'POST', body }
    )
    if (result.success) {
      if (agentId) {
        const agent = sw.agentsStatus.find(a => a.id === agentId)
        if (agent) agent.integrated = true
      }
      sw.configured = true
      await checkAISoftwareStatus()
      toast.success(result.message || `${sw.name} 钻石记忆系统集成配置完成`)
    } else {
      toast.error(result.error || '配置失败')
    }
  } catch (error: any) {
    toast.error('配置失败: ' + error.message)
  } finally {
    if (configuringTarget) configuringTarget.configuring = false
    sw.configuring = false
  }
}

async function toggleAISoftware(sw: AISoftware, agentId?: string) {
  const apiBase = sw.id === 'openclaw' ? '/api/openclaw' : sw.id === 'qclaw' ? '/api/qclaw' : sw.id === 'hermes-agent' ? '/api/hermes' : null
  if (!apiBase) return
  const isCurrentlyOn = agentId
    ? sw.agentsStatus.find(a => a.id === agentId)?.integrated || false
    : sw.configured
  if (isCurrentlyOn && sw.configuring) return
  const configuringTarget = agentId
    ? sw.agentsStatus.find(a => a.id === agentId)
    : sw
  if (configuringTarget) configuringTarget.configuring = true
  sw.configuring = true
  try {
    const body = agentId ? JSON.stringify({ agent_id: agentId }) : undefined
    if (isCurrentlyOn) {
      const result = await apiRequest<{ success: boolean; message?: string }>(
        `${apiBase}/unconfigure-diamond-memory`,
        { method: 'POST', body }
      )
      if (result.success) {
        if (agentId) {
          const agent = sw.agentsStatus.find(a => a.id === agentId)
          if (agent) agent.integrated = false
        }
        sw.configured = false
        await checkAISoftwareStatus()
        toast.success(result.message || `已关闭 ${sw.name} 钻石记忆系统集成`)
      } else {
        toast.error('关闭失败')
      }
    } else {
      const result = await apiRequest<{ success: boolean; message?: string; error?: string }>(
        `${apiBase}/configure-diamond-memory`,
        { method: 'POST', body }
      )
      if (result.success) {
        if (agentId) {
          const agent = sw.agentsStatus.find(a => a.id === agentId)
          if (agent) agent.integrated = true
        }
        sw.configured = true
        await checkAISoftwareStatus()
        toast.success(result.message || `${sw.name} 钻石记忆系统集成配置完成`)
      } else {
        toast.error(result.error || '配置失败')
      }
    }
  } catch (error: any) {
    toast.error('操作失败: ' + error.message)
  } finally {
    if (configuringTarget) configuringTarget.configuring = false
    sw.configuring = false
  }
}
</script>

<style scoped>
.view-container { padding: 24px; height: 100%; overflow-y: auto; overflow-x: hidden; }
h2 { font-size: 24px; font-weight: 700; color: var(--color-text); margin: 0 0 24px; }
.settings-grid { display: grid; grid-template-columns: 1fr; gap: 20px; width: 100%; min-width: 0; }
.settings-section { background: var(--color-surface); border-radius: 12px; padding: 20px; box-shadow: var(--shadow); border: 1px solid var(--color-border); width: 100%; min-width: 0; box-sizing: border-box; }
.settings-section.full-width { grid-column: 1 / -1; }
.settings-section h3 { font-size: 15px; font-weight: 600; color: var(--color-text); margin: 0 0 16px; padding-bottom: 10px; border-bottom: 1px solid var(--color-border); }
.setting-row { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--color-bg); min-width: 0; }
.setting-row:last-of-type { border-bottom: none; }
.setting-label { color: var(--color-text-secondary); font-size: 13px; flex-shrink: 0; }
.setting-value { color: var(--color-text); font-size: 13px; display: flex; align-items: center; gap: 8px; font-weight: 500; text-align: left; flex: 1 1 auto; min-width: 0; overflow: hidden; }
.path-value { flex: 1 1 auto; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: 'SF Mono', 'Fira Code', monospace; font-size: 12px; text-align: left; margin-left: 12px; min-width: 0; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--color-text-tertiary); flex-shrink: 0; }
.status-dot.online { background: var(--color-success); }
.storage-actions { display: flex; align-items: center; gap: 12px; margin-top: 12px; }
.storage-hint { font-size: 12px; color: var(--color-text-secondary); margin-top: 8px; line-height: 1.5; }
.changing-hint { font-size: 13px; color: var(--color-primary); animation: pulse 1.5s infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

.theme-switcher { display: flex; gap: 8px; }
.theme-option { display: flex; align-items: center; gap: 6px; padding: 8px 16px; border: 1px solid var(--color-border); border-radius: 8px; background: var(--color-surface); color: var(--color-text-secondary); font-size: 13px; font-weight: 500; cursor: pointer; transition: all 0.2s; }
.theme-option:hover { border-color: var(--color-primary); color: var(--color-text); }
.theme-option.active { border-color: var(--color-primary); background: var(--color-primary-bg); color: var(--color-primary); }

.model-provider-row { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid var(--color-bg); }
.provider-tabs { display: flex; gap: 8px; }
.provider-tab { padding: 6px 14px; border: 1px solid var(--color-border); border-radius: 6px; background: var(--color-surface); cursor: pointer; font-size: 13px; font-weight: 500; color: var(--color-text-secondary); transition: all 0.15s; }
.provider-tab.active { border-color: var(--color-primary); background: var(--color-primary-bg); color: var(--color-primary); }
.model-keep-alive-row { display: flex; align-items: center; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--color-bg); }
.keep-alive-hint { font-size: 12px; color: var(--color-text-secondary); }
.switch { position: relative; display: inline-block; width: 40px; height: 22px; }
.switch input { opacity: 0; width: 0; height: 0; }
.slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: var(--color-border); transition: .3s; }
.slider:before { position: absolute; content: ""; height: 16px; width: 16px; left: 3px; bottom: 3px; background-color: white; transition: .3s; }
input:checked + .slider { background-color: var(--color-success); }
input:checked + .slider:before { transform: translateX(18px); }
.slider.round { border-radius: 22px; }
.slider.round:before { border-radius: 50%; }

.setup-wizard { display: flex; flex-direction: column; gap: 12px; padding: 16px 0; }
.wizard-step { border: 1.5px solid var(--color-border); border-radius: 10px; padding: 16px; transition: all 0.2s; }
.wizard-step.active { border-color: var(--color-primary); background: var(--color-primary-bg); }
.wizard-step.disabled { opacity: 0.5; pointer-events: none; }
.wizard-step.done { border-color: var(--color-success); background: var(--color-success-bg); }
.step-header { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 8px; }
.step-number { width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700; color: var(--color-text-secondary); background: var(--color-surface-secondary); flex-shrink: 0; }
.step-number.done { background: var(--color-success); color: white; font-size: 14px; }
.wizard-step.active .step-number { background: var(--color-primary); color: white; }
.step-info h4 { font-size: 14px; font-weight: 600; margin: 0 0 4px; color: var(--color-text); }
.step-desc { font-size: 12px; color: var(--color-text-tertiary); margin: 0; line-height: 1.5; }
.step-body { margin-top: 12px; padding-left: 40px; }
.btn-download-ollama { padding: 10px 24px; background: var(--color-primary); color: var(--color-text-on-primary); border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 500; transition: background 0.15s; }
.btn-download-ollama:hover { background: var(--color-primary-hover); }
.btn-download-ollama:disabled { opacity: 0.6; cursor: not-allowed; }
.progress-section { display: flex; flex-direction: column; gap: 6px; }
.progress-section .progress-bar { height: 6px; background: var(--color-surface-secondary); border-radius: 3px; overflow: hidden; }
.progress-section .progress-fill { height: 100%; background: var(--color-primary); transition: width 0.3s; border-radius: 3px; }
.progress-meta { display: flex; justify-content: space-between; font-size: 11px; color: var(--color-text-tertiary); }
.step-success { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--color-success); }
.step-error { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--color-error); flex-wrap: wrap; }
.success-icon { font-size: 16px; }
.btn-cancel, .btn-retry { padding: 5px 14px; border-radius: 6px; font-size: 12px; cursor: pointer; border: 1px solid var(--color-border); background: transparent; transition: all 0.15s; }
.btn-cancel:hover { background: var(--color-hover-bg); }
.btn-retry { color: var(--color-primary); border-color: var(--color-primary); }
.btn-retry:hover { background: var(--color-primary-bg); }
.download-row .rec-status.pulling { display: flex; align-items: center; gap: 8px; min-width: 180px; }
.download-row .rec-status.pulling .progress-bar { flex: 1; height: 4px; }
.download-row .rec-status.pulling .progress-fill { height: 100%; background: var(--color-primary); border-radius: 2px; }
.download-row .rec-status.pulling .progress-text { font-size: 11px; color: var(--color-primary); min-width: 30px; text-align: right; }
.download-row .btn-download { padding: 4px 14px; background: var(--color-primary); color: var(--color-text-on-primary); border: none; border-radius: 6px; font-size: 12px; cursor: pointer; transition: background 0.15s; }
.download-row .btn-download:hover { background: var(--color-primary-hover); }
.download-row .btn-download:disabled { opacity: 0.5; cursor: not-allowed; }

.sub-title { font-size: 14px; font-weight: 600; color: var(--color-text); margin: 16px 0 10px; }
.model-section { margin: 12px 0; }
.mt-4 { margin-top: 16px; }
.mb-4 { margin-bottom: 16px; }
.empty-hint { font-size: 13px; color: var(--color-text-secondary); padding: 16px 0; }

.model-rows { display: flex; flex-direction: column; gap: 4px; }
.model-row {
  display: flex; align-items: center; gap: 8px; padding: 8px 12px;
  border: 1px solid var(--color-border); border-radius: 6px;
  cursor: pointer; transition: all 0.15s; font-size: 13px;
}
.model-row:hover { border-color: var(--color-border-hover); }
.model-row.active { border-color: var(--color-primary); background: var(--color-primary-bg); }
.model-row.download-row { cursor: default; }
.model-row.download-row.installed { border-color: var(--color-success); background: var(--color-success-bg); }
.model-row-icon { font-size: 14px; flex-shrink: 0; }
.model-row-name { font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 0 1 auto; min-width: 90px; max-width: 150px; }
.model-row-size { font-size: 12px; color: var(--color-text-secondary); white-space: nowrap; }
.model-row-desc { font-size: 12px; color: var(--color-text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; min-width: 0; }
.model-row-spacer { flex: 1; }
.download-row .model-row-size { margin-left: auto; }

.btn-delete-text {
  padding: 2px 8px; border: none; border-radius: 4px;
  background: transparent; cursor: pointer; font-size: 12px;
  color: var(--color-error); font-weight: 500; transition: all 0.15s;
}
.btn-delete-text:hover { background: var(--color-error-bg); }

.badge { padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 500; white-space: nowrap; }
.badge.current { background: var(--color-success); color: var(--color-text-on-primary); }
.badge.embedding { background: var(--color-indigo); color: var(--color-text-on-primary); }
.badge.required { background: var(--color-warning); color: var(--color-text-on-primary); cursor: pointer; user-select: none; padding: 2px 8px; border-radius: 12px; font-size: 11px; }
.badge.recommended { background: var(--color-primary); color: var(--color-text-on-primary); padding: 2px 8px; border-radius: 12px; font-size: 11px; }
.badge.required:hover { background: var(--color-warning-hover); }
.badge.installed { background: var(--color-success); color: var(--color-text-on-primary); }

.btn-switch { padding: 5px 14px; border: 1px solid var(--color-border); border-radius: 6px; background: var(--color-surface); cursor: pointer; font-size: 12px; font-weight: 500; color: var(--color-text); transition: all 0.15s; }
.btn-switch:hover:not(:disabled) { background: var(--color-primary-bg); border-color: var(--color-primary); color: var(--color-primary); }
.btn-switch:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-download { padding: 5px 14px; border: none; border-radius: 6px; background: var(--color-primary); color: white; font-size: 12px; font-weight: 500; cursor: pointer; }
.btn-download:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-retry { padding: 2px 8px; border: 1px solid var(--color-error); border-radius: 4px; background: transparent; color: var(--color-error); font-size: 11px; cursor: pointer; }
.btn-cancel { padding: 2px 8px; border: 1px solid var(--color-primary); border-radius: 4px; background: transparent; color: var(--color-primary); font-size: 11px; cursor: pointer; margin-top: 4px; }
.btn-more-models { margin-top: 12px; padding: 8px 16px; border: 1px dashed var(--color-border); border-radius: 8px; background: transparent; color: var(--color-text-secondary); font-size: 13px; cursor: pointer; width: 100%; transition: all 0.15s; }
.btn-more-models:hover { border-color: var(--color-primary); color: var(--color-primary); }

.rec-status { font-size: 12px; font-weight: 500; }
.rec-status.installed { color: var(--color-success); }
.rec-status.pulling { color: var(--color-primary); }
.rec-status.failed { color: var(--color-error); display: flex; align-items: center; gap: 8px; }
.progress-bar { width: 100%; height: 5px; background: var(--color-border); border-radius: 3px; overflow: hidden; margin: 4px 0; }
.progress-fill { height: 100%; background: var(--color-primary); border-radius: 3px; transition: width 0.3s; }
.progress-text { font-size: 11px; color: var(--color-text-secondary); }

.ollama-offline { text-align: center; padding: 24px; color: var(--color-text-secondary); }
.ollama-offline .empty-icon { font-size: 36px; margin-bottom: 8px; }
.ollama-offline .hint { font-size: 13px; }

.form-group { margin-bottom: 14px; }
.form-group label { display: block; margin-bottom: 4px; font-weight: 500; font-size: 13px; color: var(--color-text-secondary); }
.input-field { width: 100%; padding: 8px 12px; border: 1px solid var(--color-border); border-radius: 6px; font-size: 13px; outline: none; box-sizing: border-box; }
.input-field:focus { border-color: var(--color-primary); }
.actions { display: flex; gap: 10px; margin-top: 16px; }
.test-result { margin-top: 12px; padding: 10px; border-radius: 6px; font-weight: 500; font-size: 13px; }
.test-result.success { background: var(--color-success-bg); color: var(--color-success-text); }
.test-result.error { background: var(--color-error-bg); color: var(--color-error-text); }
.hint { font-size: 12px; color: var(--color-text-secondary); }
.about-text { color: var(--color-text-secondary); font-size: 13px; line-height: 1.6; margin: 6px 0; }

.btn-primary { padding: 7px 16px; border: none; border-radius: 6px; background: var(--color-primary); color: var(--color-text-on-primary); font-size: 13px; cursor: pointer; font-weight: 500; }
.btn-primary:hover:not(:disabled) { background: var(--color-primary-hover); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-secondary { padding: 7px 16px; border: 1px solid var(--color-border); border-radius: 6px; background: var(--color-surface); color: var(--color-text); font-size: 13px; cursor: pointer; font-weight: 500; }
.btn-secondary:hover { background: var(--color-bg); }
.btn-danger { padding: 7px 16px; border: none; border-radius: 6px; background: var(--color-error); color: var(--color-text-on-primary); font-size: 13px; cursor: pointer; font-weight: 500; }
.btn-danger:hover:not(:disabled) { background: var(--color-error-hover); }
.btn-danger:disabled { opacity: 0.5; cursor: not-allowed; }

.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: var(--color-overlay); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal { background: var(--color-surface); border-radius: 12px; padding: 24px; width: 500px; max-width: 90vw; max-height: 80vh; overflow-y: auto; }
.modal.modal-small { width: 400px; }
.modal.modal-large { width: 700px; }
.modal h3 { margin: 0 0 16px; font-size: 18px; }
.modal-header-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.modal-header-row h3 { margin: 0; }
.close-btn { background: none; border: none; cursor: pointer; font-size: 18px; color: var(--color-text-secondary); }
.close-btn:hover { color: var(--color-text); }
.confirm-text { font-size: 14px; color: var(--color-text); margin: 0 0 16px; line-height: 1.5; }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px; }

.library-search { margin-bottom: 16px; }
.library-grid { display: flex; flex-direction: column; gap: 4px; max-height: 400px; overflow-y: auto; }
.library-row {
  display: flex; align-items: center; gap: 8px; padding: 8px 12px;
  border: 1px solid var(--color-border); border-radius: 6px;
  font-size: 13px; transition: all 0.15s;
}
.library-row:hover { border-color: var(--color-border-hover); }
.library-name { font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 0 1 auto; min-width: 90px; max-width: 150px; }
.library-desc { font-size: 12px; color: var(--color-text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; min-width: 0; }
.library-size { font-size: 12px; color: var(--color-text-tertiary); white-space: nowrap; flex-shrink: 0; margin-left: auto; }
.library-row .rec-status.pulling { display: flex; align-items: center; gap: 8px; min-width: 180px; }
.library-row .rec-status.pulling .progress-bar { flex: 1; height: 4px; }
.library-row .rec-status.pulling .progress-fill { height: 100%; background: var(--color-primary); border-radius: 2px; }
.library-row .rec-status.pulling .progress-text { font-size: 11px; color: var(--color-primary); min-width: 30px; text-align: right; }

.modal-fade-enter-active, .modal-fade-leave-active { transition: opacity 0.2s ease; }
.modal-fade-enter-from, .modal-fade-leave-to { opacity: 0; }

.model-item-wrapper { display: flex; flex-direction: column; }
.embedding-info-panel {
  margin-top: 4px; padding: 14px 16px; border: 1px solid var(--color-warning);
  border-radius: 8px; background: var(--color-warning-bg);
}
.info-header { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.info-icon { font-size: 16px; }
.info-title { font-size: 14px; font-weight: 600; color: var(--color-text); flex: 1; }
.info-close { background: none; border: none; cursor: pointer; font-size: 14px; color: var(--color-text-secondary); padding: 2px 6px; border-radius: 4px; }
.info-close:hover { background: var(--color-hover-bg); color: var(--color-text); }
.info-body { font-size: 13px; color: var(--color-text-secondary); line-height: 1.7; }
.info-body p { margin: 0 0 8px; }
.info-body ul { margin: 0; padding-left: 18px; }
.info-body li { margin-bottom: 4px; }
.info-body strong { color: var(--color-text); }
.info-expand-enter-active, .info-expand-leave-active { transition: all 0.25s ease; overflow: hidden; }
.info-expand-enter-from, .info-expand-leave-to { opacity: 0; max-height: 0; margin-top: 0; padding-top: 0; padding-bottom: 0; }
.info-expand-enter-to, .info-expand-leave-from { opacity: 1; max-height: 300px; }

@media (max-width: 900px) {
  .view-container { padding: 20px; }
  .settings-section { padding: 18px; }
  .setting-row { gap: 12px; }
  .setting-label { min-width: 80px; }
  .model-row-desc { display: none; }
}

@media (max-width: 768px) {
  .view-container { padding: 16px; }
  .settings-section { padding: 16px; }
  .setting-row { flex-wrap: wrap; gap: 8px; }
  .setting-label { min-width: auto; }
  .model-rows { font-size: 12px; }
  .model-row { padding: 8px; gap: 6px; }
  .model-row-desc { display: none; }
  .ai-software-card { flex-wrap: wrap; padding: 12px; }
  .ai-card-info { max-width: 100%; }
  .ai-card-spacer { display: none; }
  .ai-agent-switches { flex-wrap: wrap; }
  .provider-tabs { flex-wrap: wrap; }
}

@media (max-width: 480px) {
  .view-container { padding: 12px; }
  h2 { font-size: 20px; margin-bottom: 16px; }
  .settings-section { padding: 12px; }
  .setting-row { flex-direction: column; align-items: flex-start; gap: 4px; }
  .setting-label { font-size: 12px; }
  .theme-switcher { width: 100%; }
  .theme-option { flex: 1; justify-content: center; }
  .storage-actions { flex-direction: column; align-items: stretch; }
  .actions { flex-direction: column; }
  .btn-primary, .btn-secondary, .btn-danger { width: 100%; }
  .model-row { flex-wrap: wrap; }
  .model-row-size { font-size: 11px; }
}

.ai-software-grid { display: flex; flex-direction: column; gap: 4px; }
.ai-software-card { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border: 1px solid var(--color-border); border-radius: 6px; background: var(--color-bg); transition: all 0.15s; overflow: hidden; }
.ai-software-card.configured { border-color: var(--color-success); background: var(--color-success-bg); }
.ai-software-card.not-installed { opacity: 0.6; }
.ai-card-icon { font-size: 14px; flex-shrink: 0; }
.ai-card-info { display: flex; flex-direction: column; gap: 0; min-width: 0; max-width: 50%; }
.ai-card-name { font-weight: 500; font-size: 13px; white-space: nowrap; }
.ai-card-desc { font-size: 12px; color: var(--color-text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ai-card-spacer { flex: 0 0 12px; }
.ai-card-status { font-size: 12px; color: var(--color-text-secondary); white-space: nowrap; flex-shrink: 0; }
.ai-software-card.configured .ai-card-status { color: var(--color-success); }
.ai-card-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.modal-header-actions { display: flex; align-items: center; gap: 8px; }
.switch-sm { width: 32px; height: 18px; flex-shrink: 0; }
.switch-sm .slider:before { height: 12px; width: 12px; left: 3px; bottom: 3px; }
.switch-sm input:checked + .slider:before { transform: translateX(14px); }
.ai-agent-switches { display: flex; align-items: center; gap: 2px; flex-shrink: 0; }
.ai-agent-switch { display: flex; align-items: center; gap: 2px; padding: 1px 4px; background: var(--color-surface); border-radius: 4px; }
.ai-agent-name { font-size: 10px; color: var(--color-text-secondary); white-space: nowrap; }
.switch-xs { position: relative; display: inline-block; width: 24px; height: 14px; flex-shrink: 0; }
.switch-xs input { opacity: 0; width: 0; height: 0; }
.switch-xs .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: var(--color-border); transition: .2s; border-radius: 14px; }
.switch-xs .slider:before { position: absolute; content: ""; height: 8px; width: 8px; left: 3px; bottom: 3px; background-color: white; transition: .2s; border-radius: 50%; }
.switch-xs input:checked + .slider { background-color: var(--color-success); }
.switch-xs input:checked + .slider:before { transform: translateX(10px); }
.btn-sm { padding: 4px 10px; font-size: 11px; flex-shrink: 0; }

.btn-check-update { padding: 6px 16px; border: 1px solid var(--color-primary); border-radius: 6px; background: var(--color-primary-bg); color: var(--color-primary); font-size: 13px; font-weight: 500; cursor: pointer; transition: all 0.2s; }
.btn-check-update:hover:not(:disabled) { background: var(--color-primary); color: #fff; }
.btn-check-update:disabled { opacity: 0.6; cursor: not-allowed; }

.btn-uninstall { padding: 8px 18px; border: 1px solid var(--color-error); border-radius: 6px; background: var(--color-error-bg); color: var(--color-error); font-size: 13px; font-weight: 500; cursor: pointer; transition: all 0.2s; }
.btn-uninstall:hover:not(:disabled) { background: var(--color-error); color: var(--color-text-on-primary); }
.btn-uninstall:disabled { opacity: 0.5; cursor: not-allowed; }
.uninstall-warning { color: var(--color-error) !important; font-weight: 500; }
.uninstall-list { margin: 8px 0 12px; padding-left: 18px; font-size: 13px; color: var(--color-text-secondary); line-height: 1.8; }
.uninstall-options { margin: 12px 0; display: flex; flex-direction: column; gap: 8px; }
.uninstall-option { display: flex; align-items: flex-start; gap: 10px; padding: 10px 14px; border: 1px solid var(--color-border); border-radius: 8px; cursor: pointer; transition: all 0.2s; }
.uninstall-option:hover { border-color: var(--color-primary); background: var(--color-surface-hover); }
.uninstall-option.active { border-color: var(--color-primary); background: var(--color-primary-bg); }
.option-radio { font-size: 16px; line-height: 1.4; color: var(--color-primary); flex-shrink: 0; }
.option-content { display: flex; flex-direction: column; gap: 2px; }
.option-content strong { font-size: 13px; color: var(--color-text); }
.option-desc { font-size: 12px; color: var(--color-text-secondary); line-height: 1.4; }
.uninstall-confirm-input { margin: 12px 0; }
.uninstall-confirm-input label { display: block; margin-bottom: 6px; font-size: 13px; color: var(--color-text-secondary); }
.uninstall-confirm-input strong { color: var(--color-error); }

.interval-select { padding: 6px 12px; border: 1px solid var(--color-border); border-radius: 6px; background: var(--color-surface); color: var(--color-text); font-size: 13px; cursor: pointer; outline: none; }
.interval-select:focus { border-color: var(--color-primary); }

.modal-tutorial { width: 680px; max-height: 85vh; }
.tutorial-content { display: flex; flex-direction: column; gap: 20px; }
.tutorial-section { padding: 16px; border: 1px solid var(--color-border); border-radius: 8px; background: var(--color-bg); }
.tutorial-section-title { font-size: 15px; font-weight: 600; color: var(--color-text); margin-bottom: 10px; }
.tutorial-text { font-size: 13px; color: var(--color-text-secondary); line-height: 1.6; margin: 0 0 8px; }
.tutorial-list { margin: 4px 0; padding-left: 18px; font-size: 13px; color: var(--color-text-secondary); line-height: 1.8; }
.tutorial-checklist { display: flex; flex-direction: column; gap: 6px; }
.tutorial-check { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--color-text-secondary); padding: 6px 10px; border-radius: 6px; background: var(--color-surface); }
.tutorial-check.checked { color: var(--color-success); }
.check-icon { font-size: 14px; flex-shrink: 0; }
.tutorial-step { display: flex; gap: 14px; margin-bottom: 16px; }
.tutorial-step:last-child { margin-bottom: 0; }
.step-number { width: 28px; height: 28px; border-radius: 50%; background: var(--color-primary); color: var(--color-text-on-primary); display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: 600; flex-shrink: 0; }
.step-content { flex: 1; min-width: 0; }
.step-title { font-size: 14px; font-weight: 600; color: var(--color-text); margin-bottom: 6px; }
.step-ol { margin: 4px 0; padding-left: 18px; font-size: 13px; color: var(--color-text-secondary); line-height: 1.8; }
.step-ol li { margin-bottom: 2px; }
.tutorial-form-info { display: flex; flex-direction: column; gap: 6px; padding: 10px 14px; background: var(--color-surface); border-radius: 6px; margin: 8px 0; }
.form-field { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.field-label { color: var(--color-text-secondary); min-width: 50px; }
.field-value { color: var(--color-text); font-weight: 500; font-family: 'SF Mono', 'Fira Code', monospace; }
.tutorial-code-block { border: 1px solid var(--color-border); border-radius: 8px; overflow: hidden; margin: 8px 0; }
.code-header { display: flex; justify-content: space-between; align-items: center; padding: 6px 12px; background: var(--color-surface); border-bottom: 1px solid var(--color-border); }
.code-lang { font-size: 11px; color: var(--color-text-tertiary); font-weight: 500; text-transform: uppercase; }
.btn-copy { padding: 3px 10px; border: 1px solid var(--color-border); border-radius: 4px; background: var(--color-surface); color: var(--color-text-secondary); font-size: 11px; cursor: pointer; transition: all 0.15s; }
.btn-copy:hover { border-color: var(--color-primary); color: var(--color-primary); }
.code-content { padding: 12px 14px; margin: 0; font-family: 'SF Mono', 'Fira Code', monospace; font-size: 12px; line-height: 1.6; color: var(--color-text); overflow-x: auto; background: var(--color-bg); white-space: pre; }
.tutorial-tip { padding: 10px 14px; border-radius: 6px; background: var(--color-primary-bg); border: 1px solid var(--color-primary); font-size: 13px; color: var(--color-text-secondary); line-height: 1.6; }
.tutorial-tip code { padding: 1px 5px; border-radius: 3px; background: var(--color-surface); font-family: 'SF Mono', 'Fira Code', monospace; font-size: 12px; color: var(--color-text); }
.tutorial-tools { display: flex; flex-direction: column; gap: 8px; margin-top: 8px; }
.tutorial-tool { padding: 10px 14px; border: 1px solid var(--color-border); border-radius: 6px; background: var(--color-surface); }
.tool-name { font-size: 13px; font-weight: 600; color: var(--color-primary); margin-bottom: 4px; font-family: 'SF Mono', 'Fira Code', monospace; }
.tool-desc { font-size: 12px; color: var(--color-text-secondary); margin-bottom: 2px; }
.tool-params { font-size: 11px; color: var(--color-text-tertiary); font-family: 'SF Mono', 'Fira Code', monospace; }
.tutorial-examples { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }
.example-item { padding: 8px 14px; border-radius: 6px; background: var(--color-surface); font-size: 13px; color: var(--color-text-secondary); border-left: 3px solid var(--color-primary); }
.mt-2 { margin-top: 8px; }

</style>
