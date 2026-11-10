"""从 data/secrets.env 读凭据（如果存在）。

这个文件只在本机，权限 600，不进版本库；没有它也能启动，只是语音/视觉识别会不可用。
格式：一行一个 KEY=VALUE。
"""

import os
from pathlib import Path


def load_local_env(root):
    path = Path(root) / 'data' / 'secrets.env'
    if not path.exists():
        return 0
    n = 0
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v
            n += 1
    return n
