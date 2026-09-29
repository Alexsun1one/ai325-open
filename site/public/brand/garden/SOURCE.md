# brand/garden 资产来源

两张图均为 Sun 自有项目 SilicoVille（`/Users/sunwuyuan/Desktop/01-项目/cursor_0311`）的既有美术，
经 GARDEN R1 任务书授权原样复制到本站使用（不裁不改，UI 侧只做 CSS 定位/裁剪展示）。

| 文件 | 源路径 | sha256 | 本站用途 |
| --- | --- | --- | --- |
| `cozy-homestead-v1.webp` | `cursor_0311/public/assets/homestead/cozy-homestead-v1.webp` | `e58cab9252095d1815de5d9217aff1f17c426926738341f1faaf43b7656e70de` | 未开通页主视觉 + 家园页头装饰条（固定比例 object-fit，懒加载） |
| `survival-crops-v1.png` | `cursor_0311/public/assets/world/survival-crops-v1.png` | `d90ca8f58796059116095c6d00ab1b533b12a373e27a6d4102a6d601914c5fff` | 地块内景 sprite：左半幅=苗期，右半幅=成熟期（CSS background-position 定位，不改图） |

实测尺寸：homestead 1254×1254；crops 1774×887（任务书口径 1786×893，以实测为准）。
地块的实时状态由服务端响应驱动（DOM 按钮），这两张图只是装饰与状态插画，不是交互本体。
