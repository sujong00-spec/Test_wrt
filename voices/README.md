# 音色录音放这里（本目录不进仓库）

**默认不需要放任何东西**：`config.json` 里 `voice.engine` 是 `system`，用系统自带语音念（Windows SAPI / macOS say / Linux espeak-ng），零配置、不联网。

想换成**自己的声音**（音色克隆），在这个目录放一段参考录音：

1. 录 3~8 秒**纯中文**（别夹英文单词，参考段读糊了会带坏音色），安静环境、单声道、16k wav 就行；
2. 放进本目录，例如 `voices/my-voice.wav`；
3. 改 `config.json`：
   - `voice.engine` 改成 `gradio`（音色克隆服务，可以是云上创空间或本机 CosyVoice2）
   - `voice.ref_wav` 指向 `voices/my-voice.wav`
   - `voice.prompt_text` 填**这段录音念的原文**，必须逐字一致，否则音色会跑偏
4. 重启服务，第一次念新内容时自动合成并缓存。

想放几段不同的录音就放几个文件，换音色只是改一行 `ref_wav`；缓存键带音色指纹，换录音不会串音。

本目录只在本机：`.gitignore` 里只保留本文件，`voices/` 下的录音、以及 `cache/` 里的合成音频都不会进仓库。
