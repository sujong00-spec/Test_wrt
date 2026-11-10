# 数据目录（内容不进仓库）

| 文件 | 用途 | 是否入库 |
| --- | --- | --- |
| `baidu.json` | 手写文字识别密钥（`api_key` / `secret_key`） | ✗ 只提交 `baidu.json.example` |
| `secrets.env` | 语音/视觉模型 token（一行一个 `KEY=VALUE`） | ✗ 只提交 `secrets.env.example` |
| `moxie.db` | 默写记录（每轮清单、批改、时长） | ✗ |
| `state.json` | 当前清单与设置 | ✗ |
| `access.json` | 访问口令 | ✗ |
| `results/` | 孩子写完的答案照片 | ✗ |

`data/` 整个目录加进 `.gitignore`（`*.example` 除外），**提交前请确认里面没有 `secrets.env`、`baidu.json` 与任何照片**。

## 从示例开始

```bash
cp data/baidu.json.example data/baidu.json
cp data/secrets.env.example data/secrets.env
```

两个文件都是可选的：不填就只用「手动输入」，语音/视觉通道自动降级。
