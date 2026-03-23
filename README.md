# AstrBot IPCAM 插件
基于AstrBot方式实现对rtsp视频流的图像截取和视频捕获。

## 已实现
- ✅ 图像捕获（支持质量和尺寸调整）
- ✅ 视频捕获（支持多种编码格式）
- ✅ 视频流连通性测试
- ✅ 超时处理和错误处理
- ✅ 自动清理本地文件
- ✅ **AstrBot 原生配置系统**
- ✅ **自定义 WebUI 配置页面**

## 配置系统

插件使用 AstrBot 原生配置系统，通过 `_conf_schema.json` 定义配置架构。

### 配置文件

插件会生成 `data/config/ipcam_config.json` 配置文件，包含所有可配置参数：

```json
{
    "stream_url": "rtsp://192.168.1.4:8554/live",
    "connection_timeout": 5,
    "read_timeout": 5,
    "video_duration": 10,
    "video_codec": "mp4v",
    "image_quality": 90,
    "image_width": 0,
    "auto_cleanup": true,
    "enable_logging": true
}
```

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

### 使用示例
1. 确保已配置正确的 RTSP 视频流地址
2. 发送 `/cap_img` 获取当前画面
3. 发送 `/cap_vid` 录制并发送视频

## 配置管理

### 在 WebUI 中配置（推荐）
1. 在 AstrBot 管理面板中，找到 IPCAM 插件
2. 点击"配置"按钮
3. 修改各项配置参数
4. 点击保存

### 手动配置
1. 找到 AstrBot 数据目录下的 `data/config/ipcam_config.json`
2. 直接编辑配置文件
3. 重启插件或 AstrBot 使配置生效

## 技术特点

### 视频捕获
- 使用 mp4v (H.264) 编码替代 XVID
- 编码器自动回退机制（mp4v → MJPG）
- 超时处理和错误处理
- 文件生成验证
- 资源正确释放

### 图像捕获
- 支持 JPEG 质量调整
- 支持图片尺寸调整
- 使用唯一文件名避免冲突
- 自动资源释放

### 配置系统
- AstrBot 原生配置架构（`_conf_schema.json`）
- 配置自动验证和持久化
- 支持在线修改和保存

## 安装说明

1. 将插件文件夹复制到 AstrBot 插件目录
2. 重启 AstrBot
3. 在管理面板中配置视频流地址
4. 开始使用！

## 注意事项

- 确保 RTSP 视频流可访问
- 录制视频会占用临时存储空间
- 建议启用自动清理功能
- MP4V 编码兼容性最好

## 项目结构

```
astrbot_plugin_ipcam/
├── main.py              # 插件主代码
├── _conf_schema.json    # 配置架构定义
├── metadata.yaml        # 插件元数据
├── README.md            # 项目说明
└── LICENSE              # 许可证
```

本意是用旧手机实现一个我家里小鹦鹉的监控。
