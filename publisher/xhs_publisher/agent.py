#!/usr/bin/env python3
"""
Paper Reading Agent - 主控制程序
协调三个 MCP Server 完成完整流程
"""

import asyncio
from asyncio import subprocess
import json
import signal
import sys
import os
import textwrap
from pathlib import Path
from typing import Dict, Any

from PIL import Image, ImageDraw, ImageFont
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from contextlib import AsyncExitStack


from config import MCP_SERVERS, PROJECT_ROOT

def log(msg):  
    print(msg, file=sys.stderr, flush=True)

class PaperReadingAgent:
    """论文阅读 Agent"""

    def __init__(self):
        self.servers: Dict[str, Any] = {}
        self.sessions: Dict[str, ClientSession] = {}
        self.exit_stack = AsyncExitStack()
        self.xhs_session: ClientSession = None  # 小红书 MCP 会话 

    async def __aenter__(self):
        """进入上下文"""
        await self.connect_servers()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """退出上下文，自动清理"""
        await self.exit_stack.aclose()
    
    async def connect_servers(self):
        """连接所有 MCP Server"""
        log("🔌 正在连接 MCP Servers...")
        
        for name, config in MCP_SERVERS.items():
            try:
                # 创建服务器参数
                server_params = StdioServerParameters(
                    command=config["command"],
                    args=config["args"],
                    # cwd=str(PROJECT_ROOT)  # 设置工作目录
                    env=None
                )
                log(f"   ⏳ 正在启动进程...")
                
                # 使用 stdio_client 启动并连接
                read, write = await self.exit_stack.enter_async_context(
                    stdio_client(server_params)
                )
                
                # # 创建会话
                # session = ClientSession(read, write)
                
                # # 初始化
                # await session.initialize()

                session = ClientSession(read, write)
                await session.__aenter__()  # 关键：手动调用上下文管理器
            
                # 初始化
                await session.initialize()

                # async with ClientSession(read, write) as session:
                #     # Initialize the session
                #     await session.initialize()
                    
                self.sessions[name] = session
                self.servers[name] = session
                    
                log(f"  ✅ {name} server 已连接")
                
            except Exception as e:
                log(f"  ❌ {name} server 连接失败: {e}")
                raise
        
        log("✅ 所有 MCP Servers 已连接\n")

    async def connect_xhs_server(self, url: str = "http://localhost:8000/sse"):
        """连接小红书 MCP Server (SSE 模式)"""
        log(f"🔌 正在连接小红书 MCP Server: {url}")

        try:
            # 使用 sse_client 连接
            read, write = await self.exit_stack.enter_async_context(
                sse_client(url)
            )

            # 创建会话
            session = ClientSession(read, write)
            await session.__aenter__()
            await session.initialize()

            self.xhs_session = session
            log("✅ 小红书 MCP Server 已连接")

        except Exception as e:
            log(f"❌ 小红书 MCP Server 连接失败: {e}")
            raise
    
    async def disconnect_servers(self):
        """断开所有连接"""
        log("\n🔌 正在断开连接...")
        
        for name, session_info in self.sessions.items():
            try:
                # 先尝试优雅关闭 session
                if 'session' in session_info:
                    try:
                        await session_info['session'].__aexit__(None, None, None)
                    except (RuntimeError, asyncio.CancelledError) as e:
                        # 忽略 cancel scope 错误
                        if "cancel scope" not in str(e):
                            raise
                
                # 确保进程被终止
                if 'process' in session_info:
                    process = session_info['process']
                    if process.poll() is None:  # 进程还在运行
                        process.terminate()
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            process.kill()
                
                log(f"  ✅ {name} server 已断开")
                
            except Exception as e:
                # 只显示非预期的错误
                if "cancel scope" not in str(e) and not isinstance(e, asyncio.CancelledError):
                    log(f"  ⚠️  {name} server 断开时出错: {e}")


    
    async def run_workflow(self, query: str, max_papers: int = 3):
        """执行完整工作流"""
        log("="*60)
        log(f"🚀 开始paper reading agent工作流: {query}")
        log("="*60)
        
        try:
            # ===== 步骤 1: 搜索论文 =====
            log(f"\n📚 步骤 1: 根据 给定query关键词 >>> {query} <<< 搜索 Arxiv 论文...")
            papers = await self.search_papers(query, max_papers)
            
            if not papers:
                log("❌ 没有找到论文")
                return
            
            log(f"✅ 找到 {len(papers)} 篇论文")
            for i, paper in enumerate(papers, 1):
                log(f"   {i}. {paper['title'][:60]}...")
            
            # ===== 步骤 2: 选择第一篇论文并处理 =====
            selected_paper = papers[0]
            log(f"\n📖 选择论文: {selected_paper['title']}")
            
            # 2.1 下载 PDF
            log("\n⬇️  步骤 2.1: 下载 PDF...")
            pdf_info = await self.download_paper(
                selected_paper['paper_id'],
                selected_paper['pdf_url']
            )
            log(f"✅ PDF 已下载: {pdf_info['path']}")
            
            # 2.2 提取文本
            log("\n📄 步骤 2.2: 提取 PDF 文本...")
            text_info = await self.extract_text(pdf_info['path'])
            log(f"✅ 提取了 {text_info['extracted_pages']} 页，"
                  f"共 {text_info['text_length']} 字符")
            
            # 2.3 总结论文
            log("\n🤖 步骤 2.3: AI 总结论文...")
            summary_info = await self.summarize_paper(
                text_info['text'],
                selected_paper['title']
            )
            log(f"✅ 总结完成，使用了 {summary_info['tokens_used']} tokens")
            log("\n总结内容：")
            log("-" * 60)
            log(summary_info['summary'])
            log("-" * 60)
            
            # # 2.4 格式化为小红书风格
            print("\n✨ 步骤 2.4: 格式化为小红书风格...")
            formatted = await self.format_for_xiaohongshu(
                summary_info['summary'],
                selected_paper['title'],
                selected_paper['authors']
            )
            print("✅ 格式化完成")
            
            # ===== 步骤 3: 发布到小红书 =====
            print("\n📱 步骤 3: 发布到小红书...")
            
            # 3.1 预览
            print("\n👀 步骤 3.1: 预览帖子...")
            preview_info = await self.preview_post(
                formatted['post_content'],
                formatted['tags']
            )
            print(preview_info['preview'])

            # 3.2 确认发布
            confirm = input("\n是否发布到小红书？(y/n): ").strip().lower()

            if confirm == 'y':
                # 3.2.1 生成封面图
                print("\n🎨 步骤 3.2: 生成封面图...")
                post_title = formatted.get('title', selected_paper['title'][:20])
                cover_image = self.generate_cover_image(post_title)

                # 3.3 连接小红书 MCP Server
                print("\n🔌 步骤 3.3: 连接小红书服务...")
                await self.connect_xhs_server()

                # 3.4 登录小红书
                # print("\n🔐 步骤 3.4: 登录小红书...")
                # await self.login_xhs()

                # 3.5 发布到小红书
                print("\n📤 步骤 3.5: 发布帖子...")
                publish_info = await self.publish_to_xiaohongshu(
                    title=post_title,
                    content=formatted['post_content'],
                    tags=formatted['tags'],
                    images=[cover_image]
                )
                print(f"✅ 发布成功！")
                if publish_info.get('publish_result'):
                    pub_result = publish_info['publish_result']
                    print(f"   执行时间: {publish_info.get('execution_time', 0)} 秒")
            else:
                print("❌ 取消发布")

            log("\n" + "="*60)
            log("✅ 工作流完成！")
            log("="*60)
        
        except Exception as e:
            log(f"\n❌ 工作流出错: {e}")
            import traceback
            traceback.print_exc()
    
    # ===== Crawler 相关方法 =====
    
    async def search_papers(self, query: str, max_results: int) -> list:
        """搜索论文"""
        log("   [DEBUG] 开始调用 MCP search_papers...")
        result = await self.servers['crawler'].call_tool(
            "search_papers",
            {
                "query": query,
                "max_results": max_results,
                "sort_by": "relevance"
            }
        )
        log("   [DEBUG] MCP 调用返回")

        data = json.loads(result.content[0].text)
        if data['success']:
            return data['papers']
        else:
            raise Exception(data['error'])
    
    async def download_paper(self, paper_id: str, pdf_url: str) -> dict:
        """下载论文"""
        result = await self.servers['crawler'].call_tool(
            "download_paper",
            {
                "paper_id": paper_id,
                "pdf_url": pdf_url
            }
        )
        
        data = json.loads(result.content[0].text)
        if data['success']:
            return data
        else:
            raise Exception(data['error'])
    
    # ===== Processor 相关方法 =====
    
    async def extract_text(self, pdf_path: str) -> dict:
        """提取 PDF 文本"""
        result = await self.servers['processor'].call_tool(
            "extract_pdf_text",
            {
                "pdf_path": pdf_path,
                "max_pages": 10  # 限制页数以加快处理
            }
        )
        
        data = json.loads(result.content[0].text)
        if data['success']:
            return data
        else:
            raise Exception(data['error'])
    
    async def summarize_paper(self, text: str, title: str) -> dict:
        """总结论文"""
        result = await self.servers['processor'].call_tool(
            "summarize_paper",
            {
                "text": text,
                "title": title,
                "style": "xiaohongshu"
            }
        )
        
        data = json.loads(result.content[0].text)
        if data['success']:
            return data
        else:
            raise Exception(data['error'])
    
    async def format_for_xiaohongshu(self, summary: str, title: str, authors: list) -> dict:
        """格式化为小红书风格"""
        result = await self.servers['processor'].call_tool(
            "format_for_xiaohongshu",
            {
                "summary": summary,
                "title": title,
                "authors": authors
            }
        )
        
        data = json.loads(result.content[0].text)
        if data['success']:
            return data
        else:
            raise Exception(data['error'])
    
    # ===== Publisher 相关方法 =====
    
    async def login_xiaohongshu(self):
        """登录小红书"""
        result = await self.servers['publisher'].call_tool(
            "login",
            {
                "username": "demo_user",
                "password": "demo_pass"
            }
        )
        
        data = json.loads(result.content[0].text)
        if not data['success']:
            raise Exception(data['error'])
    
    async def preview_post(self, content: str, tags: list) -> dict:
        """预览帖子"""
        result = await self.servers['publisher'].call_tool(
            "preview_post",
            {
                "content": content,
                "tags": tags
            }
        )
        
        data = json.loads(result.content[0].text)
        if data['success']:
            return data
        else:
            raise Exception(data['error'])
    
    async def publish_post(self, content: str, tags: list) -> dict:
        """发布帖子"""
        result = await self.servers['publisher'].call_tool(
            "publish_post",
            {
                "content": content,
                "tags": tags
            }
        )

        data = json.loads(result.content[0].text)
        if data['success']:
            return data
        else:
            raise Exception(data['error'])

    # ===== 图片生成方法 =====

    def generate_cover_image(self, title: str, output_dir: str = None) -> str:
        """
        生成带标题的封面图

        Args:
            title: 标题文字
            output_dir: 输出目录，默认为 cache 目录

        Returns:
            生成的图片绝对路径
        """
        if output_dir is None:
            output_dir = str(PROJECT_ROOT / "cache")

        os.makedirs(output_dir, exist_ok=True)

        # 图片尺寸 (小红书推荐 3:4 比例)
        width, height = 1080, 1440

        # 创建渐变背景
        img = Image.new('RGB', (width, height), '#1a1a2e')
        draw = ImageDraw.Draw(img)

        # 绘制渐变背景
        for y in range(height):
            r = int(26 + (50 - 26) * y / height)
            g = int(26 + (30 - 26) * y / height)
            b = int(46 + (80 - 46) * y / height)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # 绘制装饰元素
        draw.ellipse([50, 100, 250, 300], outline='#e94560', width=3)
        draw.ellipse([width-250, height-300, width-50, height-100], outline='#0f3460', width=3)

        # 加载字体
        try:
            # 尝试使用系统中文字体
            font_paths = [
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
                "C:/Windows/Fonts/msyh.ttc",  # Windows 微软雅黑
                "/System/Library/Fonts/PingFang.ttc",  # macOS
            ]
            font = None
            for fp in font_paths:
                if os.path.exists(fp):
                    font = ImageFont.truetype(fp, 60)
                    small_font = ImageFont.truetype(fp, 36)
                    break
            if font is None:
                font = ImageFont.load_default()
                small_font = font
        except Exception:
            font = ImageFont.load_default()
            small_font = font

        # 绘制标题 (自动换行)
        max_chars_per_line = 12
        wrapped_title = textwrap.fill(title, width=max_chars_per_line)
        lines = wrapped_title.split('\n')

        # 计算文字位置 (居中)
        y_start = height // 2 - len(lines) * 40
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            x = (width - text_width) // 2
            y = y_start + i * 80

            # 绘制文字阴影
            draw.text((x+2, y+2), line, font=font, fill='#000000')
            # 绘制文字
            draw.text((x, y), line, font=font, fill='#ffffff')

        # 绘制底部标签
        tag_text = "📚 AI 论文解读"
        bbox = draw.textbbox((0, 0), tag_text, font=small_font)
        tag_width = bbox[2] - bbox[0]
        draw.text(((width - tag_width) // 2, height - 150), tag_text, font=small_font, fill='#e94560')

        # 保存图片
        import hashlib
        filename = hashlib.md5(title.encode()).hexdigest()[:8] + "_cover.png"
        output_path = os.path.join(output_dir, filename)
        img.save(output_path, 'PNG', quality=95)

        log(f"✅ 封面图已生成: {output_path}")
        return output_path

    # ===== 小红书 MCP 相关方法 =====

    async def publish_to_xiaohongshu(self, title: str, content: str, tags: list = None, images: list = None) -> dict:
        """
        发布帖子到小红书（通过 xhs-toolkit MCP）

        Args:
            title: 帖子标题
            content: 帖子内容
            tags: 话题标签列表
            images: 图片路径列表（至少需要一张图片）

        Returns:
            发布结果
        """
        if not self.xhs_session:
            raise Exception("未连接小红书 MCP Server，请先调用 connect_xhs_server()")

        # 小红书限制：标题 50 字符，内容 1000 字符
        if len(title) > 50:
            title = title[:47] + "..."
            log(f"⚠️ 标题已截断至 50 字符")

        if len(content) > 1000:
            content = content[:997] + "..."
            log(f"⚠️ 内容已截断至 1000 字符")

        # 1. 启动发布任务
        log("📤 启动小红书发布任务...")
        params = {
            "title": title,
            "content": content,
            "topics": tags or []
        }
        if images:
            params["images"] = images

        result = await self.xhs_session.call_tool(
            "smart_publish_note",
            params
        )

        data = json.loads(result.content[0].text)
        if not data.get('success'):
            raise Exception(data.get('message', '启动发布任务失败'))

        task_id = data['task_id']
        log(f"✅ 发布任务已启动，任务ID: {task_id}")

        # 2. 轮询检查任务状态
        log("⏳ 等待发布完成...")
        max_wait = 120  # 最大等待 120 秒
        wait_time = 0
        poll_interval = 3  # 每 3 秒检查一次

        while wait_time < max_wait:
            await asyncio.sleep(poll_interval)
            wait_time += poll_interval

            status_result = await self.xhs_session.call_tool(
                "check_task_status",
                {"task_id": task_id}
            )
            status_data = json.loads(status_result.content[0].text)

            status = status_data.get('status', '')
            progress = status_data.get('progress', 0)
            message = status_data.get('message', '')

            log(f"   [{progress}%] {message}")

            if status_data.get('is_completed'):
                break

        # 3. 获取最终结果
        final_result = await self.xhs_session.call_tool(
            "get_task_result",
            {"task_id": task_id}
        )
        final_data = json.loads(final_result.content[0].text)

        if final_data.get('success') and final_data.get('status') == 'completed':
            log("✅ 发布成功！")
            return final_data
        else:
            raise Exception(final_data.get('message', '发布失败'))

    async def login_xhs(self) -> dict:
        """登录小红书（通过 xhs-toolkit MCP）"""
        if not self.xhs_session:
            raise Exception("未连接小红书 MCP Server，请先调用 connect_xhs_server()")

        log("🔐 登录小红书...")
        result = await self.xhs_session.call_tool(
            "login_xiaohongshu",
            {"force_relogin": False}
        )

        data = json.loads(result.content[0].text)
        if data.get('success'):
            log(f"✅ {data.get('message', '登录成功')}")
            return data
        else:
            raise Exception(data.get('message', '登录失败'))


async def main():
    """主函数"""
    agent = PaperReadingAgent()

    # 设置信号处理器
    loop = asyncio.get_running_loop()

    def shutdown():
        log("\n⚠️ 收到中断信号，正在清理...")
        for task in asyncio.all_tasks(loop):
            task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown)

    try:
        await agent.connect_servers()
        await agent.run_workflow(query="image generation", max_papers=3)
    except asyncio.CancelledError:
        log("任务已取消")
    finally:
        await agent.exit_stack.aclose()  # 正确关闭所有子进程
        try:
            await agent.exit_stack.aclose()
        except RuntimeError as e:
            # 忽略 AnyIO 的 cancel scope 错误
            if "cancel scope" in str(e):
                pass
            # else:
            #     raise e
            sys.exit(0)
        except Exception:
            # 忽略其他清理时的非关键错误
            pass
        log("清理完成")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass