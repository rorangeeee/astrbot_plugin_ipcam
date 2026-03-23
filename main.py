import cv2
import time
import os
import uuid
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import AstrBotConfig
from astrbot.api import logger


def test_stream_connectivity(stream_url, timeout=5):
    """测试视频流连通性，带超时功能"""
    cap = None
    try:
        cap = cv2.VideoCapture(stream_url)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout * 1000)  # 设置连接超时
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout * 1000)   # 设置读取超时
        
        if not cap.isOpened():
            return False, "无法连接到视频流。请检查视频流地址和网络连接。"
        
        # 尝试读取一帧来验证流是否真正可用
        ret, frame = cap.read()
        if not ret or frame is None:
            return False, "视频流已连接但无法读取帧，请检查视频流格式。"
        
        return True, None
    except Exception as e:
        return False, f"连接视频流时发生错误: {str(e)}"
    finally:
        if cap is not None:
            cap.release()


def capture_img(stream_url, quality=95, resize_width=None):
    """捕获图片，支持质量和尺寸调整"""
    cap = None
    try:
        cap = cv2.VideoCapture(stream_url)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
        
        ret, frame = cap.read()
        if not ret or frame is None:
            raise Exception("无法从视频流中捕获图像。")
        
        # 如果指定了宽度，等比例调整尺寸
        if resize_width is not None:
            ratio = resize_width / frame.shape[1]
            new_height = int(frame.shape[0] * ratio)
            frame = cv2.resize(frame, (resize_width, new_height))
        
        # 生成唯一文件名避免冲突
        filename = f"snapshot_{uuid.uuid4().hex[:8]}.jpg"
        # 使用 JPEG 编码，质量可调
        cv2.imwrite(filename, frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return filename
    except Exception as e:
        raise Exception(f"捕获图像失败: {str(e)}")
    finally:
        if cap is not None:
            cap.release()


def capture_vid(stream_url, duration=10, codec='mp4v'):
    """捕获视频，支持不同编码格式
    
    Args:
        stream_url: 视频流地址
        duration: 录制时长（秒）
        codec: 编码格式 ('mp4v', 'avc1', 'XVID', 'MJPG')
    
    Returns:
        保存的视频文件路径
    """
    cap = None
    writer = None
    output_file = None
    
    try:
        cap = cv2.VideoCapture(stream_url)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
        
        if not cap.isOpened():
            raise Exception("无法打开视频流")
        
        # 获取视频参数
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        
        # 如果 FPS 无效，设置为默认值
        if fps <= 0 or fps > 60:
            fps = 25.0
            logger.warning(f"无法获取有效帧率，使用默认值: {fps}")
        
        # 生成唯一文件名
        output_file = f"video_{uuid.uuid4().hex[:8]}.mp4"
        
        # 选择编码器
        fourcc_dict = {
            'mp4v': cv2.VideoWriter_fourcc(*'mp4v'),  # H.264/AVC1 (推荐)
            'avc1': cv2.VideoWriter_fourcc(*'avc1'),
            'XVID': cv2.VideoWriter_fourcc(*'XVID'),
            'MJPG': cv2.VideoWriter_fourcc(*'MJPG')
        }
        
        fourcc = fourcc_dict.get(codec, cv2.VideoWriter_fourcc(*'mp4v'))
        
        # 创建 VideoWriter
        writer = cv2.VideoWriter(output_file, fourcc, fps, (width, height))
        
        if not writer.isOpened():
            # 如果 mp4v 失败，尝试其他编码器
            logger.warning(f"编码器 {codec} 初始化失败，尝试使用 MJPG...")
            fourcc = cv2.VideoWriter_fourcc(*'MJPG')
            writer = cv2.VideoWriter(output_file, fourcc, fps, (width, height))
            
            if not writer.isOpened():
                raise Exception("无法初始化视频编码器，请检查 OpenCV 是否支持该编码格式")
        
        # 录制视频
        start_time = time.time()
        frame_count = 0
        
        while (time.time() - start_time) < duration:
            ret, frame = cap.read()
            if not ret:
                logger.warning("视频流读取中断")
                break
            
            writer.write(frame)
            frame_count += 1
        
        # 确保写入器中的数据被刷新
        writer.release()
        writer = None
        
        # 验证文件是否生成
        if not os.path.exists(output_file):
            raise Exception("视频文件生成失败")
        
        file_size = os.path.getsize(output_file)
        if file_size == 0:
            raise Exception("生成的视频文件大小为0")
        
        logger.info(f"视频录制完成: {output_file}, 帧数: {frame_count}, 大小: {file_size} bytes")
        return output_file
        
    except Exception as e:
        # 清理可能生成的不完整文件
        if output_file and os.path.exists(output_file):
            try:
                os.remove(output_file)
            except:
                pass
        raise Exception(f"录制视频失败: {str(e)}")
        
    finally:
        # 确保资源正确释放
        if cap is not None:
            cap.release()
        if writer is not None and writer.isOpened():
            writer.release()


@register("ipcam", "WhEN", "通过AstrBot实现IPCAM捕获功能", "1.0.0")
class MyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        """初始化插件
        
        Args:
            context: AstrBot 上下文
            config: 插件配置（AstrBot 根据 _conf_schema.json 自动传入）
        """
        super().__init__(context)
        self.config = config  # 保存配置
        logger.info("IPCAM 插件已加载")
        logger.info(f"当前配置: stream_url={config.get('stream_url', '未设置')}")

    @filter.command("cap_vid")
    async def cap_vid(self, event: AstrMessageEvent):
        """录制视频命令"""
        stream_url = self.config.get("stream_url")
        video_duration = self.config.get("video_duration", 10)
        video_codec = self.config.get("video_codec", "mp4v")
        connection_timeout = self.config.get("connection_timeout", 5)
        auto_cleanup = self.config.get("auto_cleanup", True)
        enable_logging = self.config.get("enable_logging", True)
        
        if enable_logging:
            logger.info(f"开始录制视频: 时长={video_duration}秒, 编码={video_codec}")
        
        yield event.plain_result("正在测试视频流连通性...")
        
        # 测试连通性
        connected, error_msg = test_stream_connectivity(stream_url, timeout=connection_timeout)
        if not connected:
            yield event.plain_result(f"❌ IPCam 连通性测试未通过：{error_msg}")
            return
        
        yield event.plain_result(f"✅ 连通性测试通过，正在录制视频（{video_duration}秒）...")
        
        try:
            from astrbot.api.message_components import Video
            
            # 录制视频
            vid = capture_vid(stream_url, duration=video_duration, codec=video_codec)
            
            # 发送视频
            video_msg = Video.fromFileSystem(path=vid)
            yield event.chain_result([video_msg])
            
            if enable_logging:
                logger.info(f"视频发送成功: {vid}")
            
            # 可选：删除本地视频文件以节省空间
            if auto_cleanup:
                try:
                    os.remove(vid)
                    if enable_logging:
                        logger.info(f"本地视频文件已清理: {vid}")
                except Exception as e:
                    logger.warning(f"清理本地视频文件失败: {e}")
                
        except Exception as e:
            logger.error(f"录制视频时出错: {str(e)}")
            yield event.plain_result(f"❌ 录制视频失败：{str(e)}")
        
    @filter.command("cap_img")
    async def cap_img(self, event: AstrMessageEvent):
        """捕获图片命令"""
        stream_url = self.config.get("stream_url")
        image_quality = self.config.get("image_quality", 90)
        image_width = self.config.get("image_width", 0)
        connection_timeout = self.config.get("connection_timeout", 5)
        auto_cleanup = self.config.get("auto_cleanup", True)
        enable_logging = self.config.get("enable_logging", True)
        
        if enable_logging:
            logger.info(f"开始捕获图片: 质量={image_quality}, 宽度={image_width}")
        
        yield event.plain_result("正在测试视频流连通性...")
        
        connected, error_msg = test_stream_connectivity(stream_url, timeout=connection_timeout)
        if not connected:
            yield event.plain_result(f"❌ IPCam 连通性测试未通过：{error_msg}")
            return
        
        yield event.plain_result("✅ 连通性测试通过，正在捕获图像...")
        
        try:
            img = capture_img(
                stream_url, 
                quality=image_quality, 
                resize_width=image_width if image_width > 0 else None
            )
            yield event.image_result(img)
            
            if enable_logging:
                logger.info(f"图像发送成功: {img}")
            
            # 可选：删除本地图片文件
            if auto_cleanup:
                try:
                    os.remove(img)
                except Exception as e:
                    logger.warning(f"清理本地图片文件失败: {e}")
                
        except Exception as e:
            logger.error(f"捕获图像时出错: {str(e)}")
            yield event.plain_result(f"❌ 捕获图像失败：{str(e)}")
    
    async def terminate(self):
        """插件销毁时调用"""
        logger.info("IPCAM 插件已卸载")
