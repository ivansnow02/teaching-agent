# 教学代理API使用指南

## 概述

本文档提供了如何使用教学代理API的详细说明。
- **章节目录生成器**：用于生成课程的章节目录。
- **章节课件生成器**：用于生成每个章节的详细课件内容
- **RAG代理 (RAG Agent)**: 基于检索增强生成的上下文问答

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

当status变成success时，使用加入Run（获取结果） response.content即为结构化课件内容。

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
  "response": {
    "content": "### 教案：图形学中的数学基础知识教学方案\n\n---\n\n## 一、教案目标\n\n**教学目标**：\n学生能够理解并掌握计算机图形学中所涉及的数学基础知识，包括坐标系统、向量运算、矩阵变换、投影变换等内容，并具备将这些知识应用于实际问题的能力。\n\n---\n\n## 二、教学内容与安排\n\n### 第一部分：坐标系统的讲解（40分钟）\n\n#### 教学目标：\n1. 理解二维和三维坐标系的基本结构。\n2. 掌握齐次坐标的表示方法及其在几何变换中的作用。\n\n#### 教学内容：\n- **二维坐标系**：x轴与y轴构成平面坐标系，点用(x, y)表示。\n- **三维坐标系**：增加z轴，形成空间坐标系，点用(x, y, z)表示。\n- **齐次坐标**：引入额外维度，如(x, y, 1)或(x, y, z, 1)，用于统一处理平移、旋转、缩放等操作。\n\n#### 教学方法：\n- 图形演示法\n- 实例分析法\n- 板书/多媒体结合讲解\n\n#### 教学评估：\n- 提问互动\n- 坐标系绘制练习\n\n---\n\n### 第二部分：向量运算详解（30分钟）\n\n#### 教学目标：\n1. 掌握向量加减法的计算及几何意义。\n2. 理解点积与叉积的定义、公式及其应用。\n\n#### 教学内容：\n\n| 运算 | 公式 | 几何意义 |\n|------|------|----------|\n| 向量加法 | $ \\vec{a} + \\vec{b} = (a_x + b_x, a_y + b_y) $ | 表示两个方向的合成 |\n| 向量减法 | $ \\vec{a} - \\vec{b} = (a_x - b_x, a_y - b_y) $ | 表示从一点到另一点的方向 |\n| 点积 | $ \\vec{a} \\cdot \\vec{b} = a_x b_x + a_y b_y $ | 衡量两向量夹角的余弦值 |\n| 叉积 | $ \\vec{a} \\times \\vec{b} = |\\vec{a}||\\vec{b}| \\sin(\\theta) $ | 表示垂直于两向量的新向量 |\n\n#### 教学方法：\n- 黑板推导\n- 动画图解展示\n- 小组讨论与练习\n\n#### 教学评估：\n- 向量运算小测验\n- 向量应用案例分析\n\n---\n\n### 第三部分：矩阵变换（40分钟）\n\n#### 教学目标：\n1. 掌握基本的矩阵运算规则。\n2. 理解平移、旋转、缩放的矩阵表示形式及其在图形变换中的应用。\n\n#### 教学内容：\n\n| 变换类型 | 矩阵表示（2D） | 应用场景 |\n|----------|----------------|----------|\n| 平移     | $\\begin{bmatrix} 1 & 0 & t_x \\\\ 0 & 1 & t_y \\\\ 0 & 0 & 1 \\end{bmatrix}$ | 改变物体位置 |\n| 缩放     | $\\begin{bmatrix} s_x & 0 & 0 \\\\ 0 & s_y & 0 \\\\ 0 & 0 & 1 \\end{bmatrix}$ | 调整大小 |\n| 旋转     | $\\begin{bmatrix} \\cos\\theta & -\\sin\\theta & 0 \\\\ \\sin\\theta & \\cos\\theta & 0 \\\\ 0 & 0 & 1 \\end{bmatrix}$ | 改变方向 |\n\n#### 教学方法：\n- 演示矩阵运算过程\n- 使用动画展示变换效果\n- 学生动手练习矩阵乘法\n\n#### 教学评估：\n- 矩阵变换作业题\n- 编程实现简单变换\n\n---\n\n### 第四部分：投影变换（30分钟）\n\n#### 教学目标：\n1. 理解正交投影与透视投影的区别。\n2. 掌握两种投影方式的数学表达形式。\n\n#### 教学内容：\n\n| 投影类型 | 数学表达 | 特点 |\n|----------|-----------|------|\n| 正交投影 | 不考虑距离变化，保持平行线不变 | 适用于工程制图 |\n| 透视投影 | 引入视点概念，近大远小 | 适用于真实感渲染 |\n\n**透视投影矩阵示例**（简化版）：\n$$\nP = \\begin{bmatrix}\n\\frac{2n}{r-l} & 0 & \\frac{r+l}{r-l} & 0 \\\\\n0 & \\frac{2n}{t-b} & \\frac{t+b}{t-b} & 0 \\\\\n0 & 0 & -\\frac{f+n}{f-n} & -\\frac{2fn}{f-n} \\\\\n0 & 0 & -1 & 0\n\\end{bmatrix}\n$$\n\n#### 教学方法：\n- 对比讲解+动画演示\n- 示例代码展示投影效果\n\n#### 教学评估：\n- 区分正交与透视投影的选择题\n- 编写投影变换程序片段\n\n---\n\n### 第五部分：图解与示例辅助教学（45分钟）\n\n#### 教学目标：\n通过图解、实例和可视化工具帮助学生更直观地理解抽象数学概念。\n\n#### 教学内容：\n- 向量图解：箭头表示方向与长度\n- 矩阵变换演示：图像随矩阵改变而变形\n- 投影图示：对比正交与透视效果差异\n\n#### 教学方法：\n- 使用GeoGebra、Desmos等动态软件演示\n- 展示实际游戏或图形引擎中的变换效果\n- 学生动手绘图练习\n\n#### 教学评估：\n- 根据图解回答问题\n- 绘图任务反馈\n\n---\n\n### 第六部分：课堂练习与课后作业（共约3小时）\n\n#### 课堂练习（75分钟）：\n1. **坐标系建模**：绘制不同坐标系下的三角形、立方体。\n2. **矩阵变换实验**：完成一次复合变换（先旋转再平移）。\n3. **光线追踪模拟**：使用向量与点积判断光线是否与球体相交。\n\n#### 课后作业（建议3.5小时）：\n1. **虚拟现实场景设计**：创建一个包含光照、物体移动的小型VR场景。\n2. **LOD技术实现**：编写程序根据视角距离切换模型细节层次。\n3. **重要性采样演示**：编写代码模拟基于概率密度函数的采样过程。\n\n#### 教学评估：\n- 课堂练习表现评分\n- 课后作业提交与代码审查\n\n---\n\n## 三、教学资源推荐\n\n- 教材：《计算机图形学基础》《线性代数》《高等数学》\n- 工具：OpenGL、Unity、Python Matplotlib、GeoGebra\n- 辅助材料：图解卡片、教学视频、代码模板\n\n---\n\n## 四、教学时间总览\n\n| 教学模块 | 时间分配 |\n|----------|----------|\n| 坐标系统 | 40分钟 |\n| 向量运算 | 30分钟 |\n| 矩阵变换 | 40分钟 |\n| 投影变换 | 30分钟 |\n| 图示辅助 | 45分钟 |\n| 课堂练习 | 75分钟 |\n| 总计     | **约4小时** |\n\n---\n\n## 五、教学反思与优化建议\n\n- **优点**：课程结构清晰，涵盖图形学核心数学内容；理论与实践结合紧密。\n- **改进方向**：\n  - 增加更多编程实操环节；\n  - 引入图形引擎API（如Unity、Three.js）进行实战演练；\n  - 针对不同基础的学生提供差异化练习。\n\n---\n\n**结语**：本教案旨在通过系统化的教学安排，帮助学生建立扎实的图形学数学基础，并能灵活运用于实际开发与项目实践中。",
    "additional_kwargs": {
      "refusal": null
    },
    "response_metadata": {
      "token_usage": {
        "completion_tokens": 1801,
        "prompt_tokens": 2348,
        "total_tokens": 4149,
        "completion_tokens_details": null,
        "prompt_tokens_details": null
      },
      "model_name": "qwen3-235b-a22b",
      "system_fingerprint": null,
      "id": "chatcmpl-ab1888b0-d9bc-9148-8686-b5c8b1e1507e",
      "service_tier": null,
      "finish_reason": "stop",
      "logprobs": null
    },
    "type": "ai",
    "name": null,
    "id": "run--c5fb25a2-0040-47b5-a484-7bc5be1a082e-0",
    "example": false,
    "tool_calls": [],
    "invalid_tool_calls": [],
    "usage_metadata": {
      "input_tokens": 2348,
      "output_tokens": 1801,
      "total_tokens": 4149,
      "input_token_details": {},
      "output_token_details": {}
    }
  }
}
```

## RAG代理 (RAG Agent)

### 创建Assistant

POST /assistants

```json
{
    "graph_id": "rag_agent", // 从rag_agent，quiz_generator或lesson_planner中选择
    "config": {
        "configurable":{
            "course_id": "用户唯一标识符"
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

这个可以用流式

```json
{
    "assistant_id": "assistant_id", // assistant_id是上面创建的Assistant的ID
    "input": {
    "messages": "tensorflow.js是什么",
    "max_rewrite": 3,
    "rewrite_count": 0
  }
}
```
