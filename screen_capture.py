"""
截屏模块 - 基于 mss 的高效截屏
"""
import mss
import PIL.Image
import io
import base64


def capture_screen(screen_index: int = 0) -> PIL.Image.Image:
    """
    截取指定显示器屏幕
    
    Args:
        screen_index: 显示器索引，0=主屏，1+=扩展屏
        
    Returns:
        PIL Image 对象
    """
    with mss.mss() as sct:
        monitors = sct.monitors
        if screen_index < len(monitors):
            monitor = monitors[screen_index]
        else:
            monitor = monitors[0]  # fallback 到主屏
            
        screenshot = sct.grab(monitor)
        img = PIL.Image.frombytes(
            "RGB", 
            screenshot.size, 
            screenshot.bgra, 
            "raw", 
            "BGRX"
        )
    return img


def compress_image(img: PIL.Image.Image, quality: int = 70) -> tuple[bytes, str]:
    """
    将图片压缩为 JPEG 并返回 base64
    
    Args:
        img: PIL Image 对象
        quality: JPEG 质量（1-100）
        
    Returns:
        (压缩后的 bytes, base64 字符串)
    """
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=quality)
    compressed = buffer.getvalue()
    b64 = base64.b64encode(compressed).decode("utf-8")
    return compressed, b64


def image_to_api_format(img: PIL.Image.Image, quality: int = 70) -> dict:
    """
    将图片转换为 LLM API 可用的格式
    
    Returns:
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
    """
    _, b64 = compress_image(img, quality)
    return {
        "type": "image_url",
        "image_url": {
            "url": f"data:image/jpeg;base64,{b64}"
        }
    }


if __name__ == "__main__":
    # 测试截屏
    print("正在截屏...")
    img = capture_screen(0)
    print(f"截屏成功: {img.size}")
    
    # 测试压缩
    compressed, b64 = compress_image(img, 70)
    print(f"压缩后大小: {len(compressed)} bytes")
    print(f"Base64 长度: {len(b64)} chars")
    print("截屏模块测试通过 ✓")
