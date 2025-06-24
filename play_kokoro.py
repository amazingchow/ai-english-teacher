import soundfile as sf
from kokoro import KPipeline

pipeline = KPipeline(lang_code="a")
text = """
Hello, how are you? I'm a student from China. My name is Alice.
"""
generator = pipeline(text, voice="af_heart")
for i, (gs, ps, audio) in enumerate(generator):
    print(i, gs, ps)
    sf.write(f"{i}.wav", audio, 24000)
