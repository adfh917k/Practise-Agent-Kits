#!/usr/bin/env python3
"""
MCP Server 2: 论文处理和总结服务
功能：
- 提取 PDF 文本
- 使用 LLM 总结论文
- 生成小红书格式内容
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import PyPDF2
import anthropic
from mcp.server import Server
from mcp.types import Tool, TextContent


def log(msg):  
    print(msg, file=sys.stderr, flush=True)

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import ANTHROPIC_API_KEY, CACHE_DIR, USE_LOCAL_MODELS

# log(USE_LOCAL_MODELS)

app = Server("paper-processor")


# if use local models 

if USE_LOCAL_MODELS:
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
    import torch


    # try:
    #     MODEL_PATH = USE_LOCAL_MODELS
    #     log("🔄 使用本地模型推理...")
    #     log(f"🔄 正在加载 {MODEL_PATH}模型...")

    #     # quantization_config = BitsAndBytesConfig(
    #     #     load_in_8bit=True,
    #     #     llm_int8_threshold=6.0,
    #     #     llm_int8_has_fp16_weight=False
    #     # )
    #     tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
    #     model = AutoModelForCausalLM.from_pretrained(
    #         MODEL_PATH,
    #         torch_dtype=torch.bfloat16,
    #         # load_in_8bit=True, 
    #         device_map="auto",
    #         low_cpu_mem_usage=True
    #     )
    #     log("✅ 模型加载完成")
    # except Exception as e:
    #     log(e)
    #     log(f"加载本地模型{MODEL_PATH}失败.....")


# ============================================
# 本地推理函数
# ============================================
def call_local_llm(prompt_text: str, max_tokens: int = 20) -> dict:
    """
    调用本地 Llama 模型生成响应
    
    返回格式：
    {
        "text": "生成的文本",
        "input_tokens": 123,
        "output_tokens": 456
    }
    """

    try:
        MODEL_PATH = USE_LOCAL_MODELS
        log("🔄 使用本地模型推理...")
        log(f"🔄 正在加载 {MODEL_PATH}模型...")

        # quantization_config = BitsAndBytesConfig(
        #     load_in_8bit=True,
        #     llm_int8_threshold=6.0,
        #     llm_int8_has_fp16_weight=False
        # )
        tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
        model = AutoModelForCausalLM.from_pretrained(
            MODEL_PATH,
            torch_dtype=torch.bfloat16,
            # load_in_8bit=True, 
            device_map="auto",
            low_cpu_mem_usage=True
        )
        log("✅ 模型加载完成")
    except Exception as e:
        log(e)
        log(f"加载本地模型{MODEL_PATH}失败.....")

    # 格式化为 Llama 3.1 对话格式
    messages = [
        {"role": "user", "content": prompt_text}
    ]
    
    # 应用聊天模板
    input_text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )
    
    # 编码输入
    inputs = tokenizer(input_text, return_tensors="pt").to(model.device)
    input_length = inputs['input_ids'].shape[1]
    
    log("✅ 模型开始生成")
    # 生成
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_tokens,
            temperature=0.7,
            top_p=0.9,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id
        )
    
    # 解码输出（只返回新生成的部分）
    generated_ids = outputs[0][input_length:]
    generated_text = tokenizer.decode(
        generated_ids,
        skip_special_tokens=True
    )
    
    output_length = len(generated_ids)

    log("✅ 模型生成完毕")
    
    return {
        "text": generated_text.strip(),
        "input_tokens": input_length,
        "output_tokens": output_length
    }


@app.list_tools()
async def list_tools() -> list[Tool]:
    """列出可用工具"""
    return [
        Tool(
            name="extract_pdf_text",
            description="从 PDF 中提取文本内容",
            inputSchema={
                "type": "object",
                "properties": {
                    "pdf_path": {
                        "type": "string",
                        "description": "PDF 文件路径"
                    },
                    "max_pages": {
                        "type": "integer",
                        "description": "最多提取的页数（0 表示全部）",
                        "default": 0
                    }
                },
                "required": ["pdf_path"]
            }
        ),
        Tool(
            name="summarize_paper",
            description="使用 AI 总结论文内容",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "论文文本内容"
                    },
                    "title": {
                        "type": "string",
                        "description": "论文标题"
                    },
                    "style": {
                        "type": "string",
                        "enum": ["academic", "simple", "xiaohongshu"],
                        "default": "xiaohongshu",
                        "description": "总结风格"
                    }
                },
                "required": ["text", "title"]
            }
        ),
        Tool(
            name="format_for_xiaohongshu",
            description="将总结内容格式化为小红书风格",
            inputSchema={
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "论文总结内容"
                    },
                    "title": {
                        "type": "string",
                        "description": "论文标题"
                    },
                    "authors": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "作者列表"
                    }
                },
                "required": ["summary", "title"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """处理工具调用"""
    
    if name == "extract_pdf_text":
        return await extract_pdf_text(
            pdf_path=arguments["pdf_path"],
            max_pages=arguments.get("max_pages", 0)
        )
    
    elif name == "summarize_paper":
        return await summarize_paper(
            text=arguments["text"],
            title=arguments["title"],
            style=arguments.get("style", "xiaohongshu")
        )
    
    elif name == "format_for_xiaohongshu":
        return await format_for_xiaohongshu(
            summary=arguments["summary"],
            title=arguments["title"],
            authors=arguments.get("authors", [])
        )
    
    else:
        raise ValueError(f"Unknown tool: {name}")


async def extract_pdf_text(pdf_path: str, max_pages: int) -> list[TextContent]:
    """提取 PDF 文本"""
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            total_pages = len(pdf_reader.pages)
            
            # 确定要提取的页数
            pages_to_extract = total_pages if max_pages == 0 else min(max_pages, total_pages)
            
            # 提取文本
            text = ""
            for i in range(pages_to_extract):
                page = pdf_reader.pages[i]
                text += page.extract_text() + "\n\n"
            
            result_text = json.dumps({
                "success": True,
                "total_pages": total_pages,
                "extracted_pages": pages_to_extract,
                "text_length": len(text),
                "text": text[:50000]  # 限制长度，避免过大
            }, ensure_ascii=False)
            
            return [TextContent(type="text", text=result_text)]
    
    except Exception as e:
        error_text = json.dumps({
            "success": False,
            "error": str(e)
        })
        return [TextContent(type="text", text=error_text)]


async def summarize_paper(text: str, title: str, style: str) -> list[TextContent]:
    """使用 Claude 总结论文"""
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        
        # 根据风格选择提示词
        prompts = {
            "academic": f"""请以学术风格总结这篇论文《{title}》。
包括：研究背景、主要方法、关键发现、意义。字数 300-500 字。

论文内容：
{text[:15000]}""",
            
            "simple": f"""请用简单易懂的语言总结这篇论文《{title}》。
用通俗的语言解释核心思想。字数 200-300 字。

论文内容：
{text[:15000]}""",
            
            "xiaohongshu": f"""请将这篇 AI 论文《{title}》总结成小红书风格的内容：

要求：
1. 标题要吸引眼球，加 emoji
2. 开头引起兴趣
3. 3-4 个要点，每个用 emoji 标记
4. 语言轻松活泼，但保持专业
5. 结尾引导互动
6. 总长度 150-250 字

论文内容：
{text[:15000]}"""
        }
        
        prompt = prompts.get(style, prompts["xiaohongshu"])


        if USE_LOCAL_MODELS:
            response = call_local_llm(prompt)

            result_text = json.dumps({
                "success": True,
                "summary": response["text"],
                "style": style,
                "model": "Llama-3.1-8B-Instruct",
                "tokens_used": response["input_tokens"] + response["output_tokens"]
            }, ensure_ascii=False, indent=2)

        else:
            # 调用 Claude
            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=512,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            summary = message.content[0].text
            
            result_text = json.dumps({
                "success": True,
                "summary": summary,
                "style": style,
                "tokens_used": message.usage.input_tokens + message.usage.output_tokens
            }, ensure_ascii=False, indent=2)
        
        return [TextContent(type="text", text=result_text)]
    
    except Exception as e:
        error_text = json.dumps({
            "success": False,
            "error": str(e)
        })
        return [TextContent(type="text", text=error_text)]


async def format_for_xiaohongshu(summary: str, title: str, authors: list) -> list[TextContent]:
    """格式化为小红书风格"""
    try:
        # 生成小红书帖子
        post = f"""📚 AI 论文解读 | {title[:30]}{'...' if len(title) > 30 else ''}

{summary}

👨‍🔬 作者：{', '.join(authors[:3])}{'等' if len(authors) > 3 else ''}

#AI论文 #机器学习 #深度学习 #学术前沿 #科研分享

---
💡 想了解更多 AI 前沿论文？关注我，每天分享最新研究成果！
"""
        
        # 生成标签
        tags = [
            "#AI论文", "#机器学习", "#深度学习", 
            "#学术前沿", "#科研分享", "#人工智能"
        ]
        
        result_text = json.dumps({
            "success": True,
            "post_content": post,
            "tags": tags,
            "length": len(post),
            "preview": post[:100] + "..."
        }, ensure_ascii=False, indent=2)
        
        return [TextContent(type="text", text=result_text)]
    
    except Exception as e:
        error_text = json.dumps({
            "success": False,
            "error": str(e)
        })
        return [TextContent(type="text", text=error_text)]


if __name__ == "__main__":
    import asyncio
    import mcp.server.stdio
    
    async def main():
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options()
            )
    
    asyncio.run(main())