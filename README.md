# AstrBot IPCAM 插件
基于AstrBot方式实现对rtsp视频流的图像截取和视频捕获。

## 已实现
- ✅ 图像捕获
- ✅ 视频捕获
- ✅ 定时捕获

## 配置系统

### 配置选项说明

#### 基础配置
- **视频流地址 (stream_url)**: 输入你的网络摄像头 RTSP 地址
- **连接超时 (connection_timeout)**: 视频流连接超时时间（1-60秒）
- **读取超时 (read_timeout)**: 视频流读取超时时间（1-60秒）

#### 视频配置
- **录制时长 (video_duration)**: 录制视频的默认时长（1-300秒）
- **视频编码 (video_codec)**: 选择视频编码格式
  - MP4V (H.264) - 推荐，兼容性最好
  - AVC1 (H.264)
  - MJPEG - 兼容性最好
  - XVID

#### 图片配置
- **图片质量 (image_quality)**: JPEG 压缩质量（1-100）
- **图片宽度 (image_width)**: 调整图片宽度，0 表示保持原始尺寸

#### 高级选项
- **自动清理 (auto_cleanup)**: 发送后自动删除本地文件
- **启用日志 (enable_logging)**: 记录详细操作日志

## 命令使用

### 命令列表
- `/cap_img` - 捕获当前图像并发送
- `/cap_vid` - 录制视频（使用配置的默认时长）并发送
- `/schedulecap_img [间隔分钟]` - 开启定时图片捕获
- `/schedulecap_vid [间隔分钟] [视频时长秒]` - 开启定时视频录制
- `/schedulecap_off` - 取消定时捕获任务

### 使用示例
1. 确保已配置正确的 RTSP 视频流地址
2. 发送 `/cap_img` 获取当前画面
3. 发送 `/cap_vid` 录制并发送视频
4. 发送 `/schedulecap_img 5` 每5分钟自动捕获图片
5. 发送 `/schedulecap_vid 10 5` 每10分钟录制5秒视频
6. 发送 `/schedulecap_off` 取消定时任务

本意是用旧手机实现一个我家里小鹦鹉的监控。
