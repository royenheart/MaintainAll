#!/usr/bin/env python3
import wave
import sys
import os
import json
import argparse
import tempfile
import ffmpeg
from vosk import KaldiRecognizer, Model, SetLogLevel

SetLogLevel(level=-1)

parser = argparse.ArgumentParser(
    description="Vosk Audio2Speech",
    formatter_class=argparse.RawDescriptionHelpFormatter,
)
parser.add_argument("-a", "--audio", required=True, type=str, help="set audio file")
parser.add_argument("-o", "--output", required=True, type=str, help="set output file")
parser.add_argument("-m", "--model", required=True, type=str, help="set model path")

args = parser.parse_args()

audio = args.audio
output = args.output
model = args.model


def wf_open(audio_file) -> wave.Wave_read:
    wf: wave.Wave_read = wave.open(os.path.join(audio_file), "rb")
    if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getcomptype() != "NONE":
        raise Exception("Audio file must be WAV format mono PCM.")
    return wf


try:
    wf = wf_open(audio_file=audio)
except FileNotFoundError:
    print(f"Audio file {audio} not found.", file=sys.stderr)
    sys.exit(1)
except (wave.Error, Exception) as e:
    print(f"Audio {audio} parse error: {e}", file=sys.stderr)
    print(f"Now try to use ffmpeg to convert {audio} to WAV format mono PCM.")
    tempd = tempfile.mkdtemp()
    tempaudio = os.path.join(tempd, "tmp.wav")
    try:
        stream = ffmpeg.input(audio)
        stream = ffmpeg.output(stream, tempaudio, ac=1, ar=16000, format="wav")
        ffmpeg.run(stream)
        print(f"Audio {audio} has been converted to {tempaudio}.")
    except ffmpeg.Error as e:
        print(f"ffmpeg convert error: {e}", file=sys.stderr)
    wf = wf_open(audio_file=tempaudio)

model = Model(model_path=model)

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
with open(output, "w", encoding="utf-8") as f:
    for line in results:
        f.write(line + "\n")

print(f"Transcription of audio {audio} saved to {output}")
