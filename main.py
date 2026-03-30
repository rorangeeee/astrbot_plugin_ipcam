import asyncio
import concurrent.futures
import cv2
import re
import time
import os
import uuid
from typing import Optional

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import AstrBotConfig
from astrbot.api import logger


def _mask_credentials_in_url(url: str) -> str:
    """遮蔽URL中的敏感凭据信息"""
    # 匹配 rtsp://user:pass@host 格式
    pattern = r'(://)([^:]+):([^@]+)(@)'
    masked = re.sub(pattern, r'\1\2:****\4', url)
    return masked


def _validate_stream_url(stream_url: str | None) -> tuple[bool, str]:
    """验证stream_url是否有效
    
    Returns:
        (is_valid, error_message)
    """
    if not stream_url:
        return False, "stream_url 未设置，请在插件配置中设置视频流地址"
    
    if not isinstance(stream_url, str):
        return False, "stream_url 必须是字符串类型"
    
    stream_url = stream_url.strip()
    if not stream_url:
        return False, "stream_url 不能为空"
    
    # 检查是否是支持的协议
    supported_protocols = ('rtsp://', 'http://', 'https://', 'rtmp://')
    if not any(stream_url.lower().startswith(proto) for proto in supported_protocols):
        return False, f"不支持的视频流协议，仅支持: {', '.join(supported_protocols)}"
    
    return True, ""


def test_stream_connectivity(stream_url: str, timeout: int = 5, read_timeout: int = 5) -> tuple[bool, str | None]:
    """测试视频流连通性，带超时功能"""
    cap = None
    try:
        cap = cv2.VideoCapture(stream_url)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout * 1000)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, read_timeout * 1000)
        
        if not cap.isOpened():
            return False, "无法连接到视频流，请检查视频流地址和网络连接"
        
        ret, frame = cap.read()
        if not ret or frame is None:
            return False, "视频流已连接但无法读取帧，请检查视频流格式"
        
        return True, None
        
    except cv2.error as e:
        return False, f"OpenCV 错误: {str(e)}"
    except Exception as e:
        return False, f"连接视频流时发生错误: {str(e)}"
    finally:
        if cap is not None:
            cap.release()


def _validate_video_params(width: int, height: int, fps: float) -> tuple[bool, str, int, int, float]:
    """验证视频参数合法性
    
    Returns:
        (is_valid, error_message, validated_width, validated_height, validated_fps)
    """
    # 检查宽度和高度
    if width <= 0 or height <= 0:
        return False, f"无效的视频分辨率: {width}x{height}，请检查视频流", 0, 0, 0.0
    
    # 校验 FPS
    validated_fps = fps
    if fps <= 0 or fps > 60:
        validated_fps = 25.0
        logger.warning(f"无法获取有效帧率，使用默认值: {validated_fps}")
    
    return True, "", width, height, validated_fps


def capture_img(stream_url: str, quality: int = 95, resize_width: int | None = None,
                timeout: int = 5, output_dir: str | None = None) -> str:
    """捕获图片，支持质量和尺寸调整
    
    Args:
        stream_url: 视频流地址
        quality: JPEG 压缩质量 (1-100)
        resize_width: 目标宽度，None 则保持原始尺寸
        timeout: 连接和读取超时（秒）
        output_dir: 输出目录，None 则使用临时目录
    
    Returns:
        保存的图片文件路径
    
    Raises:
        ValueError: 参数无效
        RuntimeError: 捕获失败
    """
    # 参数校验
    if not isinstance(quality, int) or not (1 <= quality <= 100):
        raise ValueError(f"无效的图片质量值: {quality}，应在 1-100 之间")
    
    if resize_width is not None:
        if not isinstance(resize_width, int) or resize_width <= 0:
            raise ValueError(f"无效的宽度值: {resize_width}")
    
    cap = None
    try:
        cap = cv2.VideoCapture(stream_url)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout * 1000)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout * 1000)
        
        if not cap.isOpened():
            raise RuntimeError("无法打开视频流，请检查视频流地址和网络连接")
        
        ret, frame = cap.read()
        if not ret or frame is None:
            raise RuntimeError("无法从视频流中读取帧，请检查视频流是否正在推流")
        
        # 尺寸调整
        if resize_width is not None and resize_width > 0:
            original_height, original_width = frame.shape[:2]
            ratio = resize_width / original_width
            new_height = int(original_height * ratio)
            frame = cv2.resize(frame, (resize_width, new_height))
        
        # 生成唯一文件名
        filename = f"snapshot_{uuid.uuid4().hex[:8]}.jpg"
        
        # 确定输出路径
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            filepath = os.path.join(output_dir, filename)
        else:
            filepath = filename
        
        # 写入文件
        success = cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not success:
            raise RuntimeError("JPEG 编码失败")
        
        if not os.path.exists(filepath):
            raise RuntimeError(f"图片文件未能正确生成: {filepath}")
        
        return filepath
        
    except cv2.error as e:
        raise RuntimeError(f"OpenCV 操作失败: {str(e)}")
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"捕获图像时发生未知错误: {str(e)}")
    finally:
        if cap is not None:
            cap.release()


def capture_vid(stream_url: str, duration: int = 10, codec: str = 'mp4v',
                timeout: int = 5, output_dir: str | None = None) -> str:
    """捕获视频，支持不同编码格式
    
    Args:
        stream_url: 视频流地址
        duration: 录制时长（秒）
        codec: 编码格式 ('mp4v', 'avc1', 'XVID', 'MJPG')
        timeout: 连接和读取超时（秒）
        output_dir: 输出目录，None 则使用临时目录
    
    Returns:
        保存的视频文件路径
    
    Raises:
        ValueError: 参数无效
        RuntimeError: 录制失败
    """
    # 参数校验
    if not isinstance(duration, int) or duration <= 0:
        raise ValueError(f"无效的录制时长: {duration}，应大于 0")
    if duration > 600:
        raise ValueError(f"录制时长过长: {duration} 秒，最大支持 600 秒")
    
    valid_codecs = ('mp4v', 'avc1', 'XVID', 'MJPG')
    if codec not in valid_codecs:
        raise ValueError(f"不支持的视频编码: {codec}，支持的格式: {', '.join(valid_codecs)}")
    
    cap = None
    writer = None
    output_file = None
    
    try:
        cap = cv2.VideoCapture(stream_url)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout * 1000)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout * 1000)
        
        if not cap.isOpened():
            raise RuntimeError("无法打开视频流，请检查视频流地址和网络连接")
        
        # 获取视频参数
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        
        # 验证视频参数
        is_valid, error_msg, width, height, fps = _validate_video_params(width, height, fps)
        if not is_valid:
            raise RuntimeError(error_msg)
        
        # 生成唯一文件名
        filename = f"video_{uuid.uuid4().hex[:8]}.mp4"
        
        # 确定输出路径
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, filename)
        else:
            output_file = filename
        
        # 选择编码器
        fourcc_dict = {
            'mp4v': cv2.VideoWriter_fourcc(*'mp4v'),
            'avc1': cv2.VideoWriter_fourcc(*'avc1'),
            'XVID': cv2.VideoWriter_fourcc(*'XVID'),
            'MJPG': cv2.VideoWriter_fourcc(*'MJPG')
        }
        fourcc = fourcc_dict.get(codec, cv2.VideoWriter_fourcc(*'mp4v'))
        
        # 创建 VideoWriter
        writer = cv2.VideoWriter(output_file, fourcc, fps, (width, height))
        
        if not writer.isOpened():
            logger.warning(f"编码器 {codec} 初始化失败，尝试使用 MJPG...")
            fourcc = cv2.VideoWriter_fourcc(*'MJPG')
            writer = cv2.VideoWriter(output_file, fourcc, fps, (width, height))
            
            if not writer.isOpened():
                raise RuntimeError("无法初始化视频编码器，请检查 OpenCV 是否支持该编码格式")
        
        # 录制视频
        start_time = time.time()
        frame_count = 0
        read_error_count = 0
        max_read_errors = 3  # 最多允许连续读取错误次数
        
        while (time.time() - start_time) < duration:
            ret, frame = cap.read()
            
            if not ret:
                read_error_count += 1
                if read_error_count >= max_read_errors:
                    logger.warning(f"视频流连续读取失败 {max_read_errors} 次，停止录制")
                    break
                # 短暂等待后重试
                time.sleep(0.1)
                continue
            
            read_error_count = 0  # 重置错误计数
            writer.write(frame)
            frame_count += 1
        
        # 确保数据写入
        writer.release()
        writer = None
        
        # 验证文件
        if not os.path.exists(output_file):
            raise RuntimeError("视频文件未能正确生成")
        
        file_size = os.path.getsize(output_file)
        if file_size == 0:
            raise RuntimeError("生成的视频文件大小为 0")
        
        logger.info(f"视频录制完成: {os.path.basename(output_file)}, 帧数: {frame_count}, 大小: {file_size} bytes")
        return output_file
        
    except cv2.error as e:
        # 清理可能生成的不完整文件
        if output_file and os.path.exists(output_file):
            try:
                os.remove(output_file)
            except OSError:
                pass  # 忽略清理失败
        raise RuntimeError(f"OpenCV 操作失败: {str(e)}")
    except RuntimeError:
        # 清理可能生成的不完整文件
        if output_file and os.path.exists(output_file):
            try:
                os.remove(output_file)
            except OSError:
                pass
        raise
    except Exception as e:
        # 清理可能生成的不完整文件
        if output_file and os.path.exists(output_file):
            try:
                os.remove(output_file)
            except OSError:
                pass
        raise RuntimeError(f"录制视频时发生未知错误: {str(e)}")
    finally:
        if cap is not None:
            cap.release()
        if writer is not None and writer.isOpened():
            writer.release()


def _get_data_dir(context: Context) -> str:
    """获取插件数据存储目录"""
    # 优先使用官方数据目录
    try:
        data_dir = context.get_data_dir()
        plugin_dir = os.path.join(data_dir, "ipcam")
        os.makedirs(plugin_dir, exist_ok=True)
        return plugin_dir
    except Exception:
        # 降级：使用系统临时目录
        import tempfile
        temp_dir = os.path.join(tempfile.gettempdir(), "astrbot_ipcam")
        os.makedirs(temp_dir, exist_ok=True)
        return temp_dir


@register("ipcam", "WhEN", "通过AstrBot实现IPCAM捕获功能", "1.0.0")
class MyPlugin(Star):
    
    def __init__(self, context: Context, config: AstrBotConfig):
        """初始化插件
        
        Args:
            context: AstrBot 上下文
            config: 插件配置（AstrBot 根据 _conf_schema.json 自动传入）
        """
        super().__init__(context)
        self.config = config
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=3, thread_name_prefix="ipcam_")
        
        # 定时任务相关
        self._schedule_task: Optional[asyncio.Task] = None
        self._schedule_running = False
        self._schedule_capture_type: str = "img"  # "img" 或 "vid"
        self._schedule_video_duration: int = 10  # 定时视频录制时的时长
        self._schedule_target_id: str = ""  # 定时任务的目标ID（群聊或私聊）
        self._schedule_is_group: bool = True  # 是否是群聊
        
        logger.info("IPCAM 插件已加载")
        
        # 验证配置并记录（不泄露敏感信息）
        stream_url = config.get("stream_url", "")
        if stream_url:
            masked_url = _mask_credentials_in_url(stream_url)
            logger.info(f"视频流地址: {masked_url}")
        else:
            logger.warning("视频流地址未设置，请在插件配置中进行配置")
    
    @filter.command("cap_vid")
    async def cap_vid(self, event: AstrMessageEvent):
        """录制视频命令"""
        stream_url = self.config.get("stream_url")
        
        # [高] 必填校验
        is_valid, error_msg = _validate_stream_url(stream_url)
        if not is_valid:
            yield event.plain_result(f"❌ 配置错误: {error_msg}")
            return
        
        video_duration = self.config.get("video_duration", 10)
        video_codec = self.config.get("video_codec", "mp4v")
        connection_timeout = self.config.get("connection_timeout", 5)
        read_timeout = self.config.get("read_timeout", 5)
        auto_cleanup = self.config.get("auto_cleanup", True)
        enable_logging = self.config.get("enable_logging", True)
        
        if enable_logging:
            logger.info(f"开始录制视频: 时长={video_duration}秒, 编码={video_codec}")
        
        loop = asyncio.get_event_loop()
        data_dir = await loop.run_in_executor(self._executor, _get_data_dir, self.context)
        
        try:
            yield event.plain_result(f"正在连接视频流并录制（{video_duration}秒）...")
            
            if enable_logging:
                logger.info("开始录制视频...")
            
            # [高] 在线程池中执行阻塞式 I/O 操作，避免阻塞事件循环
            vid = await loop.run_in_executor(
                self._executor,
                capture_vid,
                stream_url,
                video_duration,
                video_codec,
                connection_timeout,
                data_dir
            )
            
            # 发送视频
            from astrbot.api.message_components import Video
            video_msg = Video.fromFileSystem(path=vid)
            yield event.chain_result([video_msg])
            
            if enable_logging:
                logger.info(f"视频发送成功: {os.path.basename(vid)}")
            
        except ValueError as e:
            logger.error(f"参数错误: {str(e)}")
            yield event.plain_result(f"❌ 配置错误: {str(e)}")
            
        except RuntimeError as e:
            logger.error(f"录制视频失败: {str(e)}")
            yield event.plain_result(f"❌ 录制视频失败: {str(e)}")
            
        except Exception as e:
            logger.error(f"录制视频时发生未知错误: {type(e).__name__}: {str(e)}")
            yield event.plain_result(f"❌ 录制视频失败: {str(e)}")
            
        finally:
            # [中] 文件清理
            if auto_cleanup and 'vid' in dir() and vid and os.path.exists(vid):
                try:
                    os.remove(vid)
                    if enable_logging:
                        logger.info(f"本地视频文件已清理: {os.path.basename(vid)}")
                except OSError as e:
                    logger.warning(f"清理本地视频文件失败: {e}")
    
    @filter.command("cap_img")
    async def cap_img(self, event: AstrMessageEvent):
        """捕获图片命令"""
        stream_url = self.config.get("stream_url")
        
        # [高] 必填校验
        is_valid, error_msg = _validate_stream_url(stream_url)
        if not is_valid:
            yield event.plain_result(f"❌ 配置错误: {error_msg}")
            return
        
        image_quality = self.config.get("image_quality", 90)
        image_width = self.config.get("image_width", 0)
        connection_timeout = self.config.get("connection_timeout", 5)
        read_timeout = self.config.get("read_timeout", 5)
        auto_cleanup = self.config.get("auto_cleanup", True)
        enable_logging = self.config.get("enable_logging", True)
        
        if enable_logging:
            logger.info(f"开始捕获图片: 质量={image_quality}, 宽度={image_width}")
        
        loop = asyncio.get_event_loop()
        data_dir = await loop.run_in_executor(self._executor, _get_data_dir, self.context)
        
        try:
            yield event.plain_result("正在连接视频流并捕获图像...")
            
            if enable_logging:
                logger.info("开始捕获图像...")
            
            # [高] 在线程池中执行阻塞式 I/O 操作，避免阻塞事件循环
            img = await loop.run_in_executor(
                self._executor,
                capture_img,
                stream_url,
                image_quality,
                image_width if image_width > 0 else None,
                connection_timeout,
                data_dir
            )
            
            yield event.image_result(img)
            
            if enable_logging:
                logger.info(f"图像发送成功: {os.path.basename(img)}")
                
        except ValueError as e:
            logger.error(f"参数错误: {str(e)}")
            yield event.plain_result(f"❌ 配置错误: {str(e)}")
            
        except RuntimeError as e:
            logger.error(f"捕获图像失败: {str(e)}")
            yield event.plain_result(f"❌ 捕获图像失败: {str(e)}")
            
        except Exception as e:
            logger.error(f"捕获图像时发生未知错误: {type(e).__name__}: {str(e)}")
            yield event.plain_result(f"❌ 捕获图像失败: {str(e)}")
            
        finally:
            # [中] 文件清理
            if auto_cleanup and 'img' in dir() and img and os.path.exists(img):
                try:
                    os.remove(img)
                    if enable_logging:
                        logger.info(f"本地图片文件已清理: {os.path.basename(img)}")
                except OSError as e:
                    logger.warning(f"清理本地图片文件失败: {e}")
    
    @filter.command("schedulecap_img")
    async def schedulecap_img(self, event: AstrMessageEvent, interval: int | None = None):
        """开启定时图片捕获命令"""
        # 参数校验
        interval_minutes = interval if interval is not None else 60
        if interval_minutes <= 0:
            yield event.plain_result("❌ 间隔时间必须大于0")
            return
        
        # 停止已有的定时任务
        await self._stop_schedule_task()
        
        # 获取目标session
        self._schedule_target_id = event.unified_msg_origin
        self._schedule_is_group = event.get_group_id() is not None
        
        # 启动新的定时任务
        self._schedule_capture_type = "img"
        self._schedule_video_duration = self.config.get("video_duration", 10)
        
        yield event.plain_result(f"⏰ 已开启定时图片捕获，间隔 {interval_minutes} 分钟")
        
        await self._start_schedule_task("img", interval_minutes, 0)
    
    @filter.command("schedulecap_vid")
    async def schedulecap_vid(self, event: AstrMessageEvent, interval: int | None = None, duration: int | None = None):
        """开启定时视频录制命令"""
        interval_minutes = interval if interval is not None else 60
        video_duration = duration if duration is not None else self.config.get("video_duration", 10)
        
        if interval_minutes <= 0:
            yield event.plain_result("❌ 间隔时间必须大于0")
            return
        if video_duration <= 0 or video_duration > 600:
            yield event.plain_result("❌ 视频时长必须在1-600秒之间")
            return
        
        # 停止已有的定时任务
        await self._stop_schedule_task()
        
        # 获取目标session
        self._schedule_target_id = event.unified_msg_origin
        self._schedule_is_group = event.get_group_id() is not None
        
        # 启动新的定时任务
        self._schedule_capture_type = "vid"
        self._schedule_video_duration = video_duration
        
        yield event.plain_result(f"⏰ 已开启定时视频录制，间隔 {interval_minutes} 分钟，时长 {video_duration} 秒")
        
        await self._start_schedule_task("vid", interval_minutes, 0)
    
    @filter.command("schedulecap_off")
    async def schedulecap_off(self, event: AstrMessageEvent):
        """取消定时捕获任务"""
        if not self._schedule_running:
            yield event.plain_result("❌ 当前没有正在运行的定时任务")
            return
        
        await self._stop_schedule_task()
        yield event.plain_result("✅ 定时捕获任务已取消")
    
    async def _start_schedule_task(self, capture_type: str, interval_minutes: int, initial_delay: int = 0):
        """启动定时任务
        
        Args:
            capture_type: 捕获类型 "img" 或 "vid"
            interval_minutes: 间隔时间（分钟）
            initial_delay: 初始延迟（秒），0 表示立即执行
        """
        if self._schedule_running:
            logger.warning("定时任务已在运行中")
            return
        
        self._schedule_running = True
        self._schedule_capture_type = capture_type
        
        async def schedule_loop():
            """定时任务循环"""
            while self._schedule_running:
                try:
                    # 初始延迟
                    if initial_delay > 0:
                        await asyncio.sleep(initial_delay)
                    else:
                        # 立即执行第一次
                        pass
                    
                    while self._schedule_running:
                        # 执行捕获
                        await self._execute_scheduled_capture()
                        
                        # 等待间隔
                        wait_seconds = interval_minutes * 60
                        logger.info(f"定时任务等待 {interval_minutes} 分钟后下次执行")
                        
                        # 分段等待，以便能及时响应停止信号
                        for _ in range(wait_seconds):
                            if not self._schedule_running:
                                break
                            await asyncio.sleep(1)
                
                except asyncio.CancelledError:
                    logger.info("定时任务被取消")
                    break
                except Exception as e:
                    logger.error(f"定时任务执行出错: {type(e).__name__}: {str(e)}")
                    # 出错后等待1分钟再重试
                    for _ in range(60):
                        if not self._schedule_running:
                            break
                        await asyncio.sleep(1)
        
        self._schedule_task = asyncio.create_task(schedule_loop())
        logger.info(f"定时任务已启动: 类型={capture_type}, 间隔={interval_minutes}分钟")
    
    async def _stop_schedule_task(self):
        """停止定时任务"""
        if not self._schedule_running and self._schedule_task is None:
            return
        
        self._schedule_running = False
        
        if self._schedule_task:
            self._schedule_task.cancel()
            try:
                await self._schedule_task
            except asyncio.CancelledError:
                pass
            self._schedule_task = None
        
        logger.info("定时任务已停止")
    
    async def _execute_scheduled_capture(self):
        """执行定时捕获"""
        stream_url = self.config.get("stream_url")
        
        # 验证 stream_url
        is_valid, error_msg = _validate_stream_url(stream_url)
        if not is_valid:
            logger.error(f"定时捕获失败: {error_msg}")
            return
        
        enable_logging = self.config.get("enable_logging", True)
        auto_cleanup = self.config.get("auto_cleanup", True)
        
        loop = asyncio.get_event_loop()
        data_dir = await loop.run_in_executor(self._executor, _get_data_dir, self.context)
        
        try:
            if self._schedule_capture_type == "img":
                # 捕获图片
                image_quality = self.config.get("image_quality", 90)
                image_width = self.config.get("image_width", 0)
                connection_timeout = self.config.get("connection_timeout", 5)
                
                if enable_logging:
                    logger.info("定时任务: 开始捕获图片...")
                
                img = await loop.run_in_executor(
                    self._executor,
                    capture_img,
                    stream_url,
                    image_quality,
                    image_width if image_width > 0 else None,
                    connection_timeout,
                    data_dir
                )
                
                # 发送图片到目标
                await self._send_image_to_target(img)
                
                if enable_logging:
                    logger.info(f"定时任务: 图片发送成功")
                
                # 清理
                if auto_cleanup and os.path.exists(img):
                    try:
                        os.remove(img)
                    except OSError as e:
                        logger.warning(f"清理本地图片文件失败: {e}")
                
            else:  # "vid"
                # 录制视频
                video_duration = self._schedule_video_duration
                video_codec = self.config.get("video_codec", "mp4v")
                connection_timeout = self.config.get("connection_timeout", 5)
                
                if enable_logging:
                    logger.info(f"定时任务: 开始录制视频({video_duration}秒)...")
                
                vid = await loop.run_in_executor(
                    self._executor,
                    capture_vid,
                    stream_url,
                    video_duration,
                    video_codec,
                    connection_timeout,
                    data_dir
                )
                
                # 发送视频到目标
                await self._send_video_to_target(vid)
                
                if enable_logging:
                    logger.info(f"定时任务: 视频发送成功")
                
                # 清理
                if auto_cleanup and os.path.exists(vid):
                    try:
                        os.remove(vid)
                    except OSError as e:
                        logger.warning(f"清理本地视频文件失败: {e}")
        
        except Exception as e:
            logger.error(f"定时捕获执行失败: {type(e).__name__}: {str(e)}")
    
    async def _send_image_to_target(self, img_path: str):
        """发送图片到定时任务的目标"""
        try:
            from astrbot.api.message_components import Image
            from astrbot.core.message.message_event_result import MessageChain
            image_msg = Image.fromFileSystem(path=img_path)
            chain = MessageChain([image_msg])
            await self.context.send_message(self._schedule_target_id, chain)
            logger.info(f"定时任务: 图片已发送到 {self._schedule_target_id}")
        except Exception as e:
            logger.error(f"定时任务: 发送图片失败: {e}")
    
    async def _send_video_to_target(self, vid_path: str):
        """发送视频到定时任务的目标"""
        try:
            from astrbot.api.message_components import Video
            from astrbot.core.message.message_event_result import MessageChain
            video_msg = Video.fromFileSystem(path=vid_path)
            chain = MessageChain([video_msg])
            await self.context.send_message(self._schedule_target_id, chain)
            logger.info(f"定时任务: 视频已发送到 {self._schedule_target_id}")
        except Exception as e:
            logger.error(f"定时任务: 发送视频失败: {e}")
    
    async def terminate(self):
        """插件销毁时调用"""
        # 停止定时任务
        await self._stop_schedule_task()
        
        # 关闭线程池
        self._executor.shutdown(wait=False)
        logger.info("IPCAM 插件已卸载")
