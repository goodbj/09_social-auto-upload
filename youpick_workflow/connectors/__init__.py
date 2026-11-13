"""平台适配层（可插拔）。

core/ 只允许 import 本层 `connectors.base` 的抽象契约，绝不允许直接 import
`platform.weixin` / `platform.douyin` ……否则就黏上了具体平台。
新增平台 = 在 platform/ 下加一个实现 PlatformClient 的文件，core 一行不用改。
"""
