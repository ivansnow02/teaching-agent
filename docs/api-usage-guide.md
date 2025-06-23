# 教学代理API使用指南

## 概述

本文档提供了如何使用教学代理API的详细说明。该API提供三个专门的AI代理：
- **课程规划器 (Lesson Planner)**: 从教学大纲生成结构化课程计划
- **RAG代理 (RAG Agent)**: 基于检索增强生成的上下文问答
- **测验生成器 (Quiz Generator)**: 创建练习题和评估

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

#### LLM

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

先在`/documents/upload/{user_id}`端点上传知识库，以便RAG代理可以访问这些文档进行问答。


## 1. 课程规划器 (Lesson Planner)


### 创建Assistant

POST /assistants

```json
{
    "graph_id": "lesson_planner", // 从rag_agent，quiz_generator或lesson_planner中选择
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
    "raw_syllabus": "您的教学大纲内容...",
    "num_choice_questions": 5,
    "num_short_answer_questions": 3,
    "num_true_or_false_questions": 4
  }
}
```

```json

```

**响应示例**:
```json
{
  "final_lesson_plan": "# Python编程基础课程计划\n\n## 第一章：Python入门\n...",
  "parsed_syllabus": [
    {
      "chapter_title": "Python入门",
      "knowledge_points": [
        "Python语法和基本数据类型",
        "变量和操作符"
      ]
    }
  ],
  "chapter_results": [
    {
      "chapter_title": "Python入门",
      "content": "详细的教学内容...",
      "time_allocation": {
        "activities": [
          {
            "name": "理论讲解",
            "minutes": 30
          },
          {
            "name": "实践练习",
            "minutes": 20
          }
        ],
        "rationale": "时间分配的理由..."
      },
      "practice_exercises": {
        "multiple_choice": [...],
        "short_answer": [...],
        "true_or_false": [...]
      }
    }
  ]
}
```

## 2. RAG代理 (RAG Agent)

### 提问


**请求示例**:

```json
"input": {
      "content": "tensorflow.js是什么"
},

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

## 3. 测验生成器 (Quiz Generator)

### 生成测验


**请求示例**:

```json
"input": {
  "content": "需要生成测验的内容...",
  "num_choice_questions": 3,
  "num_short_answer_questions": 2,
  "num_true_or_false_questions": 2
},
```

**响应示例**:
```json
{
  "practice_exercises": {
    "multiple_choice": [
      {
        "question": {
          "question": "在Python中，如何定义一个函数？",
          "knowledge_points": ["函数定义", "Python语法"]
        },
        "distractors": [ // 错误选项
          "使用function关键字",
          "使用func关键字",
          "使用method关键字"
        ],
        "answer": "使用def关键字" // 正确答案
      }
    ],
    "short_answer": [
      {
        "question": {
          "question": "解释Python函数中return语句的作用。",
          "knowledge_points": ["函数返回值", "return语句"]
        },
        "reference_answer": "return语句用于从函数中返回一个值给调用者，并终止函数的执行。"
      }
    ],
    "true_or_false": [
      {
        "question": {
          "question": "Python函数必须有返回值。",
          "knowledge_points": ["函数返回值"]
        },
        "answer": false
      }
    ]
  }
}
```
