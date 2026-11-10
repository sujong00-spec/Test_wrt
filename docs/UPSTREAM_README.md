# 小学生默写助手 · kids-memory-buddy

给小学生用的默写/听写练习工具：**拍下作业本 → 自动认出要默写的内容 → 用你自己的声音一条一条念 → 写完整张纸拍一张 → 自动批改 → 错题本 + 能力评估**。

服务跑在自己家的电脑上，iPad / 手机浏览器打开就能用：不用装 App、不用注册、不采集数据。**所有能力都有本机部署方案**，从识别到朗读可以一件不出家门。

![首页](docs/screenshot-home.png)
![清单](docs/screenshot-list.png)

```
📷 拍照/选图 ──► 文字整理 ──► 逐条朗读 ──► 孩子写 ──► 📷 上传答案 ──► 自动批改 ──► 家长复核 ──► 错题本/评估
```

## 功能

- **中文默写 / 英文默写**两个分类，各自一套文字整理规则（中文去拼音去表头；英文保留字母、丢英文表头、逗号词表按词切）
- **拍照识别**：认出的内容进**可改可删可排序的核对页**，不会直接开念；识别通道可自动降级（本机 OCR → 手写识别接口 → 视觉大模型）
- **朗读**：默认用**系统自带音色**（Windows / macOS 自动挑中文音色，零配置、不联网、不需要参考录音）；想用**自己的声音**就把录音丢进 `voices/` 目录切到音色克隆；每条念两遍（`请默写：X` → 停 → `X`，句子用「请再听一遍」），节奏（手动 / 自动快 / 自动慢）与语速（快 / 正常 / 慢）各三档，语速用变速不变调处理
- **手输兜底**：一行一条打进去，或粘贴识别结果
- **批改**：上传孩子写完的纸 → 按顺序对齐逐条判 **对 / 错 / 没写** → 给出差异（少了哪个字、写成什么）→ **家长逐条复核修订**
- **错题本**：按错误次数聚合，一键生成「用错题再默一次」的清单；复核改对的自动移出
- **能力评估**：累计轮次 / 字数 / 正确率 / 连续打卡、近 14 天练习量、正确率趋势、中英文对比、最常错内容

## 快速开始

只要 Python 3.10+（**核心只用标准库**，不用 pip 装任何东西；ffmpeg 可选，装了才有三档语速与 mp3）。
**不配任何密钥也能直接跑**：朗读用系统自带音色，内容靠手动输入或本机 OCR；联网的识别通道纯属可选加强。

```bash
git clone https://github.com/<你的账号>/kids-memory-buddy.git
cd kids-memory-buddy
python3 server.py                # 默认 0.0.0.0:8770，本机打开 http://127.0.0.1:8770/
```

iPad / 手机访问：

1. 电脑上跑 `allow-lan.bat`（Windows，需管理员）或自行把端口暴露到局域网；
2. 同一 Wi-Fi 下打开 `http://<电脑IP>:8770/`；
3. Safari 打开后「分享 → 添加到主屏幕」，就当 App 用。

不在家里用：`python3 tunnel.py --minutes 30` 开一条**带钥匙、自动过期**的临时公网链接（Cloudflare 反向隧道，需要 `cloudflared`），到期隧道与钥匙一起失效；`--stop` 立刻断开。

## 全部本地部署（不依赖任何云服务）

| 能力 | 本机方案 | 怎么起 | 云上替代 |
| --- | --- | --- | --- |
| 文字整理 | 内置规则，本来就离线 | — | — |
| 拍照识别 | `tools/ocr_server.py`（RapidOCR / PaddleOCR，CPU 可跑） | `pip install rapidocr-onnxruntime` → `python3 tools/ocr_server.py --port 8788` → `config.json` 填 `recognize.local.url` | 百度手写文字识别 |
| 视觉兜底 / 精批 | 本机视觉模型（Ollama） | `ollama pull qwen2.5-vl:7b` → `recognize.vision.base_url=http://127.0.0.1:11434/v1`，`model=qwen2.5-vl:7b`，`token_env` 留空 | 任意 OpenAI 兼容视觉模型 |
| 朗读 | ① **系统自带语音（默认，零配置、不联网）** ② 本机 CosyVoice2 ③ 任意 OpenAI 兼容 TTS（Kokoro-FastAPI 等） ④ 本机命令行 TTS（piper / say / edge-tts） | 见下面四条 | 音色克隆创空间 |
| 变速不变调 | ffmpeg | `sudo apt install ffmpeg` / `brew install ffmpeg`；不装也能用，只是没有三档语速 | — |
| 记录 / 错题本 / 评估 | 内置 SQLite，本来就离线 | — | — |

### 朗读的四种选法（默认就已经能用）

**⓪ 系统自带语音（默认）**：什么都不用装、不用配。Windows 走 SAPI、macOS 走 `say`、Linux 走 `espeak-ng`（Windows / macOS 会自动挑中文音色，例如 Microsoft Huihui、Tingting）。想指定音色或语速：`voice.system.voice` / `voice.system.rate`。

**① 本机跑 CosyVoice2（能复刻音色，最接近"用我自己的声音念"）**

```bash
git clone https://github.com/FunAudioLLM/CosyVoice && cd CosyVoice
pip install -r requirements.txt
python webui.py --port 50000          # 先在网页上点一次「3s极速复刻」跑通
```

`config.json`：`voice.engine=gradio`、`studio=http://127.0.0.1:50000`、`ref_wav=voices/my-voice.wav`、`prompt_text` 填参考录音念的原文、`token_env` 留空（本机地址不校验令牌）；`fn_index` 按你本机网页上的按钮顺序调（官方 webui 默认 1）。

**② 任意 OpenAI 兼容语音服务（最省事）**

```bash
docker run -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu        # 或 openedai-speech 等
```

`config.json`：`voice.engine=openai`、`voice.openai.base_url=http://127.0.0.1:8880/v1`、`voice` 填服务里的音色名。

**③ 本机命令行 TTS（最轻，piper 纯离线）**

```bash
pip install piper-tts                 # 再下个中文模型：zh_CN-huayan-medium.onnx
```

`config.json`：

```json
"command": {
  "argv": ["piper", "--model", "/path/zh_CN-huayan-medium.onnx", "--output_file", "{out}"],
  "stdin": true, "ext": ".wav"
}
```

`{text}` / `{out}` 会被替换成文本与输出路径；`stdin: true` 表示文字从标准输入喂进去（piper 是这样）；`edge-tts` 这类把文字当参数的写法去掉 `stdin` 即可。注意 edge-tts 走微软在线服务，不算离线。

### 本机能力自测（不联网、不需要任何密钥）

```bash
python3 test/test_local.py     # 起假的本机 OCR / 语音服务，验证三条本机通道真的能用
```

## 配置（`config.json`）

| 区块 | 说明 |
| --- | --- |
| `server` | 监听地址与端口 |
| `access` | 可选的固定访问口令（默认关闭）；公网临时链接一律要求钥匙，不需要这个 |
| `voice` | `engine`（gradio / openai / command）+ 各引擎参数、`speeds`（三档语速倍率）、`phrase`（朗读话术） |
| `recognize` | `chain`（识别顺序，没配的自动跳过：`local` 本机 OCR、`baidu` 手写识别、`vision` 视觉模型）+ 各通道参数 |
| `play` | 节奏停顿秒数、两遍之间的间隔、默认语速 |

识别与语音都可留空：什么都不配也能跑「手动输入 + 手动核对」。

## 隐私

- 数据全在本机：`data/moxie.db`（记录）、`data/results/`（答案照片）、`cache/`（合成语音）、`data/secrets.env`（凭据）；`data/`、`cache/`、`voice/*.wav` 都在 `.gitignore` 里，**不会进仓库**；
- 全本机方案下，照片、文字、语音都不出机器；
- 公网访问走反向隧道，家里不开任何入站端口；临时链接**带一次性钥匙、到时自动过期**，没有钥匙连静态文件都取不到。

## 目录

```
server.py            启动入口
config.json          全部可调参数
core/
  webapp.py          极简 Web 骨架（路由 / 静态文件 / 功能注册 / 访问口令）
  api.py             通用接口（识别、朗读方案、语音缓存、清单存档）
  textclean.py       文字整理（中英文）
  speech.py          朗读稿（念两遍、数字读法、纠音、切片）
  tts.py             语音合成 + 缓存 + 变速（三种引擎，都可本机）
  recognize.py       拍照识别（本机 OCR / 手写识别 / 视觉模型，可自动降级）
  grading.py         批改：对齐 + 判定 + 差异
  history.py         档案：轮次/条目/批改/错题本/统计（SQLite）
  records_api.py     档案接口
  store.py           设置与清单存档
features/moxie/      默写功能（META + 路由 + 前端页面）
features/<id>/       加新学习功能：复制一份改个名，注册进 features/__init__.py
tools/ocr_server.py  本机 OCR 服务（离线识别）
voices/              放你自己的音色录音（只在本机，不进仓库）
test/                自测（含 test_local.py 本机通道自测）
tunnel.py            临时公网链接（带钥匙、自动过期）
```

## 自测

```bash
python3 test/test_text.py      # 文字整理与朗读稿（离线）
python3 test/test_local.py     # 本机 OCR / 本机语音通道（离线，用假服务）
python3 test/test_access.py    # 访问口令与暴露面
python3 test/test_api.py       # 起服务 + 真识别 + 真合成（需联网与凭据）
python3 test/test_records.py   # 记录/批改/复核/错题本/统计（识别部分需联网与凭据）
```

## 想加别的学习功能

`features/` 下一个目录就是一个功能：元信息（名字/图标/入口页）+ 自己的路由 + 自己的前端页面。
语音合成、拍照识别、清单存档是所有功能共用的接口，新功能不用重复实现。

## License

MIT
