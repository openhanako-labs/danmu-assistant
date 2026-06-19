"""
弹幕皮肤模块
Phase 2: 不同类型弹幕有不同样式
"""
from dataclasses import dataclass
from typing import Dict, Optional
import random


@dataclass
class DanmuSkin:
    """弹幕皮肤"""
    font_size: int = 16
    font_bold: bool = True
    colors: list = None  # 颜色列表
    stroke_width: int = 2  # 描边宽度
    shadow_offset: tuple = (1, 1)  # 阴影偏移 (x, y)
    shadow_color: str = "rgba(0,0,0,128)"  # 阴影颜色
    background_alpha: int = 0  # 背景透明度
    font_family: str = "Microsoft YaHei"
    
    def __post_init__(self):
        if self.colors is None:
            self.colors = self._get_default_colors()
    
    def _get_default_colors(self) -> list:
        """获取默认颜色"""
        return [
            "#FFFFFF",  # 白色
            "#FF6B6B",  # 红色
            "#4ECDC4",  # 青色
            "#45B7D1",  # 蓝色
            "#96CEB4",  # 绿色
            "#FFEAA7",  # 黄色
            "#DDA0DD",  # 紫色
        ]
    
    def get_random_color(self) -> str:
        """随机获取颜色"""
        return random.choice(self.colors)


class DanmuSkinManager:
    """
    弹幕皮肤管理器
    
    为不同类型的弹幕分配不同的皮肤
    """
    
    # 预定义皮肤
    SKINS = {
        "default": DanmuSkin(
            font_size=16,
            colors=["#FFFFFF", "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7", "#DDA0DD"]
        ),
        "meme": DanmuSkin(
            font_size=18,
            font_bold=True,
            colors=["#FF6B6B", "#FFEAA7", "#DDA0DD"],  # 暖色调
            stroke_width=3,
            shadow_offset=(2, 2)
        ),
        "comment": DanmuSkin(
            font_size=16,
            font_bold=False,
            colors=["#FFFFFF", "#98D8C8", "#45B7D1"],  # 冷色调
            stroke_width=2
        ),
        "reaction": DanmuSkin(
            font_size=20,
            font_bold=True,
            colors=["#FF6B6B", "#FF9FF3", "#54A0FF"],  # 鲜艳色调
            stroke_width=4,
            shadow_offset=(3, 3)
        ),
        "highlight": DanmuSkin(
            font_size=22,
            font_bold=True,
            colors=["#FFD700", "#FF6B6B"],  # 金色和红色
            stroke_width=5,
            shadow_offset=(4, 4)
        )
    }
    
    def __init__(self, default_skin: str = "default"):
        """
        Args:
            default_skin: 默认皮肤名称
        """
        self.default_skin = default_skin
        self.custom_skins: Dict[str, DanmuSkin] = {}
    
    def get_skin(self, danmu_type: str) -> DanmuSkin:
        """
        获取指定类型的皮肤
        
        Args:
            danmu_type: 弹幕类型 (comment/meme/reaction/highlight)
            
        Returns:
            DanmuSkin 对象
        """
        # 优先使用自定义皮肤
        if danmu_type in self.custom_skins:
            return self.custom_skins[danmu_type]
        # 其次使用预定义皮肤
        if danmu_type in self.SKINS:
            return self.SKINS[danmu_type]
        # 最后使用默认皮肤
        return self.SKINS.get(self.default_skin, DanmuSkin())
    
    def register_skin(self, name: str, skin: DanmuSkin):
        """
        注册自定义皮肤
        
        Args:
            name: 皮肤名称
            skin: DanmuSkin 对象
        """
        self.custom_skins[name] = skin
    
    def get_all_skin_names(self) -> list:
        """获取所有皮肤名称"""
        return list(self.SKINS.keys()) + list(self.custom_skins.keys())


# 全局皮肤管理器实例
skin_manager = DanmuSkinManager()


if __name__ == "__main__":
    # 测试
    print("=== 弹幕皮肤管理器测试 ===")
    
    # 获取不同类型弹幕的皮肤
    for danmu_type in ["comment", "meme", "reaction", "highlight"]:
        skin = skin_manager.get_skin(danmu_type)
        print(f"\n[{danmu_type}] 皮肤:")
        print(f"  字体大小: {skin.font_size}")
        print(f"  是否粗体: {skin.font_bold}")
        print(f"  颜色: {skin.colors}")
        print(f"  描边宽度: {skin.stroke_width}")
        print(f"  阴影偏移: {skin.shadow_offset}")
    
    print("\n弹幕皮肤管理器测试通过 ✓")
