"""核心业务逻辑层（纯业务，不知道 edition、不 import 平台 SDK）。

只认 `connectors.base` 的抽象契约 + 注入进来的 store / pace 对象，
绝不出现 `if is_premium` / `weixin` 这类字眼。版本差异只准在
`capabilities.py` + `assemble.py`，本层一律不动。
"""
