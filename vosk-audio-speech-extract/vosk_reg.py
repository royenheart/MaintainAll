import wave
import sys
import os
import json
from vosk import KaldiRecognizer, Model, SetLogLevel

SetLogLevel(level=-1)

wf: wave.Wave_read = wave.open(os.path.join("output_audio.wav"), "rb")
if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getcomptype() != "NONE":
    print("Audio file must be WAV format mono PCM.")
    sys.exit(1)

model = Model(model_path="vosk-model-small-cn-0.22")

rec = KaldiRecognizer(model, wf.getframerate())
rec.SetWords(True)
rec.SetPartialWords(True)

# 用于存储识别结果的列表
results = []

# 逐帧读取音频并进行识别
while True:
    data = wf.readframes(4000)
    if len(data) == 0:
        break
    if rec.AcceptWaveform(data):
        result = json.loads(rec.Result())["text"]
        print(result)
        results.append(result)
    else:
        pass
        # print(rec.PartialResult())

# 获取最后的识别结果
final_result = json.loads(rec.FinalResult())["text"]
print(final_result)
results.append(final_result)

# 将识别结果存储到文件中
with open("transcription.txt", "w", encoding="utf-8") as f:
    for line in results:
        f.write(line + "\n")

print("Transcription saved to transcription.txt")
