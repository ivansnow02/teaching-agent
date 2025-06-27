# 教学代理API使用指南

## 概述

本文档提供了如何使用教学代理API的详细说明。
- **章节目录生成器**：用于生成课程的章节目录。
- **章节课件生成器**：用于生成每个章节的详细课件内容
- **RAG代理 (RAG Agent)**: 基于检索增强生成的上下文问答
- **实训内容生成器**：用于生成实训环节的详细内容

### 光是调试的话

直接：


#### LightRAG

```powershell
# 安装uv
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 使用uv
uv venv

# 激活虚拟环境
# Linux/MacOS
source venv/bin/activate
# Windows powershell
.\.venv\Scripts\Activate.ps1

uv sync

uv pip install -e .

uv pip install -r requirements.txt

# 运行
uv run lightrag\api\lightrag_multiuser_server.py
```

#### teaching_agent

```powershell
uv venv

.\.venv\Scripts\Activate.ps1

uv sync

langgraph dev --allow-blocking --no-reload

```

### docker安装(先不用)

```bash
docker run -p 9621:9621 -v $(pwd)/data:/app/data lightrag:amd64

docker run \
  -p 8123:8000 \
  --env-file .env \
  -e LANGCHAIN_ENDPOINT="https://api.smith.langchain.com" \
  -e LANGSMITH_API_KEY="在.env里复制过来" \
  -e REDIS_URI="redis的连接字符串" \
  -e DATABASE_URI="Postgres的连接字符串" \
  teaching_agent:amd64
```

### 使用之前

先在`/documents/upload/{course_id}`端点上传知识库，以便RAG代理可以访问这些文档进行问答。


## 章节目录生成 (Chapter Outline Generator)

### 创建Assistant

POST /assistants

```json
{
    "graph_id": "chapter_outline_generator", // 章节目录生成器
    "config": {
        "configurable":{
            "course_id": "课程id"
        }
    }
}
```

### 创建Thread

POST /threads

最简单的配置就是直接空就好了

```json
{}
```

### 创建Run



```json
{
    "assistant_id": "assistant_id", // assistant_id是上面创建的Assistant的ID
    "input": {
        "raw_syllabus": "您的教学大纲内容...",
        "has_experiment": true, // 是否包含实训内容
        "hour_per_class": 2 // 每节课的课时数
    }
}
```

**返回结果**

```json
{
    "has_experiment": true,
    "hour_per_class": 2,
    "raw_syllabus": "计算机图形学课程大纲……",
    "chapters": [
        {
            "title": "第一章：绪论",
            "content": "介绍计算机图形学的基本概念、发展历史、应用领域，以及图形系统和显示设备的工作原理。",
            "order": 1
        },
        {
            "title": "实训一：图形开发环境搭建",
            "content": "学习如何配置基本的图形开发环境，为后续实验奠定基础。",
            "order": 2
        },
        {
            "title": "第二章：图形学数学基础",
            "content": "讲解坐标系统、向量运算、矩阵变换、投影变换等图形学所需的数学知识。",
            "order": 3
        },

    ]
}
```

## 章节课件生成 (Chapter Content Generator)

### 创建Assistant

POST /assistants

```json
{
    "graph_id": "chapter_content_generator", // 章节课件生成器
    "config": {
        "configurable":{
            "course_id": "课程id"
        }
    }
}
```

### 创建Thread

POST /threads

最简单的配置就是直接空就好了

```json
{}
```

### 创建Run

建议用**创建后台运行的run**

/threads/{thread_id}/runs

```json
{
    "assistant_id": "3c33c2bb-073f-49c8-9dfe-8db81c89d05e",
    "input": {
        "raw_syllabus": "title:第二章：图形学数学基础,content:讲解坐标系统、向量运算、矩阵变换及投影变换等图形学所需的数学基础知识。"
    }
}
```

轮询 /threads/{thread_id}/runs/{run_id}
**返回结果**
```json
{
    "run_id": "1f0528ad-1cc8-67b0-93de-c798c9e9107e",
    "thread_id": "52bbd3d9-f4ee-4daa-b15f-57b9da2f8020",
    "assistant_id": "3c33c2bb-073f-49c8-9dfe-8db81c89d05e",
    "metadata": {
        "graph_id": "chapter_content_generator",
        "assistant_id": "3c33c2bb-073f-49c8-9dfe-8db81c89d05e"
    },
    "status": "pending",
    "kwargs": {
        "input": {
            "raw_syllabus": "title:第二章：图形学数学基础,content:讲解坐标系统、向量运算、矩阵变换及投影变换等图形学所需的数学基础知识。"
        },
        "command": null,
        ……
}
```

当status变成success时，使用加入Run（获取结果） response即为结构化课件内容。

**返回结果**

```json
{
  "raw_syllabus": "title:第二章：图形学数学基础,content:讲解坐标系统、向量运算、矩阵变换及投影变换等图形学所需的数学基础知识。",
  "plan": [
    "确定教案的目标，即学生能够理解并应用图形学中的数学基础知识。",
    "根据需要调整语言表达，使内容更易理解和吸引学生。"
  ],
  "before_parallel_plan": [
    "确定教案的目标，即学生能够理解并应用图形学中的数学基础知识。",
    "撰写课程介绍部分，包括课程标题和目标，明确学习本章的意义。"
  ],
  "parallel_plan": [
    "设计讲解坐标系统的部分，涵盖二维与三维坐标系的基本概念。",
    "编写向量运算的详细内容，包括加法、减法、点积、叉积及其几何意义。",

  ],
  "after_parallel_plan": [
    "设计课堂练习或课后作业，让学生通过实践巩固所学知识。",

  ],
  "past_steps": [
    [
      "确定教案的目标，即学生能够理解并应用图形学中的数学基础知识。",
      "<task>\n确定教案的目标，即学生能够理解并应用图形学中的数学基础知识。\n</task>\n\n<result>\n教案的目标是让学生掌握图形学中涉及的数学基础知识，并能够将其应用于实际问题中。这包括但不限于向量、矩阵、坐标变换、几何形状的表示和操作等内容。通过学习这些数学概念，学生将能够理解和实现计算机图形学中的基本算法和功能。\n</result>"
    ],

  ],
  "response": "### 教案：图形学中的数学基础知识教学方案\n\n---\n\n## 一、教案目标\n\n**教学目标**：\n学生能够理解并掌握计算机图形学中所涉及的数学基础知识，包括坐标系统、向量运算、矩阵变换、投影变换等内容，并具备将这些知识应用于实际问题的能力。\n\n---\n\n## 二、教…",
  ……（省略其他内容）
}
```

## 实训课实验步骤生成 (Chapter Experiment Generator)

### 创建Assistant

POST /assistants

```json
{
    "graph_id": "chapter_experiment_generator", // 实训课实验步骤生成器
    "config": {
        "configurable":{
            "course_id": "课程id"
        }
    }
}
```

### 创建Thread

POST /threads

最简单的配置就是直接空就好了

```json
{}
```

### 创建Run

建议用**创建后台运行的run**

/threads/{thread_id}/runs

```json
{
    "assistant_id": "xxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "input": {
        "raw_syllabus": "title:实训一：图形开发环境搭建,content:学习如何配置基本的图形开发环境，为后续实验奠定基础。"
    }
}
```

轮询 /threads/{thread_id}/runs/{run_id}
**返回结果**
```json
{
    "run_id": "xxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "thread_id": "xxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "assistant_id": "xxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "metadata": {
        "graph_id": "chapter_experiment_generator",
        "assistant_id": "xxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
    },
    "status": "pending",
    "kwargs": {
        "input": {
            "raw_syllabus": "title:实训一：图形开发环境搭建,content:学习如何配置基本的图形开发环境，为后续实验奠定基础。"
        },
        "command": null
    }
}
```

当status变成success时，使用加入Run（获取结果） response即为结构化实验步骤内容。

**返回结果**

```json
{
  "raw_syllabus": "\"title\": \"实验1: 图形开发环境搭建\",\n      \"content\": \"熟悉图形开发环境的搭建过程，为后续实验做好准备。\",\n      \"order\": 2,\n      \"type\": \"experiment\"\n    },",
  "plan": [],
  "past_steps": [
    [
      "安装图形开发所需的集成开发环境（IDE）。",
      "### 安装图形开发所需的集成开发环境（IDE）\n\n#### 1. 选择适合的 ID0, 100]……",
      "选择适合操作系统的图形开发 IDE（如 VSCode、Qt Creator 等），下载安装后配置必要插件和语言环境，安装对应图形库（如 Pygame 或 OpenGL），创建项目并编写基础图形代码进行验证。"
    ],
    ……（省略其他步骤）
  ],
  "response": "### 安装图形开发所需的集成开发环境（IDE）\n\n#### 1. 选择适合的 IDE\n根据你的操作系统（Windows、macOS 或 Linux），选择一个适合图形开发的 IDE。常见的图形开发 IDE 包括：\n\n- **Visual Studio Code (VSCode)**：轻量级，支持多种编程语言，插件丰富。\n- **Eclipse**：适用于 Java 开发，有图形界面插件。\n- **Qt Creator**：专为 Qt ……"
}
```
