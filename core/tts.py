"""语音合成：把文字合成为音频（默认用你自己的音色复刻，也可以全本机跑）。

四种引擎，`config.json` 的 `voice.engine` 选一个：

  - system ：**默认**，用系统自带语音（Windows SAPI / macOS say / Linux espeak-ng），零配置、不联网、
             不需要任何参考录音；Windows 与 macOS 上会自动挑中文音色
  - gradio ：音色克隆服务（3 秒极速复刻）。可以是云上的创空间，**也可以是本机跑的 CosyVoice2**
             （本机 Gradio 接口与云上一致，只改 `voice.studio` 地址）；参考录音放在 `voices/` 目录里
  - openai ：任意 OpenAI 兼容的语音接口（本机 Kokoro-FastAPI / openedai-speech / 各类本地 TTS 服务）
  - command：本机命令行 TTS（piper / edge-tts / say …），把文字和输出路径当参数传进去

参考录音、音色服务都跟代码分开：录音只放本机 `voices/` 目录（不入库），换音色只改 config.json。

要点：
  - 合成结果按「文本 + 语速 + 音色」缓存到磁盘，同一句永远只合成一次
  - 语速用变速不变调的方式处理（atempo），孩子听到的音高不变
  - 后台队列：一次要练十几条时并行合成，页面轮询进度
"""

import hashlib
import json
import os
import queue
import shlex
import shutil
import subprocess
import threading
import time
import urllib.request as ur
import uuid
from pathlib import Path

FFMPEG_CANDIDATES = [
    '/usr/bin/ffmpeg',
    '/usr/local/bin/ffmpeg',
    '/opt/homebrew/bin/ffmpeg',
]


def find_ffmpeg(extra=None):
    """按 FFMPEG_PATH → PATH → 常见安装位置 的顺序找 ffmpeg。"""
    if extra:
        return extra if Path(extra).exists() else None
    env = os.environ.get('FFMPEG_PATH')
    if env and Path(env).exists():
        return env
    found = shutil.which('ffmpeg')
    if found:
        return found
    for p in FFMPEG_CANDIDATES:
        if Path(p).exists():
            return p
    return None


def is_local_url(url):
    """本机服务一般没有鉴权，不需要令牌。"""
    import re
    m = re.match(r'^https?://([^/:]+)', url or '')
    return bool(m) and m.group(1).lower() in ('127.0.0.1', 'localhost', '0.0.0.0', '::1',
                                              'host.docker.internal')


class VoiceError(Exception):
    pass


def system_tts_available():
    """系统里有没有自带语音（默认引擎靠它，开箱即用）。"""
    import platform
    if platform.system() == 'Darwin' or shutil.which('say'):
        return True
    if shutil.which('powershell.exe'):
        return True
    return bool(shutil.which('espeak-ng') or shutil.which('espeak') or shutil.which('pico2wave'))


class VoiceEngine:
    """封装语音合成；同一进程内多线程安全。"""

    def __init__(self, cfg, root):
        self.cfg = cfg
        self.root = Path(root)
        self.engine = (cfg.get('engine') or 'gradio').lower()
        if self.engine == 'cosyvoice2':          # 兼容旧写法
            self.engine = 'gradio'
        if self.engine not in ('system', 'gradio', 'openai', 'command'):
            raise VoiceError('未知的语音引擎：%s（可选 system / gradio / openai / command）' % self.engine)
        self.studio = (cfg.get('studio') or '').rstrip('/')
        self.mode = cfg.get('mode', '3s极速复刻')
        self.fn_index = int(cfg.get('fn_index', 1))
        self.prompt_text = cfg.get('prompt_text', '')
        self.ref_path = self.root / cfg['ref_wav'] if cfg.get('ref_wav') else None
        self.token = os.environ.get(cfg.get('token_env') or '', '')
        self.ffmpeg = find_ffmpeg()
        self.cache_dir = self.root / 'cache' / 'audio'
        self.raw_dir = self.root / 'cache' / 'raw'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._ref_uploaded = None
        self._status = {}
        self._last_error = ''
        self.voice_tag = self._voice_tag()
        self._queue = queue.Queue()
        self._workers = []
        for _ in range(max(1, int(cfg.get('workers', 3)))):
            t = threading.Thread(target=self._work_loop, daemon=True)
            t.start()
            self._workers.append(t)

    # ---------- 音色指纹 / 缓存键 ----------

    def _voice_tag(self):
        """音色指纹：换了引擎、参考音频或音色名，缓存键自动变，不会拿旧音色的音频糊上去。"""
        h = hashlib.md5()
        h.update(self.engine.encode())
        if self.engine == 'gradio':
            h.update((self.studio + '|' + self.prompt_text + '|' + str(self.mode)).encode())
            try:
                h.update(self.ref_path.read_bytes())
            except (OSError, TypeError):
                h.update(b'missing')
        elif self.engine == 'system':
            cfg = self.cfg.get('system', {}) or {}
            h.update((str(cfg.get('voice')) + '|' + str(cfg.get('rate'))).encode())
        elif self.engine == 'openai':
            cfg = self.cfg.get('openai', {}) or {}
            h.update((str(cfg.get('base_url')) + '|' + str(cfg.get('model')) + '|'
                      + str(cfg.get('voice'))).encode())
        else:
            cfg = self.cfg.get('command', {}) or {}
            h.update(json.dumps(cfg.get('argv') or cfg.get('cmd') or '', ensure_ascii=False).encode())
        return h.hexdigest()[:6]

    def key_of(self, text, speed='normal'):
        raw = speed + '\u0001' + self.voice_tag + '\u0001' + text
        return hashlib.md5(raw.encode('utf-8')).hexdigest()[:24]

    def path_of(self, text, speed='normal'):
        return self.cache_dir / (self.key_of(text, speed) + '.mp3')

    def ready(self, text, speed='normal'):
        p = self.path_of(text, speed)
        return p.exists() and p.stat().st_size > 0

    def ensure(self, texts, speed='normal'):
        """把还没合成的文本排进队列；返回 (ready, pending)。"""
        ready = pending = 0
        for t in texts:
            t = (t or '').strip()
            if not t:
                continue
            k = self.key_of(t, speed)
            if self.ready(t, speed):
                ready += 1
                continue
            with self._lock:
                st = self._status.get(k)
                if st in ('pending', 'running'):
                    pending += 1
                    continue
                self._status[k] = 'pending'
            self._queue.put((t, speed, k))
            pending += 1
        return ready, pending

    def status(self, texts, speed='normal'):
        out = {}
        for t in texts:
            t = (t or '').strip()
            if not t:
                continue
            k = self.key_of(t, speed)
            if self.ready(t, speed):
                out[k] = 'ready'
            else:
                with self._lock:
                    out[k] = self._status.get(k, 'none')
        return out

    def available(self):
        """当前引擎配好了没有（页面用它决定要不要提示「还没配语音通道」）。"""
        if self.engine == 'system':
            return system_tts_available()
        if self.engine == 'gradio':
            return bool(self.studio) and (bool(self.token) or is_local_url(self.studio)) \
                and bool(self.ref_path and self.ref_path.exists())
        if self.engine == 'openai':
            return bool((self.cfg.get('openai') or {}).get('base_url'))
        cfg = self.cfg.get('command') or {}
        return bool(cfg.get('argv') or cfg.get('cmd'))

    def failure_note(self):
        with self._lock:
            return self._last_error

    # ---------- 队列 ----------

    def _work_loop(self):
        while True:
            text, speed, key = self._queue.get()
            with self._lock:
                self._status[key] = 'running'
            try:
                self.synthesize(text, speed)
                with self._lock:
                    self._status[key] = 'ready'
                    self._last_error = ''
            except Exception as exc:  # noqa: BLE001 - 出错要让页面能显示原因
                with self._lock:
                    self._status[key] = 'failed'
                    self._last_error = str(exc)[:200]
            finally:
                self._queue.task_done()

    # ---------- 合成 ----------

    def synthesize(self, text, speed='normal', retries=3):
        dest = self.path_of(text, speed)
        if self.ready(text, speed):
            return dest
        raw = self.raw_dir / (hashlib.md5((self.voice_tag + text).encode('utf-8')).hexdigest()[:24]
                              + self.raw_ext())
        if not (raw.exists() and raw.stat().st_size > 1000):
            last = None
            for i in range(retries):
                try:
                    self._synth_raw(text, raw)
                    last = None
                    break
                except Exception as exc:  # noqa: BLE001
                    last = exc
                    time.sleep(1.5 * (i + 1))
            if last is not None:
                raise VoiceError(f'语音合成失败：{last}')
        self._to_speed(raw, dest, speed)
        if not self.audio_path(text, speed):
            raise VoiceError('音频写出失败')
        return self.audio_path(text, speed)

    def raw_ext(self):
        if self.engine == 'openai':
            return '.mp3'
        if self.engine == 'command':
            return (self.cfg.get('command', {}) or {}).get('ext', '.wav')
        return '.wav'      # system / gradio 都是 wav

    def _synth_raw(self, text, dest):
        if self.engine == 'system':
            self._synth_system(text, dest)
        elif self.engine == 'gradio':
            self._synth_gradio(text, dest)
        elif self.engine == 'system':
            cfg = self.cfg.get('system', {}) or {}
            h.update((str(cfg.get('voice')) + '|' + str(cfg.get('rate'))).encode())
        elif self.engine == 'openai':
            self._synth_openai(text, dest)
        else:
            self._synth_command(text, dest)

    # ---------- 引擎零：系统自带语音（默认，零配置） ----------

    def _synth_system(self, text, dest):
        """用系统自带 TTS 念：Windows SAPI / macOS say / Linux espeak-ng。

        不联网、不需要参考录音，Windows 与 macOS 上自动挑中文音色。
        """
        import platform
        scfg = self.cfg.get('system', {}) or {}
        voice = (scfg.get('voice') or '').strip()
        rate = int(scfg.get('rate', 0) or 0)          # -10~10，0 是正常语速
        system = platform.system()
        is_wsl = 'microsoft' in platform.uname().release.lower()

        if is_wsl and shutil.which('powershell.exe'):
            return self._system_windows(text, dest, voice, rate)
        if system == 'Darwin' or shutil.which('say'):
            cmd = ['say', '--file-format=WAVE', '--data-format=LEI16@22050', '-o', str(dest)]
            cmd += (['-v', voice] if voice else [])
            cmd.append(text)
            self._run(cmd)
            return
        if system == 'Windows' or shutil.which('powershell.exe'):
            return self._system_windows(text, dest, voice, rate)

        # Linux：espeak-ng / pico2wave / piper 依次尝试（都是离线）
        espeak = shutil.which('espeak-ng') or shutil.which('espeak')
        if espeak:
            self._run([espeak, '-v', voice or 'cmn', '-s', str(170 + rate * 10), '-w', str(dest), text])
            return
        pico = shutil.which('pico2wave')
        if pico:
            self._run([pico, '-w', str(dest), text])
            return
        raise VoiceError('系统里没有可用的语音合成：装一个 espeak-ng（sudo apt install espeak-ng）'
                         '或 piper，也可以把 voice.engine 改成 command / openai / gradio')

    def _system_windows(self, text, dest, voice, rate):
        """经 PowerShell 调 Windows 自带 SAPI；中文音色自动挑（如 Microsoft Huihui）。"""
        def win_path(p):
            try:
                out = subprocess.run(['wslpath', '-w', str(p)], capture_output=True, timeout=10)
                if out.returncode == 0 and out.stdout.strip():
                    return out.stdout.decode('utf-8', 'ignore').strip()
            except Exception:  # noqa: BLE001
                pass
            return str(p)

        txt = dest.with_suffix('.txt')
        txt.write_text(text, encoding='utf-8')
        ps1 = dest.with_suffix('.ps1')
        ps1.write_text(
            'Add-Type -AssemblyName System.Speech\n'
            '$s = New-Object System.Speech.Synthesis.SpeechSynthesizer\n'
            "$want = '%s'\n" % voice +
            "if ($want) { $s.SelectVoice($want) } else {\n"
            "  $zh = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'zh*' }"
            " | Select-Object -First 1\n"
            "  if ($zh) { $s.SelectVoice($zh.VoiceInfo.Name) }\n"
            "}\n"
            '$s.Rate = %d\n' % rate +
            "Set-Content -Path '%s' -Value $s.Voice.VoiceInfo.Name -Encoding UTF8\n" % win_path(dest.with_suffix('.voice')) +
            "$s.SetOutputToWaveFile('%s')\n" % win_path(dest) +
            "$s.Speak([System.IO.File]::ReadAllText('%s', [System.Text.Encoding]::UTF8))\n" % win_path(txt) +
            '$s.Dispose()\n',
            encoding='utf-8-sig')      # BOM：让 PowerShell 正确读中文
        p = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                            '-File', win_path(ps1)], capture_output=True, timeout=120)
        if p.returncode != 0 or not dest.exists():
            raise VoiceError('系统语音合成失败：' + (p.stderr.decode('utf-8', 'ignore')[-160:]
                                             or p.stdout.decode('utf-8', 'ignore')[-160:]))
        for tmp in (txt, ps1):
            try:
                tmp.unlink()
            except OSError:
                pass

    # ---------- 引擎一：音色克隆（Gradio，云上或本机） ----------

    def _synth_gradio(self, text, dest):
        if not self.studio:
            raise VoiceError('没有配置音色服务地址（voice.studio）')
        if not self.token and not is_local_url(self.studio):
            raise VoiceError('缺少语音服务令牌（环境变量 %s）' % self.cfg.get('token_env'))
        if not self.ref_path or not self.ref_path.exists():
            raise VoiceError('缺少参考录音：%s（把你的录音放进 voices/ 目录，或把 voice.engine 改回 system 用系统音色）' % self.ref_path)
        ref = self._upload_ref()
        session = uuid.uuid4().hex[:12]
        payload = {'data': [text, self.mode, self.prompt_text,
                            {'path': ref, 'meta': {'_type': 'gradio.FileData'}},
                            None, '', 0, False],
                   'fn_index': self.fn_index, 'session_hash': session}
        eid = self._join(payload)
        out = self._await(session, eid)
        if not out:
            raise VoiceError('语音服务没有返回音频')
        fd = out[0]
        path = fd.get('path') if isinstance(fd, dict) else str(fd)
        if not path:
            raise VoiceError('语音服务返回的文件路径为空')
        data = self._get(self.studio + '/file=' + path)
        dest.write_bytes(data)
        if dest.stat().st_size < 1000:
            raise VoiceError('返回的音频为空')

    def _upload_ref(self):
        with self._lock:
            if self._ref_uploaded:
                return self._ref_uploaded
        boundary = '----ms' + uuid.uuid4().hex
        content = self.ref_path.read_bytes()
        body = ('--%s\r\n' % boundary).encode()
        body += ('Content-Disposition: form-data; name="files"; filename="%s"\r\n'
                 % self.ref_path.name).encode()
        body += b'Content-Type: audio/wav\r\n\r\n' + content + b'\r\n'
        body += ('--%s--\r\n' % boundary).encode()
        data = self._open(self.studio + '/upload', data=body,
                          headers={'Content-Type': 'multipart/form-data; boundary=%s' % boundary})
        val = json.loads(data)[0]
        with self._lock:
            self._ref_uploaded = val
        return val

    def _join(self, payload):
        data = self._open(self.studio + '/queue/join', data=json.dumps(payload).encode(),
                          headers={'Content-Type': 'application/json'})
        return json.loads(data)['event_id']

    def _await(self, session, eid):
        for raw in self._open(self.studio + '/queue/data?session_hash=%s' % session, stream=True):
            line = raw.decode('utf-8', 'ignore').strip()
            if not line.startswith('data:'):
                continue
            try:
                obj = json.loads(line.split(':', 1)[1].strip())
            except Exception:  # noqa: BLE001
                continue
            if obj.get('event_id') and obj['event_id'] != eid:
                continue
            msg = obj.get('msg')
            if msg == 'process_completed':
                if not obj.get('success', True):
                    raise VoiceError('合成被拒绝：' + json.dumps(obj.get('output'), ensure_ascii=False)[:200])
                return obj['output']['data']
            if msg == 'process_failed':
                raise VoiceError('合成进程失败')
        raise VoiceError('连接中断')

    def _open(self, url, data=None, headers=None, stream=False, timeout=1800):
        h = {}
        if self.token:
            h['Authorization'] = 'Bearer ' + self.token
        h.update(headers or {})
        try:
            resp = ur.urlopen(ur.Request(url, data=data, headers=h), timeout=timeout)
            return resp if stream else resp.read()
        except ur.HTTPError as exc:
            raise VoiceError('语音服务返回 %s：%s' % (exc.code, exc.read()[:160].decode('utf-8', 'ignore')))

    def _get(self, url):
        return self._open(url)

    # ---------- 引擎二：OpenAI 兼容语音接口（本机 TTS 服务） ----------

    def _synth_openai(self, text, dest):
        cfg = self.cfg.get('openai', {}) or {}
        base = (cfg.get('base_url') or '').rstrip('/')
        if not base:
            raise VoiceError('没有配置本机语音服务地址（voice.openai.base_url）')
        token = os.environ.get(cfg.get('token_env') or '', '') if cfg.get('token_env') else ''
        body = {'model': cfg.get('model', 'tts-1'), 'input': text,
                'voice': cfg.get('voice', 'alloy'),
                'response_format': cfg.get('format', 'mp3'), 'speed': 1.0}
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        req = ur.Request(base + '/audio/speech', data=json.dumps(body).encode(), headers=headers)
        try:
            with ur.urlopen(req, timeout=int(cfg.get('timeout', 600))) as r:
                data = r.read()
        except ur.HTTPError as exc:
            raise VoiceError('本机语音服务返回 %s：%s' % (exc.code, exc.read()[:160].decode('utf-8', 'ignore')))
        except Exception as exc:  # noqa: BLE001
            raise VoiceError('连不上本机语音服务（%s）' % exc)
        dest.write_bytes(data)
        if dest.stat().st_size < 1000:
            raise VoiceError('本机语音服务返回了空音频')

    # ---------- 引擎三：本机命令行 TTS ----------

    def _synth_command(self, text, dest):
        cfg = self.cfg.get('command', {}) or {}
        argv = cfg.get('argv') or shlex.split(cfg.get('cmd') or '')
        if not argv:
            raise VoiceError('没有配置本机语音命令（voice.command.argv）')
        args = [str(a).replace('{text}', text).replace('{out}', str(dest)) for a in argv]
        stdin = text.encode('utf-8') if cfg.get('stdin') else None   # piper 这类从标准输入读文字
        try:
            p = subprocess.run(args, input=stdin, capture_output=True, timeout=int(cfg.get('timeout', 300)))
        except FileNotFoundError:
            raise VoiceError('找不到命令：%s' % args[0])
        except subprocess.TimeoutExpired:
            raise VoiceError('语音命令超时')
        if p.returncode != 0 or not dest.exists():
            raise VoiceError('语音命令失败：' + p.stderr.decode('utf-8', 'ignore')[-160:])
        if dest.stat().st_size < 1000:
            raise VoiceError('语音命令没有产出有效音频')

    # ---------- 变速 ----------

    def _to_speed(self, raw, dest, speed):
        """按语速生成成品文件；没有 ffmpeg 时就用原始音频。"""
        tempos = self.cfg.get('speeds', {})
        tempo = float(tempos.get(speed, 1.0) or 1.0)
        if not self.ffmpeg:
            alt = dest.with_suffix(raw.suffix)
            shutil.copyfile(raw, alt)
            return alt
        if abs(tempo - 1.0) < 0.001:
            self._run([self.ffmpeg, '-y', '-i', str(raw), '-ac', '1', '-ar', '24000',
                       '-b:a', '64k', str(dest)])
            return dest
        filters = []
        remaining = tempo
        while remaining > 2.0:
            filters.append('atempo=2.0')
            remaining /= 2.0
        while remaining < 0.5:
            filters.append('atempo=0.5')
            remaining /= 0.5
        filters.append('atempo=%.4f' % remaining)
        self._run([self.ffmpeg, '-y', '-i', str(raw), '-filter:a', ','.join(filters),
                   '-ac', '1', '-ar', '24000', '-b:a', '64k', str(dest)])
        return dest

    def _run(self, cmd):
        p = subprocess.run(cmd, capture_output=True)
        if p.returncode != 0:
            raise VoiceError('音频处理失败：' + p.stderr.decode('utf-8', 'ignore')[-200:])

    def audio_path(self, text, speed='normal'):
        p = self.path_of(text, speed)
        if p.exists():
            return p
        alt = p.with_suffix('.wav')
        if alt.exists():
            return alt
        alt = p.with_suffix('.mp3')
        if alt.exists():
            return alt
        return None
