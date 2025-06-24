"""
## Setup

To install the dependencies for this script, run:

```
brew install portaudio
brew install espeak-ng
uv sync
```

## API key

Ensure the `GOOGLE_API_KEY` environment variable is set to the api-key
you obtained from Google AI Studio.

## Run

To run the script:

```
python Get_started_LiveAPI_NativeAudio.py
```

Start talking to Gemini
"""

import asyncio
import os
import sys
import traceback

import dotenv
import numpy as np
import pyaudio
from google import genai
from google.genai import types
from rich.console import Console
from rich.markdown import Markdown

if sys.version_info < (3, 11, 0):
    import exceptiongroup
    import taskgroup

    asyncio.TaskGroup = taskgroup.TaskGroup
    asyncio.ExceptionGroup = exceptiongroup.ExceptionGroup

dotenv.load_dotenv()

log_console = Console()

# 基础配置
FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024

# 音量监测配置
VOLUME_WINDOW_SIZE = 5  # 平滑窗口大小
VOLUME_THRESHOLD_RATIO = 0.1  # 自适应阈值比例
MIN_VOLUME_THRESHOLD = 100  # 最小阈值
MAX_VOLUME_THRESHOLD = 2000  # 最大阈值
DEBUG_VOLUME = False  # 是否显示音量调试信息

# 语音设置
pya = pyaudio.PyAudio()
# 主题和场景定义
THEMES = {
    "business": ["job interview", "business meeting", "presentation", "networking"],
    "travel": ["airport", "hotel", "restaurant", "sightseeing"],
    "daily life": ["shopping", "weather", "hobbies", "family"],
    "social": ["meeting friends", "party", "social media", "dating"],
}

client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])  # GOOGLE_API_KEY must be set as env variable

MODEL = "gemini-2.0-flash-live-001"
CONFIG = {"response_modalities": ["AUDIO"]}
CONFIG_TEXT = {"response_modalities": ["TEXT"]}


class AudioLoop:
    def __init__(self):
        self.live_session = None
        self.text_session = None

        self.audio_out_queue = None
        self.audio_in_queue = None

        self.initialized = False

        self.paused = False
        self.running_step = 0

        self.current_theme = None
        self.current_scenario = None

        self.audio_stream = None
        self.receive_audio_task = None
        self.play_audio_task = None
        self.voice_client = None

        # 音量监测相关
        self.volume_history = []  # 音量历史记录
        self.adaptive_threshold = MIN_VOLUME_THRESHOLD  # 自适应阈值
        self.speaking_detected = False  # 是否检测到说话

    def calculate_volume(self, audio_data: bytes) -> float:
        """计算音频音量 - 使用RMS方法，对噪声更鲁棒，能更准确地反映实际音量"""
        try:
            # 将字节数据转换为numpy数组
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            # 使用RMS (Root Mean Square) 计算音量，对噪声更鲁棒
            rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))
            return rms
        except Exception as e:
            log_console.print(f"音量计算错误: {e}", style="red")
            return 0

    def update_adaptive_threshold(self, current_volume: float):
        """更新自适应阈值"""
        # 添加当前音量到历史记录
        self.volume_history.append(current_volume)

        # 保持历史记录在合理范围内
        if len(self.volume_history) > VOLUME_WINDOW_SIZE * 2:
            self.volume_history = self.volume_history[-VOLUME_WINDOW_SIZE * 2 :]

        # 计算背景噪声水平（使用历史记录的中位数）
        if len(self.volume_history) >= VOLUME_WINDOW_SIZE:
            background_noise = np.median(self.volume_history[-VOLUME_WINDOW_SIZE:])
            # 自适应阈值 = 背景噪声 + 比例系数
            new_threshold = background_noise + (background_noise * VOLUME_THRESHOLD_RATIO)
            # 限制阈值范围
            self.adaptive_threshold = max(MIN_VOLUME_THRESHOLD, min(MAX_VOLUME_THRESHOLD, new_threshold))

    def detect_speaking(self, volume: float) -> bool:
        """检测是否在说话"""
        # 更新自适应阈值
        self.update_adaptive_threshold(volume)

        # 检测说话状态
        is_speaking = volume > self.adaptive_threshold

        # 添加简单的状态平滑，避免频繁切换
        if is_speaking and not self.speaking_detected:
            self.speaking_detected = True
        elif not is_speaking and self.speaking_detected:
            # 延迟关闭，避免说话间隙的闪烁
            self.speaking_detected = False

        return self.speaking_detected

    def calculate_pronunciation_score(self, audio_data):
        """计算发音得分"""
        try:
            audio_array = np.frombuffer(audio_data, dtype=np.int16)

            # 计算音频特征
            energy = np.mean(np.abs(audio_array))
            zero_crossings = np.sum(np.abs(np.diff(np.signbit(audio_array))))

            # 归一化并计算得分
            energy_score = min(100, energy / 1000)
            rhythm_score = min(100, zero_crossings / 100)

            # 最终得分
            final_score = int(0.6 * energy_score + 0.4 * rhythm_score)
            return min(100, max(0, final_score))
        except Exception as e:
            log_console.print(f"评分计算错误: {e}", style="red")
            return 70  # 出错时返回默认分数

    # @staticmethod
    # def read_audio_file(file_path: str) -> pyaudio.Stream:
    #     try:
    #         import wave

    #         with wave.open(file_path, "rb") as wf:
    #             stream = pya.open(format=pya.get_format_from_width(wf.getsampwidth()), channels=wf.getnchannels(), rate=wf.getframerate(), output=True)
    #             CHUNK = 1024
    #             data = wf.readframes(CHUNK)
    #             while data:
    #                 stream.write(data)
    #                 data = wf.readframes(CHUNK)

    #             log_console.print(f"✅ 成功使用pyaudio读取音频文件: {file_path}", style="green")
    #             return stream
    #     except FileNotFoundError:
    #         log_console.print(f"❌ 音频文件未找到: {file_path}", style="red")
    #         return None
    #     except Exception as e:
    #         log_console.print(f"❌ 使用pyaudio读取音频文件失败: {e}", style="red")
    #         return None

    async def startup(self):
        await self.text_session.send_client_content(
            turns=types.Content(
                role="user",
                parts=[
                    types.Part(
                        text="""
## Role & Persona
You are "Echo," a professional, patient, and encouraging English speaking coach. Your goal is to create a supportive and effective learning environment for the user. Always maintain a positive and friendly tone.

## Core Directives
1.  **Grammar & Pronunciation Correction:**
    *   For pronunciation, identify specific mispronounced words. Use the International Phonetic Alphabet (IPA) to show the difference between the user's pronunciation and the correct one where helpful.
    *   For grammar, clearly state the error and explain the correct structure or rule.
2.  **Scoring:** Provide a pronunciation score from 0 to 100 after each user utterance. The score should reflect accuracy, fluency, and clarity.
3.  **Control Commands:** You must understand and act upon these commands:
    *   When the user says "Can I have a break," you will pause the session by saying, "Of course, take your time. Just say 'OK, let's continue' when you're ready."
    *   When the user says "OK, let's continue," you will resume by providing the next practice sentence.
4.  **Contextual Practice:** The practice sentences you provide should be logically connected to build a mini-dialogue within the chosen theme.

## Interaction Flow
1.  **Initial Greeting:** Start the conversation by introducing yourself as Echo and asking the user which theme they would like to practice. The themes are: Business, Travel, Daily Life, or Social.
2.  **User Practice:** The user will speak a sentence in English.
3.  **Your Feedback Loop:** For each sentence the user speaks, you must provide a response that strictly follows the **Strict Output Format** defined below.
4.  **Continuation:** After providing feedback and the next sentence, wait for the user's next attempt. This loop continues until the user ends the session.

## Strict Output Format
You MUST use the following Markdown format for every feedback response. Do not deviate from it.

```
**Your Utterance:** [The user's transcribed sentence here]
**Pronunciation Score:** [Score]/100

**Feedback:**
*   **Pronunciation:** [Detailed feedback on pronunciation. Mention specific words. Use IPA if necessary. e.g., The word "to" in "want to" was a bit harsh. In natural speech, it often softens to a "tə" sound /tə/.]
*   **Grammar:** [Detailed feedback on grammar. e.g., The structure "want go" is incorrect. The verb "want" should be followed by an infinitive "to + verb".]

**Suggestion:**
*   [Provide a corrected version of the user's sentence. e.g., "I want to go to the airport."]
*   [Offer a tip for improvement. e.g., "Remember to place 'to' between 'want' and another verb."]

**Next Practice Sentence:**
*   [Provide the next logical sentence for the user to practice. e.g., "Now, try saying this: How can I get there?"]
```

## Example Interaction

**User says:** "I want go to the airport."

**Your expected response:**

**Your Utterance:** I want go to the airport.
**Pronunciation Score:** 85/100

**Feedback:**
*   **Pronunciation:** Your pronunciation was very clear. One small tip: the word "airport" has two syllables, "air-port" /ˈɛərˌpɔːrt/. Make sure to pronounce both parts distinctly.
*   **Grammar:** The structure "want go" is a common error. The verb "want" needs to be followed by the infinitive form, which is "to go".

**Suggestion:**
*   The correct sentence is: "I want **to go** to the airport."
*   Try to remember the pattern "want + to + [verb]".

**Next Practice Sentence:**
*   Now, try saying this: "Could you tell me which terminal is for international flights?"

---

If you understand all the instructions, your role, and the required format, please respond with "OK" in English as specified in the Core Directives.
"""
                    )
                ],
            ),
            turn_complete=True,
        )
        current_response = []
        async for raw_response in self.text_session.receive():
            if raw_response.text:
                current_response.append(raw_response.text)
                if "".join(current_response).startswith("OK"):
                    self.initialized = True
                    return

    async def listen_audio(self):
        """监听音频输入"""
        mic_info = pya.get_default_input_device_info()
        self.audio_stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=SEND_SAMPLE_RATE,
            input=True,
            input_device_index=mic_info["index"],
            frames_per_buffer=CHUNK_SIZE,
        )
        if __debug__:
            kwargs = {"exception_on_overflow": False}
        else:
            kwargs = {}

        log_console.print("🎤 请说英语", style="yellow")
        while True:
            if self.paused:
                await asyncio.sleep(0.1)
                continue

            data = await asyncio.to_thread(self.audio_stream.read, CHUNK_SIZE, **kwargs)
            if self.running_step > 1:
                continue

            # 音量检测
            volume = self.calculate_volume(data)
            if volume == 0:
                log_console.print("🎤 :", style="yellow", end="")
                continue
            is_speaking = self.detect_speaking(volume)
            # 调试信息
            if DEBUG_VOLUME:
                log_console.print(f"\r音量: {volume:.1f}, 阈值: {self.adaptive_threshold:.1f}, 说话: {is_speaking}", style="dim", end="")

            if is_speaking:
                if self.running_step == 0:
                    log_console.print("🎤 :", style="yellow", end="")
                    self.running_step += 1
                log_console.print("*", style="green", end="")
            elif self.running_step > 0:
                # 说话停止，重置状态
                self.running_step = 0
                log_console.print()  # 换行

            await self.audio_out_queue.put({"data": data, "mime_type": "audio/pcm"})

    async def send_realtime(self):
        """发送音频数据"""
        while True:
            if self.paused:
                await asyncio.sleep(0.1)
                continue

            msg = await self.audio_out_queue.get()
            await self.live_session.send_realtime_input(audio=msg)

    async def receive_audio(self):
        """接收音频数据并处理"""
        while True:
            turn = self.live_session.receive()
            async for response in turn:
                if self.running_step == 1:
                    log_console.print("\n♻️ 处理中：", end="")
                    self.running_step += 1

                if data := response.data:
                    self.audio_in_queue.put_nowait(data)
                    continue
                if text := response.text:
                    # 检查是否是控制命令
                    if "can i have a break" in text.lower():
                        self.paused = True
                        log_console.print("\n⏸️ 会话已暂停。说 'OK let's continue' 继续", style="yellow")
                    elif "ok let's continue" in text.lower() and self.paused:
                        self.paused = False
                        log_console.print("\n▶️ 会话继续", style="green")

                    # 显示响应
                    log_console.print("\n🤖 =============================================", style="yellow")
                    log_console.print(Markdown(text))

                self.running_step = 0 if not self.paused else 2

            # If you interrupt the model, it sends a turn_complete.
            # For interruptions to work, we need to stop playback.
            # So empty out the audio queue because it may have loaded
            # much more audio than has played yet.
            while not self.audio_in_queue.empty():
                self.audio_in_queue.get_nowait()

    async def play_audio(self):
        stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=RECEIVE_SAMPLE_RATE,
            output=True,
        )
        while True:
            bytestream = await self.audio_in_queue.get()
            log_console.print("🙎 声音播放中........", style="yellow")
            await asyncio.to_thread(stream.write, bytestream)
            log_console.print("🙎 播放完毕", style="green")

    async def run(self):
        try:
            async with (
                client.aio.live.connect(model=MODEL, config=CONFIG) as live_session,
                client.aio.live.connect(model=MODEL, config=CONFIG_TEXT) as text_session,
                asyncio.TaskGroup() as tg,
            ):
                self.live_session = live_session
                self.text_session = text_session

                log_console.print("Gemini 英语口语助手", style="green", highlight=True)
                log_console.print("Make by Adam Zhou: X@summychou", style="blue")
                log_console.print("============================================", style="yellow")

                await self.startup()
                if not self.initialized:
                    log_console.print("初始化失败 ❌", style="red")
                    return
                log_console.print("初始化完成 ✅", style="green")
                log_console.print("请开始你的表演", style="yellow")

                self.audio_out_queue = asyncio.Queue(maxsize=5)
                self.audio_in_queue = asyncio.Queue()

                tg.create_task(self.listen_audio())
                tg.create_task(self.send_realtime())
                tg.create_task(self.receive_audio())
                tg.create_task(self.play_audio())

                def check_error(task):
                    if task.cancelled():
                        return
                    if task.exception():
                        log_console.print(f"Error: {task.exception()}", style="red")
                        sys.exit(-1)

                for task in tg._tasks:
                    task.add_done_callback(check_error)

        except asyncio.CancelledError:
            pass
        except asyncio.ExceptionGroup as EG:
            if self.audio_stream:
                self.audio_stream.close()
            traceback.print_exception(EG)


if __name__ == "__main__":
    loop = AudioLoop()
    asyncio.run(loop.run())
