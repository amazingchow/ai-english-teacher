# -*- coding: utf-8 -*-
# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
import sys
import traceback

import os
import json
import pyaudio
import numpy as np
from rich.console import Console
from rich.markdown import Markdown

from google import genai
from google.genai import types

if sys.version_info < (3, 11, 0):
    import taskgroup, exceptiongroup

    asyncio.TaskGroup = taskgroup.TaskGroup
    asyncio.ExceptionGroup = exceptiongroup.ExceptionGroup

# 基础配置
FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000  # 16000
CHUNK_SIZE = 1024  # 512

# 语音设置
pya = pyaudio.PyAudio()
# 主题和场景定义
THEMES = {
    "business": ["job interview", "business meeting", "presentation", "networking"],
    "travel": ["airport", "hotel", "restaurant", "sightseeing"],
    "daily life": ["shopping", "weather", "hobbies", "family"],
    "social": ["meeting friends", "party", "social media", "dating"],
}

client = genai.Client()  # GOOGLE_API_KEY must be set as env variable

MODEL = "gemini-2.0-flash-live-001"
CONFIG = {"response_modalities": ["AUDIO"]}
CONFIG_TEXT = {"response_modalities": ["TEXT"]}


class AudioLoop:

    def __init__(self):
        self.paused = False
        self.current_theme = None
        self.current_scenario = None
        self.console = Console()
        self.audio_in_queue = None
        self.out_queue = None
        self.live_session = None
        self.text_session = None
        self.audio_stream = None
        self.receive_audio_task = None
        self.play_audio_task = None
        self.voice_client = None

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
            self.console.print(f"评分计算错误: {e}", style="red")
            return 70  # 出错时返回默认分数

    async def startup(self):
        await self.text_session.send_client_content(
            turns=types.Content(
            role='user',
            parts=[types.Part(text="""
你是一名专业的英语口语指导老师。请用中英文双语进行回复，英文在前中文在后，用 --- 分隔。
                                
Your responsibilities are:
1. Help users correct grammar and pronunciation
2. Give pronunciation scores and detailed feedback
3. Understand and respond to control commands:
   - Pause when user says "Can I have a break"
   - Continue when user says "OK let's continue"
4. Provide practice sentences based on chosen themes and scenarios

你的职责是：
1. 帮助用户纠正语法和发音
2. 给出发音评分和详细反馈
3. 理解并响应用户的控制指令：
   - 当用户说"Can I have a break"时暂停
   - 当用户说"OK let's continue"时继续
4. 基于选择的主题和场景提供练习句子

First, ask which theme they want to practice (business, travel, daily life, social) in English.

每次用户说完一个句子后，你需要：
1. 识别用户说的内容（英文）
2. 给出发音评分（0-100分）
3. 详细说明发音和语法中的问题（中英文对照）
4. 提供改进建议（中英文对照）
5. 提供下一个相关场景的练习句子（中英文对照）

请始终保持以下格式：
[English content]
---
[中文内容]

如果明白了请用中英文回答OK
""")]
            ),
            turn_complete=True
        )
        async for raw_response in self.text_session.receive():
            response = json.loads(raw_response)

    async def listen_audio(self):
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

        self.console.print("🎤 请说英语", style="yellow")
        while True:
            data = await asyncio.to_thread(self.audio_stream.read, CHUNK_SIZE, **kwargs)
            await self.out_queue.put({"data": data, "mime_type": "audio/pcm"})

    async def send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.live_session.send_realtime_input(audio=msg)

    async def receive_audio(self):
        "Background task to reads from the websocket and write pcm chunks to the output queue"
        while True:
            turn = self.live_session.receive()
            async for response in turn:
                if data := response.data:
                    self.audio_in_queue.put_nowait(data)
                    continue
                if text := response.text:
                    print(text, end="")

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
            await asyncio.to_thread(stream.write, bytestream)

    async def run(self):
        # proxy = Proxy.from_url(os.environ["HTTP_PROXY"]) if os.environ.get("HTTP_PROXY") else None
        # if proxy:
        #     self.console.print("使用代理", style="yellow")
        # else:
        #     self.console.print("不使用代理", style="yellow")

        try:
            async with (
                # client.aio.live.connect(model=MODEL, config=CONFIG) as live_session,
                client.aio.live.connect(model=MODEL, config=CONFIG_TEXT) as text_session,
                asyncio.TaskGroup() as tg,
            ):
                self.console.print("Gemini 英语口语助手", style="green", highlight=True)
                self.console.print("Make by Adam Zhou: X@summychou", style="blue")
                self.console.print("============================================", style="yellow")
                
                # self.live_session = live_session
                self.text_session = text_session

                await self.startup()

                # self.audio_in_queue = asyncio.Queue()
                # self.out_queue = asyncio.Queue(maxsize=5)

                # tg.create_task(self.send_realtime())
                # tg.create_task(self.listen_audio())
                # tg.create_task(self.receive_audio())
                # tg.create_task(self.play_audio())
        except asyncio.CancelledError:
            pass
        except asyncio.ExceptionGroup as EG:
            if self.audio_stream:
                self.audio_stream.close()
            traceback.print_exception(EG)


if __name__ == "__main__":
    loop = AudioLoop()
    asyncio.run(loop.run())
