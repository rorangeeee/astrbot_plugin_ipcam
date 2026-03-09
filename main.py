import cv2
import time
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

stream_url = "rtsp://192.168.1.4:8554/live"

def test_stream_connectivity(stream_url):
    cap = cv2.VideoCapture(stream_url)
    if not cap.isOpened():
        return False, "无法连接到视频流。请检查视频流地址和网络连接。"
    else:
        return True, None

def capture_img(stream_url):
    cap = cv2.VideoCapture(stream_url)
    ret, frame = cap.read()
    if ret:
        cv2.imwrite('snapshot.png', frame)
        return 'snapshot.png'
    else:
        raise Exception("无法从视频流中捕获图像。")

def capture_vid(stream_url, duration=10):
    cap = cv2.VideoCapture(stream_url)
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    size = (width, height)
    fps = cap.get(cv2.CAP_PROP_FPS)
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    writer = cv2.VideoWriter('output.avi', fourcc, fps, size)
    start_time = time.time()
    while (time.time() - start_time) < duration:
        ret, frame = cap.read()
        if ret:
            writer.write(frame)
        else:
            break
    writer.release()
    return 'output.avi'

@register("ipcam", "WhEN", "通过AstrBot实现IPCAM捕获功能", "1.0.0")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("cap_vid")
    async def cap_vid(self, event: AstrMessageEvent):
        """ if not(test_stream_connectivity(stream_url)):
            yield event.plain_result("IPCam 连通性测试未通过。")
        from astrbot.api.message_components import Video
        vid = capture_vid(stream_url)
        music = Video.fromFileSystem(
            path=vid
        )
        yield event.chain_result([music]) """
        yield event.plain_result("视频功能尚未开发")
        
        
    @filter.command("cap_img")
    async def cap_img(self, event: AstrMessageEvent):
        if not(test_stream_connectivity(stream_url)):
            yield event.plain_result("IPCam 连通性测试未通过。")
        img = capture_img(stream_url)
        yield event.image_result(img)
    
    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
