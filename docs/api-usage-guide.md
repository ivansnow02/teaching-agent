# 教学代理API使用指南

## 概述

本文档提供了如何使用教学代理API的详细说明。
- **章节目录生成器**：用于生成课程的章节目录。
- **章节课件生成器**：用于生成每个章节的详细课件内容
- **RAG代理 (RAG Agent)**: 基于检索增强生成的上下文问答
- **实训内容生成器**：用于生成实训环节的详细内容
- **测验生成器**：用于生成课程相关的测验题目
- **批量批改代理**：用于批量批改学生提交的答案

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

## 测验题生成 (Quiz Generator)

### 创建Assistant

POST /assistants

```json
{
    "graph_id": "quiz_planner_v2", // 测验题生成器
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
        "requirements": "关于计算机图形学的二维图像生成，3道单选，2道多选，3道简答，30%简单题，40%中等题，30%难题"
    }
}
```

轮询 /threads/{thread_id}/runs/{run_id}

```json
{
  "run_id": "xxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "thread_id": "xxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "assistant_id": "xxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "metadata": {
    "graph_id": "quiz_planner_v2",
    "assistant_id": "xxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  },
  "status": "pending",
  "kwargs": {
    "input": {
      "requirements": "关于计算机图形学的二维图像生成，3道单选，2道多选，3道简答，30%简单题，40%中等题，30%难题"
    },
    "command": null
  }
}
```

当status变成success时，使用加入Run（获取结果） quiz即为生成的问题列表。

**返回结果**

```json
{
  "requirements": "关于计算机图形学的二维图像生成，3道单选，2道多选，3道简答，30%简单题，40%中等题，30%难题",
  "plan": {
    "questions": [
      {
        "questionType": "single_choice",
        "knowledgePoints": "像素操作,图像增强",
        "difficulty": "easy"
      },
……
      {
        "questionType": "short_answer",
        "knowledgePoints": "渲染与着色的关系",
        "difficulty": "hard"
      }
    ]
  },
  "single_questions_plan": {
    "questions": [
      {
        "questionType": "single_choice",
        "knowledgePoints": "像素操作,图像增强",
        "difficulty": "easy"
……
      }
    ]
  },
  "multiple_questions_plan": {
    "questions": [
      {
        "questionType": "multiple_choice",
        "knowledgePoints": "渲染技术,光照效果",
        "difficulty": "medium"
      },
 ……
    ]
  },
  "short_answer_questions_plan": {
    "questions": [
      {
        "questionType": "short_answer",
        "knowledgePoints": "图像处理核心概念",
        "difficulty": "medium"
      },
 ……
    ]
  },
  "quiz": [
    {
      "questionType": "single_choice",
      "questionText": "以下哪种操作属于图像增强的范畴？",
      "difficulty": "easy",
      "options": [
        {
          "optionLabel": "A",
          "optionText": "将图像转换为灰度图",
          "optionOrder": 1,
          "isCorrect": false
        },
        {
          "optionLabel": "B",
          "optionText": "调整图像的亮度和对比度",
          "optionOrder": 2,
          "isCorrect": true
        },
        {
          "optionLabel": "C",
          "optionText": "对图像进行像素点访问",
          "optionOrder": 3,
          "isCorrect": false
        },
        {
          "optionLabel": "D",
          "optionText": "将图像保存为不同格式",
          "optionOrder": 4,
          "isCorrect": false
        }
      ],
      "correctAnswer": "B",
      "answerExplanation": "调整图像的亮度和对比度是图像增强的一种基本操作，旨在改善图像的视觉效果。"
    },
……
    {
      "questionType": "multiple_choice",
      "questionText": "在渲染技术中，以下哪些方法常用于处理光照效果？",
      "difficulty": "medium",
      "options": [
        {
          "optionLabel": "A",
          "optionText": "光线追踪（Ray Tracing）",
          "optionOrder": 1,
          "isCorrect": true
        },
        {
          "optionLabel": "B",
          "optionText": "Z-Buffer（深度缓冲）",
          "optionOrder": 2,
          "isCorrect": true
        },
        {
          "optionLabel": "C",
          "optionText": "LOD（Level of Detail）",
          "optionOrder": 3,
          "isCorrect": false
        },
        {
          "optionLabel": "D",
          "optionText": "纹理映射（Texture Mapping）",
          "optionOrder": 4,
          "isCorrect": true
        }
      ],
      "correctAnswer": "A,B,D",
      "answerExplanation": "光线追踪用于模拟真实光照路径，Z-Buffer用于解决可见性问题并优化光照计算，而纹理映射则通过贴图增强光照表现力。LOD主要用于控制模型复杂度，而非直接处理光照效果。"
    },
 ……
    {
      "questionType": "short_answer",
      "questionText": "简述图像处理的基本步骤及其各自的作用。",
      "difficulty": "medium",
      "options": [],
      "correctAnswer": "图像处理的基本步骤包括：1. 图像获取，即通过设备捕获或生成数字图像；2. 图像增强，改善图像的视觉效果或突出感兴趣区域；3. 图像去噪，去除图像中的随机噪声以提高质量；4. 图像分割，将图像划分为多个具有特定语义的部分或对象；5. 特征提取，识别并提取图像中可用于分析的关键特征；6. 图像识别与理解，对图像内容进行解释和分类。这些步骤通常根据具体应用需求组合使用。",
      "answerExplanation": "图像处理流程从获取图像开始，经过增强、去噪、分割等环节，最终实现特征提取和图像识别，每个步骤在不同应用中可能有所侧重。"
    },
 ……
  ]
}
```

**字段说明**

- requirements: 用户输入的出题需求描述。
- plan: 题目生成计划，包含每道题的类型、知识点、难度。
- single_questions_plan / multiple_questions_plan / short_answer_questions_plan: 按题型分类的题目生成计划。
- quiz: 生成的测验题目列表，每题包含题型、题干、难度、选项、正确答案、答案解析等字段。

如需自定义题目数量、难度分布、知识点等，可在 requirements 字段中详细描述。

## 批量批改 (Batch Grading Agent)

### 创建Assistant

POST /assistants

```json
{
    "graph_id": "batch_grading_agent", // 批量批改Agent
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
        "question": {
            "questionType": "short_answer",
            "questionText": "请简述透视投影和正交投影的主要区别，并说明它们各自适用的场景。",
            "questionOrder": 5,
            "score": 20,
            "difficulty": "hard",
            "options": [],
            "correctAnswer": "透视投影：模拟人眼观察方式，远处物体看起来更小，有消失点，平行线会相交，适用于游戏、虚拟现实等需要真实感的场景。正交投影：物体大小不随距离变化，平行线保持平行，不会产生近大远小的效果，适用于CAD、工程制图等需要保持精确测量和比例的场景。",
            "answerExplanation": "两种投影方式各有特点和适用场景，理解它们的区别对于选择合适的投影方式很重要。"
        },
        "student_answers": [
            {"student_id": "1", "answer": "透视投影是一种模拟人眼看物体的方式，它会随着距离远近产生缩小的效果，能体现出深度感，常用于3D游戏和电影渲染。正交投影则不会随距离变化，物体大小恒定，更适合用于机械制图和工程建模，因为它能准确表现物体的尺寸和比例。"},
            {"student_id": "2", "answer": "透视投影是把物体直接投到屏幕上，不管远近大小都一样，所以看起来更真实；而正交投影会让远的东西变小，看起来像是有深度，常用于建筑设计。"},
            {"student_id": "3", "answer": "透视投影适合用在科学绘图，因为它精确；正交投影则适合拍电影，因为它有立体感。一个有缩放，一个没有。"},
            {"student_id": "4", "answer": "透视投影就像你用眼睛看一个长廊，远处的东西看起来更小；而正交投影就像你把东西放在扫描仪上一样，不管远近，大小都一样。游戏建模的时候会用透视，做蓝图图纸就用正交。"}
        ]
    }
}
```

轮询 /threads/{thread_id}/runs/{run_id}

**返回结果**

```json
{
  "question": {
    "questionType": "short_answer",
    "questionText": "请简述透视投影和正交投影的主要区别，并说明它们各自适用的场景。",
    "questionOrder": 5,
    "score": 20,
    "difficulty": "hard",
    "options": [],
    "correctAnswer": "透视投影：模拟人眼观察方式，远处物体看起来更小，有消失点，平行线会相交，适用于游戏、虚拟现实等需要真实感的场景。正交投影：物体大小不随距离变化，平行线保持平行，不会产生近大远小的效果，适用于CAD、工程制图等需要保持精确测量和比例的场景。",
    "answerExplanation": "两种投影方式各有特点和适用场景，理解它们的区别对于选择合适的投影方式很重要。"
  },
  "student_answers": [
    {
      "student_id": "1",
      "answer": "透视投影是一种模拟人眼看物体的方式，它会随着距离远近产生缩小的效果，能体现出深度感，常用于3D游戏和电影渲染。正交投影则不会随距离变化，物体大小恒定，更适合用于机械制图和工程建模，因为它能准确表现物体的尺寸和比例。"
    },
    {
      "student_id": "2",
      "answer": "透视投影是把物体直接投到屏幕上，不管远近大小都一样，所以看起来更真实；而正交投影会让远的东西变小，看起来像是有深度，常用于建筑设计。"
    },
    {
      "student_id": "3",
      "answer": "透视投影适合用在科学绘图，因为它精确；正交投影则适合拍电影，因为它有立体感。一个有缩放，一个没有。"
    },
    {
      "student_id": "4",
      "answer": "透视投影就像你用眼睛看一个长廊，远处的东西看起来更小；而正交投影就像你把东西放在扫描仪上一样，不管远近，大小都一样。游戏建模的时候会用透视，做蓝图图纸就用正交。"
    }
  ],
  "review_results": {
    "1": [
      {
        "student_id": "1",
        "is_correct": true,
        "score": 1,
        "analysis": "学生的回答准确地指出了透视投影和正交投影的核心区别，并正确说明了它们各自的适用场景。语言表达清晰，内容完整，符合标准答案的要求。",
        "errors": [],
        "reviewer": "reviewer_A"
      },
      {
        "student_id": "1",
        "is_correct": false,
        "score": 0.85,
        "analysis": "学生的回答整体上是正确的，准确地指出了透视投影和正交投影的核心特点及其常见应用场景。但在描述透视投影时未提及‘平行线会相交’这一关键特性，也未提到‘消失点’的概念；在描述正交投影时没有说明‘平行线保持平行’这一重要属性。这些补充信息有助于更全面地体现两种投影方式的几何特性。",
        "errors": [
          {
            "error_description": "学生在描述透视投影时，遗漏了‘平行线会相交’以及‘消失点’这两个关键概念。",
            "correction_suggestion": "建议补充说明：透视投影中，平行线会随着距离变远而相交于一点，即消失点，这是模拟真实视觉效果的重要特征。"
          },
          {
            "error_description": "学生在描述正交投影时，未明确指出‘平行线保持平行’这一几何特性。",
            "correction_suggestion": "建议补充说明：在正交投影中，无论物体距离观察者多远，平行线始终保持平行，不会因为距离变化而汇聚或分离。"
          }
        ],
        "reviewer": "reviewer_B"
      }
    ],
    "2": [
      {
        "student_id": "2",
        "is_correct": false,
        "score": 0.4,
        "analysis": "学生的回答存在多个关键性错误，混淆了透视投影和正交投影的基本特性。需要重新理解两种投影方式的定义及其应用场景。",
        "errors": [
          {
            "error_description": "学生错误地描述了透视投影的特性，称其为‘不管远近大小都一样’，这实际上是正交投影的特点。",
            "correction_suggestion": "应修正为：透视投影模拟人眼观察方式，远处物体看起来更小，有消失点，平行线会相交。"
          },
          {
            "error_description": "学生错误地将正交投影描述为‘会让远的东西变小’，这其实是透视投影的特征。",
            "correction_suggestion": "应修正为：正交投影中物体大小不随距离变化，平行线保持平行，不会产生近大远小的效果。"
          },
          {
            "error_description": "虽然提到建筑设计作为正交投影的应用场景，但未准确说明其原因（如保持精确测量和比例）。",
            "correction_suggestion": "建议补充说明正交投影适用于CAD、工程制图等需要保持精确测量和比例的场景。"
          }
        ],
        "reviewer": "reviewer_A"
      },
      {
        "student_id": "2",
        "is_correct": false,
        "score": 0.4,
        "analysis": "学生的回答混淆了透视投影和正交投影的基本特性，错误地描述了两种投影的效果，并且对适用场景的说明不够准确。整体理解存在明显偏差，需要重新学习相关知识。",
        "errors": [
          {
            "error_description": "学生错误地认为透视投影是‘把物体直接投到屏幕上，不管远近大小都一样’，这实际上是正交投影的特点。",
            "correction_suggestion": "应更正为：透视投影模拟人眼观察方式，远处物体看起来更小，有消失点，平行线会相交；而正交投影中物体大小不随距离变化，平行线保持平行。"
          },
          {
            "error_description": "学生错误地表示正交投影会让‘远的东西变小’，这其实是透视投影的特征。",
            "correction_suggestion": "应明确区分：正交投影不会产生近大远小的效果，物体大小不随距离改变，适合需要精确测量的场景如工程制图。"
          },
          {
            "error_description": "虽然提到了建筑设计作为正交投影的应用场景，但表述模糊，未提及透视投影更适合真实感渲染的场景如游戏或虚拟现实。",
            "correction_suggestion": "建议补充完整应用场景：透视投影适用于游戏、虚拟现实等需要真实感的场景；正交投影适用于CAD、建筑图纸等需要保持比例和测量精度的场景。"
          }
        ],
        "reviewer": "reviewer_B"
      }
    ],
    "3": [
      {
        "student_id": "3",
        "is_correct": false,
        "score": 0.3,
        "analysis": "学生的回答存在多个关键性错误，包括对透视投影和正交投影特点的混淆，以及适用场景的误判。此外，描述过于简略，缺乏标准答案中要求的核心要点。",
        "errors": [
          {
            "error_description": "学生将透视投影描述为适合科学绘图，这与正确答案相反。透视投影并不以精确性著称，而是以模拟人眼视觉、产生真实感著称。",
            "correction_suggestion": "应更正为：透视投影适用于游戏、虚拟现实等需要真实感的场景，而不是科学绘图。"
          },
          {
            "error_description": "学生认为正交投影适合拍电影，这是错误的。正交投影不具备立体感，也不常用于影视制作。",
            "correction_suggestion": "应更正为：正交投影适用于CAD、工程制图等需要保持形状和尺寸精确性的场景，而不是拍电影。"
          },
          {
            "error_description": "学生提到‘一个有缩放，一个没有’，这种表述不准确且模糊。正交投影中物体大小不随距离变化，而透视投影具有近大远小的效果，而非简单的‘缩放’。",
            "correction_suggestion": "建议更具体地说明：透视投影会使远处物体看起来更小，而正交投影中物体大小与距离无关。"
          }
        ],
        "reviewer": "reviewer_A"
      },
      {
        "student_id": "3",
        "is_correct": false,
        "score": 0.3,
        "analysis": "学生的回答存在多个关键性错误，包括对透视投影和正交投影特点及适用场景的混淆。此外，描述过于简略，缺乏必要的细节来体现对两种投影方式的理解。",
        "errors": [
          {
            "error_description": "学生将透视投影与科学绘图关联，并称其适合科学绘图，这是错误的。透视投影强调视觉真实感而非精确测量。",
            "correction_suggestion": "应指出透视投影适用于游戏、虚拟现实等需要模拟人眼观察效果的场景，而不是用于科学绘图。"
          },
          {
            "error_description": "学生认为正交投影适合拍电影，这是对应用场景的误解。正交投影不具有立体感，且常用于工程制图或CAD等需要保持比例一致的领域。",
            "correction_suggestion": "应说明正交投影适用于CAD、工程制图等需要保持物体尺寸不受距离影响的场景，而电影通常使用的是透视投影以增强真实感。"
          },
          {
            "error_description": "学生仅用“一个有缩放，一个没有”来概括区别，过于简略，未能准确表达透视投影中‘近大远小’和‘平行线相交’等核心特性。",
            "correction_suggestion": "应补充说明透视投影中物体大小随距离变化、有消失点、平行线会相交等特点，以及正交投影中物体大小不变、平行线保持平行等性质。"
          }
        ],
        "reviewer": "reviewer_B"
      }
    ],
    "4": [
      {
        "student_id": "4",
        "is_correct": false,
        "score": 0.85,
        "analysis": "学生的回答整体上是正确的，能够准确区分透视投影和正交投影的核心特点，并能对应到合适的使用场景。然而，回答在表达上略显简略，缺乏标准答案中提到的一些关键术语（如‘消失点’、‘平行线会相交/保持平行’等），导致信息完整性略有不足。",
        "errors": [
          {
            "error_description": "未提及透视投影中的关键几何特性，如‘消失点’、‘平行线会相交’等概念。",
            "correction_suggestion": "建议补充说明：‘透视投影模拟人眼观察方式，具有消失点，且平行线会向远处汇聚并相交’，以更全面地描述其几何特性。"
          },
          {
            "error_description": "未明确指出正交投影中‘物体大小不随距离变化’这一核心属性，仅通过类比扫描仪进行间接描述。",
            "correction_suggestion": "建议直接说明：‘正交投影中物体的大小不随观察距离改变，平行线始终保持平行’，这样可以更清晰地传达其数学性质。"
          }
        ],
        "reviewer": "reviewer_A"
      },
      {
        "student_id": "4",
        "is_correct": false,
        "score": 0.85,
        "analysis": "学生的回答整体上是正确的，能够准确描述透视投影和正交投影的基本特点及其常见应用场景。然而，回答在表达上略显简略，缺少对关键概念如‘消失点’、‘平行线是否相交’等标准答案中提到的核心要点的说明，因此在完整性和严谨性上有一定欠缺。",
        "errors": [
          {
            "error_description": "未提及透视投影中的‘消失点’以及‘平行线会相交’这一关键特性。",
            "correction_suggestion": "建议补充说明：‘透视投影中，平行线会向一个消失点汇聚并相交，这是模拟人眼视觉效果的重要特征。’"
          },
          {
            "error_description": "未明确指出正交投影中‘平行线保持平行’这一几何特性。",
            "correction_suggestion": "建议补充说明：‘正交投影中，无论物体远近，平行线始终保持平行，不会产生透视缩短的效果。’"
          },
          {
            "error_description": "语言表达较为口语化，缺乏学术性与严谨性。",
            "correction_suggestion": "建议使用更规范的语言表述，例如将‘游戏建模的时候会用透视’改为‘适用于需要真实感渲染的场景，如游戏或虚拟现实’，提升专业度。"
          }
        ],
        "reviewer": "reviewer_B"
      }
    ]
  },
  "final_grading_results": [
    {
      "student_id": "1",
      "final_score": 0.925,
      "final_analysis": "综合意见:\n- 评审A: 学生的回答准确地指出了透视投影和正交投影的核心区别，并正确说明了它们各自的适用场景。语言表达清晰，内容完整，符合标准答案的要求。\n- 评审B: 学生的回答整体上是正确的，准确地指出了透视投影和正交投影的核心特点及其常见应用场景。但在描述透视投影时未提及‘平行线会相交’这一关键特性，也未提到‘消失点’的概念；在描述正交投影时没有说明‘平行线保持平行’这一重要属性。这些补充信息有助于更全面地体现两种投影方式的几何特性。",
      "is_controversial": false
    },
    {
      "student_id": "2",
      "final_score": 0.4,
      "final_analysis": "综合意见:\n- 评审A: 学生的回答存在多个关键性错误，混淆了透视投影和正交投影的基本特性。需要重新理解两种投影方式的定义及其应用场景。\n- 评审B: 学生的回答混淆了透视投影和正交投影的基本特性，错误地描述了两种投影的效果，并且对适用场景的说明不够准确。整体理解存在明显偏差，需要重新学习相关知识。",
      "is_controversial": false
    },
    {
      "student_id": "3",
      "final_score": 0.3,
      "final_analysis": "综合意见:\n- 评审A: 学生的回答存在多个关键性错误，包括对透视投影和正交投影特点的混淆，以及适用场景的误判。此外，描述过于简略，缺乏标准答案中要求的核心要点。\n- 评审B: 学生的回答存在多个关键性错误，包括对透视投影和正交投影特点及适用场景的混淆。此外，描述过于简略，缺乏必要的细节来体现对两种投影方式的理解。",
      "is_controversial": false
    },
    {
      "student_id": "4",
      "final_score": 0.85,
      "final_analysis": "综合意见:\n- 评审A: 学生的回答整体上是正确的，能够准确区分透视投影和正交投影的核心特点，并能对应到合适的使用场景。然而，回答在表达上略显简略，缺乏标准答案中提到的一些关键术语（如‘消失点’、‘平行线会相交/保持平行’等），导致信息完整性略有不足。\n- 评审B: 学生的回答整体上是正确的，能够准确描述透视投影和正交投影的基本特点及其常见应用场景。然而，回答在表达上略显简略，缺少对关键概念如‘消失点’、‘平行线是否相交’等标准答案中提到的核心要点的说明，因此在完整性和严谨性上有一定欠缺。",
      "is_controversial": false
    }
  ],
  "final_report": {
    "common_error_patterns": [
      "混淆透视投影与正交投影的基本特性",
      "未能准确描述两种投影方式下的平行线行为（透视投影中平行线相交于消失点，正交投影中平行线保持平行）",
      "对‘消失点’的概念理解不足或未提及",
      "适用场景的说明不够准确或者完全错误"
    ],
    "overall_performance_summary": "根据学生们的得分情况（平均得分为0.625），可以发现大部分学生对于透视投影和正交投影的基本概念有一定的了解，但普遍存在一些共性的理解和表述上的误区。特别是一些关键性概念如‘消失点’以及不同投影方法下平行线的行为特点被部分同学忽略。此外，在应用场合的理解上也存在偏差。",
    "teaching_suggestions": [
      "加强基础概念的教学力度，尤其是关于透视投影中的‘消失点’概念及正交投影与透视投影在处理平行线时的不同表现。",
      "通过更多的实例分析来帮助学生更好地理解这两种投影技术的应用范围及其实际效果差异。",
      "鼓励学生使用图形化工具进行实践操作，直观感受不同投影模式的效果区别，以加深印象。",
      "组织小组讨论活动，让学生之间相互解释这两种投影方式的特点及应用场景，促进深入理解和记忆。",
      "针对错误较多的学生提供额外辅导材料或一对一指导，确保他们能够掌握这些重要知识点。"
    ]
  }
}
```

详细字段说明见下方“批量批改Agent返回字段说明”。

### 批量批改Agent返回字段说明

- question: 本次批改的题目信息，包含题型、题干、难度、标准答案、答案解析等。
- student_answers: 学生作答列表，每个对象包含student_id和answer字段，分别表示学生编号和其作答内容。
- review_results: 每个学生的详细批改结果，key为student_id，value为该学生的评审结果列表。每个评审结果包含：
  - student_id: 学生编号
  - is_correct: 该评审员判断是否完全正确
  - score: 该评审员给出的分数（0~1之间）
  - analysis: 评审员对答案的详细分析
  - errors: 如有错误，列出每个错误的描述和修正建议
  - reviewer: 评审员身份（reviewer_A、reviewer_B）
- final_grading_results: 每个学生的最终得分与综合分析，包含：
  - student_id: 学生编号
  - final_score: 最终得分（通常为两位评审员分数的平均值，或仲裁后结果）
  - final_analysis: 综合评语（可能整合多位评审员意见）
  - is_controversial: 是否经过仲裁（分歧较大时为true，否则为false）
- final_report: 本次批改的全班总结报告，包含：
  - common_error_patterns: 学生常见错误模式列表
  - overall_performance_summary: 整体表现总结（如平均分、普遍问题等）
  - teaching_suggestions: 针对本题教学的改进建议列表


## RAG代理 (RAG Agent)

### 创建Assistant

POST /assistants

```json
{
    "graph_id": "rag_agent", // 从rag_agent，quiz_generator或lesson_planner中选择
    "config": {
        "configurable":{
            "user_id": "用户唯一标识符"
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

#### 流式输出

POST /threads/{thread_id}/runs/stream

```json
{
    "assistant_id": "assistant_id", // assistant_id是上面创建的Assistant的ID
    "input": {
    "messages": "tensorflow.js是什么",
  }
}
```

**响应示例**:
```json
{
  "messages": [
    {
      "content": "tensorflow.js是什么",
      "additional_kwargs": {},
      "response_metadata": {},
      "type": "human",
      "name": null,
      "id": "6c8bf0e2-35a6-4f8a-b4f1-bb7b487e0d64",
      "example": false
    },
    {
      "content": "",
      "additional_kwargs": {
        "function_call": {
          "name": "query_mix_retrieval",
          "arguments": "{\"query\": \"tensorflow.js\\u662f\\u4ec0\\u4e48\"}"
        }
      },
      "response_metadata": {
        "finish_reason": "STOP",
        "model_name": "gemini-2.0-flash-lite",
        "safety_ratings": []
      },
      "type": "ai",
      "name": null,
      "id": "run--b0443709-befb-498a-9772-b7f4f95f5503",
      "example": false,
      "tool_calls": [
        {
          "name": "query_mix_retrieval",
          "args": {
            "query": "tensorflow.js是什么"
          },
          "id": "50ab6025-f99b-459d-b491-17f9bc00a92d",
          "type": "tool_call"
        }
      ],
      "invalid_tool_calls": [],
      "usage_metadata": {
        "input_tokens": 355,
        "output_tokens": 11,
        "total_tokens": 366,
        "input_token_details": {
          "cache_read": 0
        }
      }
    },
    {
      "content": "{\"response\":\"TensorFlow.js 是一个用于机器学习开发的 JavaScript 库，它允许开发者在浏览器和 Node.js 环境中训练和部署机器学习模型。该库提供了 GPU 加速的数学运算能力，并需要内存管理来处理张量和变量。TensorFlow.js 支持低级构建模块和高级 Keras Layers API，使其能够满足不同层次的开发需求。\\n\\nGoogle 提供了 TensorFlow.js，这是其 JavaScript 语言版本的扩展解决方案。该库支持在浏览器端部署机器学习模型，并且与微信小程序有良好的集成。TensorFlow.js 能够加载所有 Python 可以加载的模型，并且在 Node.js 环境中可以直接调用 API，而在浏览器环境中则需要转换为浏览器支持的 JSON 格式。\\n\\nTensorFlow.js 的核心概念包括：\\n\\n*   **张量 (Tensor)**：这是 TensorFlow.js 中数据的中心数据单元，是一维或多维数组。\\n*   **变量 (Variable)**：用张量的值进行初始化，但其值是可变的，可以通过 `assign` 方法更新。\\n*   **操作 (Ops)**：用于操作张量的数据，返回新的张量，例如加法 (`add`)、减法 (`sub`)、乘法 (`mul`) 和平方 (`square`) 等。\\n\\n在 TensorFlow.js 中，可以使用两种方式创建机器学习模型：\\n\\n1.  **Layers API**：提供高级 API，可以像 Keras 一样构建神经网络，支持创建 sequential 模型或 functional 模型。\\n2.  **Core API**：提供低级构建模块，允许开发者通过直接的数学运算来构建模型。\\n\\nTensorFlow.js 还支持端侧机器学习，这有助于分担云端的计算压力并提高隐私性。此外，它还提供了如图像识别、语音识别、物体识别等一系列预训练模型。\\n\\n**References:**\\n[KG] cp07-样章示例-TensorFlow.js应用开发.docx\\n[DC] cp07-样章示例-TensorFlow.js应用开发.docx\\n[DC] cp07-样章示例-TensorFlow.js应用开发.docx\\n[DC] cp07-样章示例-TensorFlow.js应用开发.docx\\n[DC] cp07-样章示例-TensorFlow.js应用开发.docx\"}",
      "additional_kwargs": {},
      "response_metadata": {},
      "type": "tool",
      "name": "query_mix_retrieval",
      "id": "010b2dca-0daa-4c6a-91af-7395052616c0",
      "tool_call_id": "50ab6025-f99b-459d-b491-17f9bc00a92d",
      "artifact": null,
      "status": "success"
    },
    {
      "content": "TensorFlow.js 是一个用于机器学习开发的 JavaScript 库。它允许开发者在浏览器和 Node.js 环境中训练和部署机器学习模型。该库由 Google 提供，支持 GPU 加速的数学运算。\n",
      "additional_kwargs": {},
      "response_metadata": {
        "safety_ratings": [],
        "finish_reason": "STOP",
        "model_name": "gemini-2.0-flash-lite"
      },
      "type": "ai",
      "name": null,
      "id": "run--9ab9f1f6-d51d-42c7-abef-7ad13e20b65f",
      "example": false,
      "tool_calls": [],
      "invalid_tool_calls": [],
      "usage_metadata": {
        "input_tokens": 589,
        "output_tokens": 47,
        "total_tokens": 636,
        "input_token_details": {
          "cache_read": 0
        }
      }
    }
  ]
}
```
