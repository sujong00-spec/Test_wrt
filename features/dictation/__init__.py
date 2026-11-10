"""한국어 받아쓰기 화면."""
from pathlib import Path
META = {'id': 'dictation', 'name': '한글 받아쓰기', 'desc': '듣고 쓰고, 함께 확인해요.', 'entry': '/f/dictation/', 'page': str(Path(__file__).parent / 'web' / 'index.html')}
STATICS = [('/f/dictation/', Path(__file__).parent / 'web')]
