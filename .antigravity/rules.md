\# 编码规内容如下：

Markdown

\# 基础开发规则## 1. 核心要求- \*\*回复语言\*\*：始终使用 \*\*中文\*\* 进行交流和代码注释。

\- \*\*确认机制\*\*：在删除文件或目录、以及安装新插件前，必须询问并获得许可。



\## 2. 后端 (C#)- 遵循 PascalCase 命名规范。

\- 必须使用 `async/await` 异步编程。

\- 接口返回统一的 JSON 格式。



\## 3. 前端 (Vue)- 统一使用 Vue 3 `<script setup>` 组合式 API。

\- 优先使用 TypeScript 声明类型，禁止使用 `any`。

\- 样式推荐使用 Tailwind CSS 或 Scss。



\## 4. 报错处理- 如果代码运行报错，请先分析日志，不要直接重写整个文件。则 (Project Rules)## 语言与框架- 始终使用 TypeScript，禁止使用 any 类型。

\- React 组件必须使用函数式组件和 Hooks。



\## 代码风格- 使用 Tailwind CSS 进行样式开发，禁止写行内 style。

\- 变量命名使用 camelCase，常量使用 UPPER\_CASE。



\## 行为限制

\- 在修改现有代码前，必须先运行项目中的单元测试 (`npm test`)。

\- 如果需要安装新依赖，必须先向我询问确认。


## 环境管理
- **Python 环境**：必须使用本地已有的 `bit_politeia` conda 环境运行 Python 代码。
- **禁止操作**：禁止创建新的 conda 环境或临时环境。
