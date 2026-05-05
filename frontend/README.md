# 钻石记忆系统 - Electron + Vue3 跨平台前端

## 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| 前端框架 | Vue3 | 3.4+ |
| 构建工具 | Vite | 5.2+ |
| 类型系统 | TypeScript | 5.4+ |
| 状态管理 | Pinia | 2.1+ |
| 路由 | Vue Router | 4.3+ |
| 桌面框架 | Electron | 29.1+ |
| 打包工具 | electron-builder | 24.13+ |

## 项目结构

```
frontend/
├── package.json              # 依赖和脚本配置
├── vite.config.ts            # Vite构建配置
├── electron-builder.yml      # Electron打包配置
├── tsconfig.json             # TypeScript配置（Renderer进程）
├── tsconfig.node.json        # TypeScript配置（Node环境）
├── tsconfig.electron.json    # TypeScript配置（Electron主进程）
└── src/
    ├── main/                 # Electron主进程
    │   ├── index.ts          # 主进程入口
    │   └── backend-manager.ts # Python后端管理器
    ├── preload/              # 预加载脚本
    │   └── index.ts          # IPC通信桥接
    └── renderer/             # Vue3渲染进程
        ├── index.html        # HTML入口
        ├── main.ts           # Vue应用入口
        ├── App.vue           # 根组件
        ├── api/              # API请求封装
        ├── router/           # 路由配置
        ├── stores/           # Pinia状态管理
        ├── views/            # 页面视图
        └── types/            # TypeScript类型定义
```

## 开发命令

```bash
# 安装依赖
npm install

# 启动Vite开发服务器（仅前端）
npm run dev

# 启动Electron开发模式（前端 + Electron）
npm run electron:dev

# 构建前端
npm run build

# 编译Electron主进程
npm run electron:build-main

# 打包Mac应用
npm run electron:build:mac

# 打包Windows应用
npm run electron:build:win

# 打包Linux应用
npm run electron:build:linux
```

## 构建输出

- `dist/renderer/` - Vite构建的前端文件
- `dist/main/` - TypeScript编译的Electron主进程
- `../dist/electron/` - electron-builder打包的安装包

## 后端集成

- 后端位置: `../backend/`
- 健康检查: `http://127.0.0.1:8000/health`
- API基础: `http://127.0.0.1:8000/api/`

后端管理器（`backend-manager.ts`）负责：
1. 启动/停止Python后端进程
2. 健康检查和自动重启
3. 支持自定义数据目录参数

## 打包流程

1. 编译Python后端：`npm run backend:build`
2. 构建前端：`npm run build`
3. 编译主进程：`npm run electron:build-main`
4. 打包安装器：`npm run electron:build:mac` 或 `npm run electron:build:win`

## 源代码保护

1. **Nuitka编译** - Python后端编译为机器码
2. **Terser混淆** - 前端JS代码混淆压缩
3. **ASAR打包** - 前端文件归档保护
