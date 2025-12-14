#!/usr/bin/env python3
"""
MCP Server 3: 小红书发布服务
功能：
- 模拟登录（Demo 版本）
- 发布内容
- 生成预览
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from datetime import datetime

from mcp.server import Server
from mcp.types import Tool, TextContent

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import XIAOHONGSHU_USERNAME, CACHE_DIR

app = Server("xiaohongshu-publisher")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """列出可用工具"""
    return [
        Tool(
            name="login",
            description="登录小红书账号（Demo 版本，模拟登录）",
            inputSchema={
                "type": "object",
                "properties": {
                    "username": {
                        "type": "string",
                        "description": "用户名"
                    },
                    "password": {
                        "type": "string",
                        "description": "密码"
                    }
                },
                "required": ["username", "password"]
            }
        ),
        Tool(
            name="publish_post",
            description="发布小红书帖子",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "帖子内容"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "标签列表"
                    },
                    "images": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "图片路径列表（可选）",
                        "default": []
                    }
                },
                "required": ["content"]
            }
        ),
        Tool(
            name="preview_post",
            description="预览帖子效果",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "帖子内容"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "标签列表"
                    }
                },
                "required": ["content"]
            }
        ),
        Tool(
            name="get_publish_status",
            description="获取发布状态",
            inputSchema={
                "type": "object",
                "properties": {
                    "post_id": {
                        "type": "string",
                        "description": "帖子 ID"
                    }
                },
                "required": ["post_id"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """处理工具调用"""
    
    if name == "login":
        return await login(
            username=arguments["username"],
            password=arguments["password"]
        )
    
    elif name == "publish_post":
        return await publish_post(
            content=arguments["content"],
            tags=arguments.get("tags", []),
            images=arguments.get("images", [])
        )
    
    elif name == "preview_post":
        return await preview_post(
            content=arguments["content"],
            tags=arguments.get("tags", [])
        )
    
    elif name == "get_publish_status":
        return await get_publish_status(
            post_id=arguments["post_id"]
        )
    
    else:
        raise ValueError(f"Unknown tool: {name}")


async def login(username: str, password: str) -> list[TextContent]:
    """模拟登录"""
    try:
        # Demo: 模拟登录成功
        await asyncio.sleep(0.5)  # 模拟网络延迟
        
        result_text = json.dumps({
            "success": True,
            "message": "登录成功（Demo 模式）",
            "username": username,
            "session_id": f"mock_session_{datetime.now().timestamp()}"
        }, ensure_ascii=False)
        
        return [TextContent(type="text", text=result_text)]
    
    except Exception as e:
        error_text = json.dumps({
            "success": False,
            "error": str(e)
        })
        return [TextContent(type="text", text=error_text)]


async def publish_post(content: str, tags: list, images: list) -> list[TextContent]:
    """发布帖子"""
    try:
        # Demo: 模拟发布
        await asyncio.sleep(1.0)  # 模拟发布延迟
        
        # 生成模拟的帖子 ID
        post_id = f"post_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # 保存到本地（模拟发布记录）
        post_record = {
            "post_id": post_id,
            "content": content,
            "tags": tags,
            "images": images,
            "published_at": datetime.now().isoformat(),
            "status": "published",
            "views": 0,
            "likes": 0,
            "comments": 0
        }
        
        record_path = CACHE_DIR / f"{post_id}.json"
        with open(record_path, 'w', encoding='utf-8') as f:
            json.dump(post_record, f, ensure_ascii=False, indent=2)
        
        result_text = json.dumps({
            "success": True,
            "message": "发布成功（Demo 模式）",
            "post_id": post_id,
            "post_url": f"https://www.xiaohongshu.com/explore/{post_id}",
            "published_at": post_record["published_at"],
            "record_saved": str(record_path)
        }, ensure_ascii=False, indent=2)
        
        return [TextContent(type="text", text=result_text)]
    
    except Exception as e:
        error_text = json.dumps({
            "success": False,
            "error": str(e)
        })
        return [TextContent(type="text", text=error_text)]


async def preview_post(content: str, tags: list) -> list[TextContent]:
    """预览帖子"""
    try:
        # 生成预览
        preview = f"""
{'='*50}
小红书帖子预览
{'='*50}

{content}

标签：{' '.join(tags)}

{'='*50}
字数统计：{len(content)} 字
标签数量：{len(tags)} 个
预计阅读时间：{len(content) // 200 + 1} 分钟
{'='*50}
"""
        
        result_text = json.dumps({
            "success": True,
            "preview": preview,
            "stats": {
                "content_length": len(content),
                "tags_count": len(tags),
                "estimated_read_time": len(content) // 200 + 1
            }
        }, ensure_ascii=False, indent=2)
        
        return [TextContent(type="text", text=result_text)]
    
    except Exception as e:
        error_text = json.dumps({
            "success": False,
            "error": str(e)
        })
        return [TextContent(type="text", text=error_text)]


async def get_publish_status(post_id: str) -> list[TextContent]:
    """获取发布状态"""
    try:
        record_path = CACHE_DIR / f"{post_id}.json"
        
        if not record_path.exists():
            raise FileNotFoundError(f"帖子记录不存在: {post_id}")
        
        with open(record_path, 'r', encoding='utf-8') as f:
            post_record = json.load(f)
        
        # 模拟一些互动数据
        import random
        post_record["views"] = random.randint(100, 1000)
        post_record["likes"] = random.randint(10, 100)
        post_record["comments"] = random.randint(0, 20)
        
        result_text = json.dumps({
            "success": True,
            "post_record": post_record
        }, ensure_ascii=False, indent=2)
        
        return [TextContent(type="text", text=result_text)]
    
    except Exception as e:
        error_text = json.dumps({
            "success": False,
            "error": str(e)
        })
        return [TextContent(type="text", text=error_text)]


# if __name__ == "__main__":
#     import mcp.server.stdio
#     mcp.server.stdio.run(app)

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