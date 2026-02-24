# batch_whisper_transcriber.py
# Whisper 오디오/비디오 배치 전사 도구
# https://github.com/YOUR_USERNAME/whisper-batch-tool

import os
import re
import whisper
import subprocess
import time
import sys
from pathlib import Path

class BatchWhisperTranscriber:
    def __init__(self):
        self.models = {
            1: "tiny",
            2: "base", 
            3: "small",
            4: "medium",
            5: "large"
        }
        
        self.model = None
        self.script_dir = Path(__file__).parent
        
        # 콘솔 창 제목 설정
        if sys.platform == "win32":
            os.system("title Whisper 배치 전사 시스템")
    
    def detect_repetition(self, text, threshold=3):
        """전체 텍스트에서 반복되는 문구를 감지하고 제거"""
        if not text or len(text.strip()) < 10:
            return text
        
        cleaned = text
        for pattern_len in range(50, 2, -1):
            pattern = re.compile(r'(.{' + str(pattern_len) + r',})\1{' + str(threshold - 1) + r',}')
            cleaned = pattern.sub(r'\1', cleaned)
        
        return cleaned.strip()
    
    def filter_hallucinated_segments(self, segments):
        """세그먼트 단위로 연속 반복 및 환각 감지 후 제거"""
        if not segments:
            return segments
        
        filtered = []
        prev_text = ""
        repeat_count = 0
        max_repeats = 2

        for seg in segments:
            text = seg["text"].strip()
            
            # 빈 텍스트 건너뛰기
            if not text or len(text) < 2:
                continue
            
            # 비한국어 환각 필터: 한글 비율이 40% 미만이면 hallucination으로 간주
            korean_chars = len(re.findall(r'[가-힣]', text))
            total_chars = len(re.findall(r'[a-zA-Z가-힣]', text))
            if total_chars > 0 and korean_chars / total_chars < 0.4:
                continue
            
            # 이전 세그먼트와 동일한 텍스트인지 체크
            if text == prev_text:
                repeat_count += 1
                if repeat_count >= max_repeats:
                    continue
            else:
                repeat_count = 0
            
            # 텍스트 내부에서 같은 짧은 구절이 과도하게 반복되는지 체크
            words = text.split()
            if len(words) > 3:
                unique_words = set(words)
                if len(unique_words) / len(words) < 0.2:
                    deduplicated = ' '.join(list(dict.fromkeys(words)))
                    seg = dict(seg)
                    seg["text"] = deduplicated
            
            prev_text = text
            filtered.append(seg)
        
        return filtered

    def print_header(self):
        """헤더 출력"""
        print("=" * 60)
        print("🎬 Whisper 오디오/비디오 → TXT 배치 변환기")
        print("=" * 60)
        print(f"📁 작업 디렉토리: {self.script_dir}")
        print(f"🐍 Python: {sys.version.split()[0]}")
        print("=" * 60)
    
    def select_model(self):
        """모델 선택"""
        print("\n🤖 Whisper 모델 선택:")
        print("-" * 50)
        
        model_info = {
            1: ("tiny", "매우 빠름", "낮음", "~39MB"),
            2: ("base", "빠름", "보통", "~74MB"), 
            3: ("small", "보통", "높음", "~244MB"),
            4: ("medium", "느림", "매우 높음", "~769MB"),
            5: ("large", "매우 느림", "최고", "~1550MB")
        }
        
        for key, (name, speed, quality, size) in model_info.items():
            print(f"  {key}: {name:8} | 속도: {speed:10} | 품질: {quality:10} | 크기: {size}")
        
        print("-" * 50)
        
        while True:
            try:
                choice = input("모델 번호 선택 (기본 3=small): ").strip()
                if choice == "":
                    choice = 3
                else:
                    choice = int(choice)
                
                if choice in self.models:
                    model_name = self.models[choice]
                    break
                else:
                    print("❌ 1-5 사이의 숫자를 입력하세요.")
            except ValueError:
                print("❌ 올바른 숫자를 입력하세요.")
        
        print(f"\n🔄 '{model_name}' 모델 로딩 중...")
        
        try:
            start_time = time.time()
            self.model = whisper.load_model(model_name)
            load_time = time.time() - start_time
            print(f"✅ 모델 로드 완료! ({load_time:.1f}초 소요)")
        except Exception as e:
            print(f"❌ 모델 로드 실패: {e}")
            input("Enter를 눌러 종료...")
            sys.exit(1)
        
        return model_name
    
    def select_target_extension(self):
        """작업 대상 확장자 선택"""
        print("\n🎯 작업 대상 선택:")
        print("  1: MKV 파일 (오디오 추출 후 전사)")
        print("  2: WAV 파일 (직접 전사)")
        
        while True:
            choice = input("선택 (기본 1): ").strip()
            if choice == "" or choice == "1":
                return ".mkv"
            elif choice == "2":
                return ".wav"
            else:
                print("❌ 1 또는 2를 입력하세요.")

    def find_target_files(self, extension):
        """현재 디렉토리에서 대상 파일 찾기"""
        files = list(self.script_dir.glob(f"*{extension}"))
        
        ext_upper = extension[1:].upper()
        print(f"\n📹 {ext_upper} 파일 검색 결과:")
        print("-" * 50)
        
        if not files:
            print(f"❌ 현재 디렉토리에 {ext_upper} 파일이 없습니다.")
            print(f"📂 현재 위치: {self.script_dir}")
            print(f"\n💡 {ext_upper} 파일을 이 폴더에 넣고 다시 실행하세요.")
            input("\nEnter를 눌러 종료...")
            return []
        
        total_size = 0
        for i, file in enumerate(files, 1):
            size_mb = file.stat().st_size / (1024 * 1024)
            total_size += size_mb
            print(f"  {i:2d}: {file.name} ({size_mb:.1f}MB)")
        
        print("-" * 50)
        print(f"📊 총 {len(files)}개 파일, {total_size:.1f}MB")
        
        return files
    
    def check_ffmpeg(self):
        """ffmpeg 설치 확인"""
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print("✅ ffmpeg 확인됨")
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        print("❌ ffmpeg를 찾을 수 없습니다!")
        print("💡 ffmpeg 설치가 필요합니다:")
        print("   1. https://ffmpeg.org/download.html")
        print("   2. 또는 'winget install ffmpeg' (Windows 11)")
        print("   3. 또는 'choco install ffmpeg' (Chocolatey)")
        input("\nEnter를 눌러 종료...")
        return False
    
    def extract_audio(self, mkv_file):
        """MKV에서 WAV 추출"""
        wav_file = mkv_file.with_suffix('.wav')
        
        if wav_file.exists():
            size_mb = wav_file.stat().st_size / (1024 * 1024)
            print(f"⚠️  {wav_file.name} 이미 존재 ({size_mb:.1f}MB) - 건너뛰기")
            return wav_file
        
        print(f"🎵 오디오 추출: {mkv_file.name} → {wav_file.name}")
        
        cmd = [
            'ffmpeg', '-i', str(mkv_file),
            '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
            '-y', str(wav_file)
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0 and wav_file.exists():
                size_mb = wav_file.stat().st_size / (1024 * 1024)
                print(f"✅ 추출 완료: {wav_file.name} ({size_mb:.1f}MB)")
                return wav_file
            else:
                print(f"❌ 추출 실패: {result.stderr[:200]}")
                return None
                
        except Exception as e:
            print(f"❌ 추출 중 오류: {e}")
            return None
    
    def transcribe_audio(self, wav_file, model_name):
        """WAV 파일을 Whisper로 전사"""
        txt_file = wav_file.with_suffix('.txt')
        
        if txt_file.exists():
            print(f"⚠️  {txt_file.name} 이미 존재")
            while True:
                overwrite = input("   덮어쓸까요? (y/n/s=건너뛰기): ").lower()
                if overwrite == 'y':
                    break
                elif overwrite in ['n', 's']:
                    print("   건너뛰기")
                    return txt_file
                else:
                    print("   y, n, s 중 하나를 입력하세요.")
        
        print(f"🎤 전사 시작: {wav_file.name} (모델: {model_name})")
        
        try:
            start_time = time.time()
            
            print("   처리 중", end="", flush=True)
            
            result = self.model.transcribe(
                str(wav_file),
                language='ko',
                fp16=False,
                verbose=False,
                condition_on_previous_text=False,  # 이전 텍스트 참조 차단 → 반복 방지
                no_speech_threshold=0.6,
                logprob_threshold=-1.0,
                compression_ratio_threshold=2.4
            )
            
            elapsed = time.time() - start_time
            
            # 후처리: 반복 텍스트 제거
            cleaned_text = self.detect_repetition(result["text"])
            filtered_segments = self.filter_hallucinated_segments(result["segments"])
            
            original_seg_count = len(result["segments"])
            filtered_seg_count = len(filtered_segments)
            if original_seg_count != filtered_seg_count:
                print(f"   🔧 반복 필터링: {original_seg_count}개 → {filtered_seg_count}개 세그먼트")
            
            # 결과 저장
            with open(txt_file, 'w', encoding='utf-8') as f:
                f.write(f"# Whisper 전사 결과\n")
                f.write(f"# 원본 파일: {wav_file.stem}{wav_file.suffix}\n")
                f.write(f"# 모델: {model_name}\n")
                f.write(f"# 전사 시간: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# 처리 시간: {elapsed:.1f}초\n")
                f.write("#" + "=" * 60 + "\n\n")
                
                # 전체 텍스트
                f.write("## 📝 전체 텍스트\n\n")
                f.write(cleaned_text + "\n\n")
                
                # 시간별 세그먼트
                f.write("## ⏱️ 시간별 세그먼트\n\n")
                for segment in filtered_segments:
                    start = int(segment["start"])
                    end = int(segment["end"])
                    text = segment["text"].strip()
                    
                    start_str = f"{start//60:02d}:{start%60:02d}"
                    end_str = f"{end//60:02d}:{end%60:02d}"
                    
                    f.write(f"[{start_str}-{end_str}] {text}\n")
            
            # 결과 통계
            word_count = len(cleaned_text.split())
            char_count = len(cleaned_text)
            
            print(f"\n✅ 전사 완료: {txt_file.name}")
            print(f"   📊 {word_count}단어, {char_count}글자, {elapsed:.1f}초 소요")
            
            return txt_file
            
        except Exception as e:
            print(f"\n❌ 전사 실패: {e}")
            return None
    
    def process_all(self):
        """전체 처리"""
        self.print_header()
        
        # 0. 작업 대상 확장자 선택
        extension = self.select_target_extension()
        
        # 사전 체크
        if not self.check_ffmpeg():
            return
        
        # 1. 모델 선택
        model_name = self.select_model()
        
        # 2. 파일 찾기
        target_files = self.find_target_files(extension)
        if not target_files:
            return
        
        # 3. 처리 모드 선택
        print(f"\n⚙️ 처리 모드 선택:")
        print("  1: 전체 자동 처리 (중간 파일 자동 삭제)")
        print("  2: 단계별 확인 처리")
        
        while True:
            try:
                mode = input("모드 선택 (기본 1): ").strip()
                mode = int(mode) if mode else 1
                if mode in [1, 2]:
                    break
                else:
                    print("❌ 1 또는 2를 입력하세요.")
            except ValueError:
                print("❌ 올바른 숫자를 입력하세요.")
        
        # 4. 처리 시작
        print(f"\n🚀 처리 시작 (모드: {'자동' if mode == 1 else '수동'})")
        print("=" * 60)
        
        start_time = time.time()
        success_count = 0
        total_files = len(target_files)
        
        for i, file in enumerate(target_files, 1):
            print(f"\n📂 [{i}/{total_files}] {file.name}")
            print("-" * 40)
            
            if mode == 2:
                process = input("이 파일을 처리할까요? (Y/n): ")
                if process.lower() == 'n':
                    print("건너뛰기")
                    continue
            
            try:
                # 오디오 추출 (MKV인 경우에만)
                if extension == ".mkv":
                    wav_file = self.extract_audio(file)
                    is_temp_wav = True
                else:
                    wav_file = file
                    is_temp_wav = False
                
                if not wav_file:
                    continue
                
                # 전사
                txt_file = self.transcribe_audio(wav_file, model_name)
                if txt_file:
                    success_count += 1
                    
                    # MKV에서 추출한 임시 WAV 파일 정리
                    if is_temp_wav:
                        if mode == 1:
                            wav_file.unlink()
                            print(f"🗑️  임시 파일 삭제: {wav_file.name}")
                        else:
                            delete = input("추출된 WAV 파일을 삭제할까요? (y/N): ")
                            if delete.lower() == 'y':
                                wav_file.unlink()
                                print(f"🗑️  삭제됨: {wav_file.name}")
                
            except KeyboardInterrupt:
                print(f"\n\n⚠️ 사용자 중단...")
                break
            except Exception as e:
                print(f"❌ 처리 실패: {e}")
        
        # 결과 요약
        total_time = time.time() - start_time
        self.print_summary(success_count, total_files, total_time)
    
    def print_summary(self, success, total, elapsed):
        """결과 요약 출력"""
        print(f"\n" + "=" * 60)
        print(f"📊 처리 완료 요약")
        print("=" * 60)
        print(f"✅ 성공: {success}/{total}개 파일")
        print(f"⏱️  총 소요시간: {elapsed/60:.1f}분")
        print(f"📁 결과 위치: {self.script_dir}")
        
        # 생성된 TXT 파일 목록
        txt_files = list(self.script_dir.glob("*.txt"))
        if txt_files:
            print(f"\n📝 생성된 전사 파일:")
            for txt_file in sorted(txt_files):
                size_kb = txt_file.stat().st_size / 1024
                print(f"  📄 {txt_file.name} ({size_kb:.1f}KB)")

def main():
    try:
        transcriber = BatchWhisperTranscriber()
        transcriber.process_all()
        
    except KeyboardInterrupt:
        print(f"\n\n🛑 프로그램이 중단되었습니다.")
    except Exception as e:
        print(f"\n❌ 예상치 못한 오류: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n" + "=" * 60)
    input("완료! Enter를 눌러 종료하세요...")

if __name__ == "__main__":
    main()
