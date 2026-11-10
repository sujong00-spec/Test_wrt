"""已安装的学习功能清单。

加一个新功能：在本目录下新建包（照抄 moxie 的结构），把包名加到 FEATURES 里即可。
"""

FEATURES = ['dictation']


def load(app):
    import importlib

    for name in FEATURES:
        app.add_feature(importlib.import_module('features.%s' % name))
    return app
