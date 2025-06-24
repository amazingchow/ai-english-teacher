# AI 英语口语助手

一个基于 Google Gemini Live API 的实时英语口语练习助手，支持语音交互和发音评分。

## 功能特性

- 🎤 实时语音识别和对话
- 🤖 AI 英语教练 Echo 提供专业指导
- 📊 发音评分和详细反馈
- 🎵 音频文件播放功能
- 🎯 多种主题练习场景
- ⏸️ 会话暂停/继续控制

## 安装依赖

```bash
# 安装系统依赖
brew install portaudio
brew install espeak-ng

# 安装 Python 依赖
uv sync
```

## 环境配置

确保设置 `GOOGLE_API_KEY` 环境变量：

```bash
export GOOGLE_API_KEY="your_google_api_key_here"
```

## 使用方法

### 启动主程序

```bash
python app.py
```

### 测试音频文件播放

```bash
python test_audio_playback.py
```

## 音频文件播放功能

新增的音频文件播放功能支持：

### 方法说明

1. **`read_audio_file(file_path: str) -> bytes`**
   - 读取 WAV 格式音频文件
   - 返回音频数据字节流
   - 自动检查音频格式兼容性

2. **`play_audio_file(file_path: str)`**
   - 异步播放音频文件
   - 非阻塞，适合在异步环境中使用

3. **`play_audio_file_sync(file_path: str)`**
   - 同步播放音频文件
   - 阻塞版本，播放完成后才继续

### 使用示例

```python
# 在 AudioLoop 实例中使用
loop = AudioLoop()

# 异步播放
await loop.play_audio_file("path/to/audio.wav")

# 同步播放
await loop.play_audio_file_sync("path/to/audio.wav")
```

### 支持的音频格式

- **格式**: WAV
- **采样率**: 24000 Hz (推荐)
- **通道数**: 1 (单声道)
- **位深度**: 16-bit

## 控制命令

- `"Can I have a break"` - 暂停会话
- `"OK let's continue"` - 继续会话

## 主题场景

- **Business**: 商务面试、会议、演讲、社交
- **Travel**: 机场、酒店、餐厅、观光
- **Daily Life**: 购物、天气、爱好、家庭
- **Social**: 朋友聚会、派对、社交媒体、约会

## 作者

Adam Zhou - X@summychou

## 许可证

MIT License
