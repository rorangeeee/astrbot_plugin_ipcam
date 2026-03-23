import cv2
import time
import os
import uuid
import json
from pathlib import Path
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

# 默认配置
DEFAULT_CONFIG = {
    "stream_url": "rtsp://192.168.1.4:8554/live",
    "connection_timeout": 5,
    "read_timeout": 5,
    "video_duration": 10,
    "video_codec": "mp4v",
    "image_quality": 90,
    "image_width": 0,
    "auto_cleanup": True,
    "enable_logging": True
}

class PluginConfig:
    """插件配置管理类"""
    
    def __init__(self, config_file="ipcam_config.json"):
        self.config_file = Path(config_file)
        self.config = self.load_config()
    
    def load_config(self):
        """从文件加载配置"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # 合并默认配置，确保所有字段都存在
                    return {**DEFAULT_CONFIG, **config}
            else:
                # 如果配置文件不存在，创建默认配置
                self.save_config(DEFAULT_CONFIG)
                return DEFAULT_CONFIG.copy()
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return DEFAULT_CONFIG.copy()
    
    def save_config(self, config):
        """保存配置到文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")
            return False
    
    def get(self, key, default=None):
        """获取配置项"""
        return self.config.get(key, default)
    
    def update(self, new_config):
        """更新配置"""
        self.config.update(new_config)
        return self.save_config(self.config)

# 创建全局配置实例
plugin_config = PluginConfig()

# 获取当前配置
def get_stream_url():
    return plugin_config.get("stream_url", DEFAULT_CONFIG["stream_url"])

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
    def __init__(self, context: Context):
        super().__init__(context)
        logger.info("IPCAM 插件已加载")
        
        # 注册 WebUI 路由
        self.context.router.register_web_ui(
            route_path="/ipcam",
            page_name="ipcam_config",
            page_path="webui_config.html",
            default_title="IPCAM 配置"
        )

    @filter.command("cap_vid")
    async def cap_vid(self, event: AstrMessageEvent):
        """录制视频命令"""
        stream_url = plugin_config.get("stream_url")
        video_duration = plugin_config.get("video_duration", 10)
        video_codec = plugin_config.get("video_codec", "mp4v")
        
        yield event.plain_result("正在测试视频流连通性...")
        
        # 测试连通性
        connected, error_msg = test_stream_connectivity(stream_url)
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
            
            logger.info(f"视频发送成功: {vid}")
            
            # 可选：删除本地视频文件以节省空间
            if plugin_config.get("auto_cleanup", True):
                try:
                    os.remove(vid)
                    logger.info(f"本地视频文件已清理: {vid}")
                except Exception as e:
                    logger.warning(f"清理本地视频文件失败: {e}")
                
        except Exception as e:
            logger.error(f"录制视频时出错: {str(e)}")
            yield event.plain_result(f"❌ 录制视频失败：{str(e)}")
        
    @filter.command("cap_img")
    async def cap_img(self, event: AstrMessageEvent):
        """捕获图片命令"""
        stream_url = plugin_config.get("stream_url")
        image_quality = plugin_config.get("image_quality", 90)
        image_width = plugin_config.get("image_width", 0)
        
        yield event.plain_result("正在测试视频流连通性...")
        
        connected, error_msg = test_stream_connectivity(stream_url)
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
            
            logger.info(f"图像发送成功: {img}")
            
            # 可选：删除本地图片文件
            if plugin_config.get("auto_cleanup", True):
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
