# 南开大学 Web 搜索引擎系统

[![Python](https://img.shields.io/badge/Python-3.7+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.0+-green.svg)](https://flask.palletsprojects.com/)
[![Whoosh](https://img.shields.io/badge/Whoosh-Search-orange.svg)](https://whoosh.readthedocs.io/)

一个基于 Flask 和 Whoosh 的南开大学校内资源搜索引擎，提供智能检索、个性化推荐和用户管理功能。

## 🎯 项目简介

本项目是信息检索课程作业，构建了一个针对南开大学校内资源的综合性 Web 搜索引擎。系统包含网页爬取、索引构建、智能检索、个性化推荐等核心功能，为用户提供高效的信息检索服务。

## ✨ 核心功能

### 🔍 多样化查询支持
- **站内查询**: 基础的关键词搜索
- **短语查询**: 支持多词组合查询
- **通配查询**: 支持 `*` 和 `?` 通配符查询
- **文档查询**: 支持 PDF、DOC、XLS 等文档类型检索
- **查询日志**: 记录用户历史查询记录
- **网页快照**: 提供网页内容的历史快照

### 👤 用户管理系统
- 用户注册与登录
- 个性化用户配置
- 查询历史记录
- 个性化推荐

### 📊 统计分析
- 点击统计分析
- 查询日志分析
- 用户行为分析

## 🏗️ 系统架构

```
Web-Search-Engine/
├── Spider/                    # 网页爬虫模块
│   ├── mutispider.py         # 多线程新闻爬虫
│   ├── downloadlink.py       # 文档下载链接爬虫
│   └── default_urls.json     # 默认爬取链接配置
├── index/                     # 索引构建模块
│   ├── creat_index_document.py # 索引创建脚本
│   └── index_dir/            # Whoosh 索引文件
├── query_service/            # 查询服务模块
│   ├── app.py               # Flask 主应用
│   ├── templates/           # HTML 模板
│   └── users.db            # 用户数据库
├── custom_analyzers.py      # 中文分词器
└── README.md               # 项目文档
```

## 🚀 快速开始

### 环境要求
- Python 3.7+
- Flask 2.0+
- Whoosh
- BeautifulSoup4
- jieba (中文分词)
- SQLite3

### 安装依赖

```bash
pip install flask whoosh beautifulsoup4 jieba requests sqlite3
```

### 1. 数据爬取

```bash
# 爬取南开新闻数据
cd Spider
python mutispider.py

# 爬取文档下载链接
python downloadlink.py
```

### 2. 构建索引

```bash
# 创建搜索索引
cd index
python creat_index_document.py
```

### 3. 启动服务

```bash
# 启动 Web 服务
cd query_service
python app.py
```

访问 `http://localhost:5000` 开始使用搜索引擎。

## 🔧 核心技术

### 中文分词
- 使用 **jieba** 分词库进行中文文本处理
- 自定义 `ChineseAnalyzer` 和 `ChineseTokenizer`
- 支持精确搜索和模糊匹配

### 搜索引擎
- 基于 **Whoosh** 全文搜索引擎
- 支持多字段索引（标题、内容、URL、锚文本）
- 实现 TF-IDF 算法进行相关性排序

### Web 框架
- 使用 **Flask** 构建 Web 应用
- 响应式前端界面
- RESTful API 设计

## 📋 使用指南

### 基础搜索
1. 在搜索框输入关键词
2. 点击搜索按钮获取结果
3. 查看搜索结果和相关信息

### 高级搜索
- **短语查询**: 使用引号包含短语 `"南开大学"`
- **通配查询**: 使用通配符 `南开*` 或 `计?`
- **文档查询**: 添加 `filetype:pdf` 等过滤条件

### 用户功能
1. 注册新用户账号
2. 登录访问个人功能
3. 查看查询历史
4. 获取个性化推荐

## 📈 性能特点

- **大规模数据**: 支持 10万+ 网页索引
- **快速检索**: 毫秒级搜索响应
- **多线程爬取**: 高效的并发数据采集
- **智能排序**: 基于向量空间模型的相关性排序

## 🛠️ 开发说明

### 爬虫模块
- `mutispider.py`: 多线程新闻爬虫，支持批量数据采集
- `downloadlink.py`: 文档链接爬虫，抓取各类文档资源
- 遵循 robots.txt 协议，礼貌爬取

### 索引模块
- 使用 Whoosh 构建倒排索引
- 支持中文分词和文本预处理
- 多字段索引提高检索精度

### 查询模块
- Flask 路由处理用户请求
- 支持多种查询模式
- 实现用户认证和权限管理

## 📝 日志记录

系统记录详细的运行日志：
- `query_log.txt`: 查询日志
- `click_log.txt`: 点击统计
- `mutiscraper.log`: 爬虫日志

## 🤝 贡献指南

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交修改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

## 📄 许可证

本项目仅用于学术研究和教育目的。

## 🙏 致谢

- 感谢南开大学信息检索课程组
- 感谢开源社区提供的优秀工具和库
- 特别感谢 Whoosh、Flask、jieba 等项目的贡献者

## 📧 联系方式

如有问题或建议，请通过以下方式联系：
- 项目地址: [GitHub Repository]
- 邮箱: [Your Email]

---

*本项目为南开大学信息检索课程作业，旨在学习和实践搜索引擎相关技术。*
