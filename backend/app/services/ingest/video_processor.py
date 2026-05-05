import os
import subprocess
import speech_recognition as sr
from pytube import YouTube

class VideoProcessor:
    def __init__(self, temp_dir):
        self.temp_dir = temp_dir
        os.makedirs(temp_dir, exist_ok=True)
    
    def process(self, video_path_or_url):
        """
        处理视频文件或URL，提取音频并转文字
        """
        audio_path = None
        
        try:
            # 判断是本地文件还是URL
            if video_path_or_url.startswith(('http://', 'https://')):
                # 从YouTube下载视频
                yt = YouTube(video_path_or_url)
                stream = yt.streams.filter(only_audio=True).first()
                audio_path = stream.download(output_path=self.temp_dir, filename_prefix="temp_")
            else:
                # 本地视频文件，提取音频
                audio_path = os.path.join(self.temp_dir, "temp_audio.wav")
                subprocess.run([
                    "ffmpeg", "-i", video_path_or_url, "-vn", "-acodec", "pcm_s16le", 
                    "-ar", "44100", "-ac", "2", audio_path
                ], check=True)
            
            # 音频转文字
            recognizer = sr.Recognizer()
            with sr.AudioFile(audio_path) as source:
                audio = recognizer.record(source)
                text = recognizer.recognize_google(audio, language="zh-CN")
            
            return {
                "text": text,
                "metadata": {
                    "source": video_path_or_url,
                    "audio_path": audio_path
                }
            }
        except Exception as e:
            return {
                "text": "",
                "metadata": {
                    "source": video_path_or_url,
                    "error": str(e)
                }
            }
        finally:
            # 清理临时文件
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)