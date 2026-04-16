"""
Interview Task Queue Service
管理每个section的独立任务队列，确保同section内任务FIFO顺序，不同section并行执行
"""
import asyncio
from collections import defaultdict
from typing import Any, Callable, Dict


class SectionTaskQueue:
    """
    为每个section维护独立的任务队列，确保同section内任务的FIFO顺序
    不同section的任务可以并行执行
    """
    def __init__(self):
        self._queues: Dict[str, asyncio.Queue[tuple]] = defaultdict(lambda: asyncio.Queue())
        self._workers: Dict[str, asyncio.Task[None]] = {}
        
    async def add_task(self, section_key: str, coro_func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """添加任务到指定section的队列"""
        queue = self._queues[section_key]
        await queue.put((coro_func, args, kwargs))
        print(f"[SectionTaskQueue] 📥 Task added to queue: {section_key}, function: {coro_func.__name__}")
        
        # 确保该section有worker在运行
        if section_key not in self._workers or self._workers[section_key].done():
            print(f"[SectionTaskQueue] 🔧 Creating new worker for section: {section_key}")
            self._workers[section_key] = asyncio.create_task(
                self._section_worker(section_key)
            )
            print(f"[SectionTaskQueue] ✅ Worker created for section: {section_key}")
        else:
            print(f"[SectionTaskQueue] ℹ️ Worker already exists for section: {section_key}")
    
    async def _section_worker(self, section_key: str):
        """处理特定section的任务队列（FIFO顺序）"""
        queue = self._queues[section_key]
        print(f"[SectionTaskQueue] 🏃 Worker started for section: {section_key}")
        
        while True:
            try:
                # 等待任务，如果队列空闲10秒后自动退出worker
                print(f"[SectionTaskQueue] ⏳ Worker {section_key} waiting for task (timeout: 10s)...")
                coro_func, args, kwargs = await asyncio.wait_for(
                    queue.get(), timeout=10.0
                )
                print(f"[SectionTaskQueue] 📨 Worker {section_key} received task: {coro_func.__name__}")
                
                try:
                    # 执行任务
                    print(f"[SectionTaskQueue] 🚀 Executing task in {section_key}: {coro_func.__name__}")
                    await coro_func(*args, **kwargs)
                    print(f"[SectionTaskQueue] ✅ Task completed successfully in {section_key}: {coro_func.__name__}")
                except Exception as e:
                    print(f"[SectionTaskQueue] ❌ Task execution error in {section_key}: {e}")
                    import traceback
                    traceback.print_exc()
                finally:
                    queue.task_done()
                    print(f"[SectionTaskQueue] ✓ Task marked as done in {section_key}")
                    
            except asyncio.TimeoutError:
                # 队列空闲，退出worker
                print(f"[SectionTaskQueue] ⏰ Worker for {section_key} idle timeout (10s), exiting")
                break
            except Exception as e:
                print(f"[SectionTaskQueue] ❌ Worker error in {section_key}: {e}")
                import traceback
                traceback.print_exc()
                break
        
        # 清理worker引用
        if section_key in self._workers:
            del self._workers[section_key]
            print(f"[SectionTaskQueue] 🧹 Worker cleaned up for section: {section_key}")


# 全局单例
section_task_queue = SectionTaskQueue()



