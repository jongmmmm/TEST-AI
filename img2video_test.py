# ============================================================
# LTX-2 이미지 → 비디오 변환 (Google Colab용)
# 사용법: Colab에서 런타임 → 런타임 유형 변경 → GPU 선택 후 실행
# ============================================================
# 1. 패키지 설치
#!pip install -q git+https://github.com/huggingface/diffusers
#!pip install -q transformers accelerate sentencepiece protobuf imageio imageio-ffmpeg ipywidgets

# 2. GPU 확인
import os
os.environ["HF_HOME"] = "/media/nas2/seunghwa.paik/hf_cache"

import torch
print(f"PyTorch: {torch.__version__}")
print(f"CUDA 사용 가능: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
else:
    raise RuntimeError("GPU가 없습니다! 런타임 → 런타임 유형 변경 → GPU 선택하세요.")

# 3. 이미지 경로 지정
image_path = '/home/yms/test/7170113c6a983.jpg'
print(f"\n이미지: {image_path}")

# 4. 프롬프트 입력
# prompt = input("\n프롬프트 입력 (영어, 엔터=기본값): ").strip()
# if not prompt:
prompt = "The scene comes to life with gentle natural movement, cinematic lighting, smooth camera motion"
print(f"프롬프트: {prompt}")

# 5. 모델 로드
from diffusers import LTXImageToVideoPipeline
from diffusers.utils import load_image, export_to_video
import os
from pathlib import Path

SAVE_DIR = "/media/nas2/seunghwa.paik"
os.makedirs(SAVE_DIR, exist_ok=True)

print("\n모델 로드 중... (최초 실행 시 다운로드에 시간이 걸립니다)")
pipe = LTXImageToVideoPipeline.from_pretrained(
    "Lightricks/LTX-Video",
    torch_dtype=torch.bfloat16,
    cache_dir=os.path.join(SAVE_DIR, "models"),
)
pipe.enable_model_cpu_offload()
pipe.vae.enable_tiling()
print("모델 로드 완료!")

# 6. 비디오 생성
import time

image = load_image(image_path)
print(f"\n원본 이미지 크기: {image.size}")
print("비디오 생성 중... (약 3~10분 소요)")

start = time.time()
video = pipe(
    image=image,
    prompt=prompt,
    negative_prompt="worst quality, inconsistent motion, blurry, jittery, distorted",
    width=704,
    height=480,
    num_frames=81,
    num_inference_steps=30,
    guidance_scale=3.0,
).frames[0]
print(f"생성 완료! ({time.time() - start:.1f}초 소요)")

# 7. 저장 및 다운로드
output_path = os.path.join(SAVE_DIR, Path(image_path).stem + "_video.mp4")
export_to_video(video, output_path, fps=24)
print(f"저장 완료: {output_path}")

print("완료!")