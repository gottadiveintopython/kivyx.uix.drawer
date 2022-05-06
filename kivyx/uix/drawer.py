__all__ = ('KXDrawer', )

from functools import partial
from kivy.metrics import sp as metrics_sp
from kivy.properties import (
    NumericProperty, ColorProperty, OptionProperty, BooleanProperty,
)
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.widget import Widget

import asynckivy as ak

KV_CODE = '''
<KXDrawerTab>:
    canvas.before:
        Color:
            rgba: self.bg_color
        Rectangle:
            pos: self.pos
            size: self.size
    canvas:
        PushMatrix:
        Translate:
            xy: self.center
        Rotate:
            angle: self.icon_angle
        Color:
            rgba: self.fg_color
        Triangle:
            points: (s := min(*self.size) * 0.2, ) and (-s, -s, -s, s, s, 0)
        PopMatrix:

<KXDrawer>:
    canvas.before:
        Color:
            rgba: root.bg_color
        Rectangle:
            pos: 0, 0
            size: self.size
    KXDrawerTab:
        id: tab
        bg_color: root.bg_color
        fg_color: root.fg_color
'''
Builder.load_string(KV_CODE)


class KXDrawerTab(ButtonBehavior, Widget):
    bg_color = ColorProperty()
    fg_color = ColorProperty()
    icon_angle = NumericProperty(0)

    __ = {
        'l': {'x': 1, 'center_y': .5, },
        'r': {'right': 0, 'center_y': .5, },
        'b': {'y': 1, 'center_x': .5, },
        't': {'top': 0, 'center_x': .5, },
    }
    def update(self, anchor, __=__):
        anchor = anchor[0]
        tab_width = max(metrics_sp(15), 24)
        self.size = self.size_hint_min = (tab_width, tab_width, )
        self.size_hint = (.4, None) if anchor in 'tb' else (None, .4)
        self.pos_hint = __[anchor].copy()
    del __


class KXDrawer(RelativeLayout):
    __events__ = ('on_pre_open', 'on_open', 'on_pre_close', 'on_close', )

    auto_front = BooleanProperty(False)
    '''If True, moves the drawer on top of the other siblings when it's opened.'''

    anim_duration = NumericProperty(.3)
    '''Duration of the opening/closing animations.'''

    bg_color = ColorProperty("#222222")

    fg_color = ColorProperty("#AAAAAA")
    '''The color of the triangle drawn on the tab'''

    anchor = OptionProperty('lm', options=r'lt lm lb rt rm rb bl bm br tl tm tr'.split())
    '''親のどの位置にくっつくか

        'l' stands for 'left'.
        'r' stands for 'right'.
        't' stands for 'top'.
        'b' stands for 'bottom'.
        'm' stands for 'middle'.
    '''

    def __init__(self, **kwargs):
        self._open_request = ak.Event()
        self._close_request = ak.Event()
        self._main_task = ak.dummy_task
        super().__init__(**kwargs)
        self._trigger_restart = t = Clock.create_trigger(self._restart)
        self.fbind('anchor', t)
        self.bind(parent=t)
        t()

    def _restart(self, dt):
        self._main_task.cancel()
        self._main_task = ak.start(self._main())

    async def _main(self):
        import asynckivy as ak

        parent = self.parent
        if parent is None:
            return
        if not isinstance(parent, FloatLayout):
            raise ValueError("KXDrawer must belong to FloatLayout (or subclass thereof)!!")

        anchor = self.anchor
        tab = self.ids.tab
        tab.update(anchor)
        self.pos_hint = self._get_initial_pos_hint(anchor)
        ph = self.pos_hint  # CAUTION: 上の行とまとめてはいけない
        # '_c'-suffix means 'close'.  '_o'-suffix means 'open'.
        icon_angle_c = self._get_initial_icon_angle(anchor)
        icon_angle_o = icon_angle_c + 180.
        pos_key_o, pos_key_c = self._get_poskeys(anchor)
        ph_value = 0. if anchor[0] in 'lb' else 1.
        tab.icon_angle = icon_angle_c
        ph[pos_key_c] = ph_value
        get_parent_pos = partial(self._get_parent_pos_in_local_coordinates, parent, pos_key_o, anchor[0] in 'tb')

        # 三角が回っている時にanchorが特定の値から特定の値に変わった場合に必要となる。(例: 'tm' -> 'bm', 'tr' -> 'br')
        # 原因はpos_hintに変化が起きずlayoutの再計算を引き起こさないから。
        parent._trigger_layout()

        while True:
            await ak.or_(ak.event(tab, 'on_press'), self._open_request.wait())
            self._open_request.clear()
            self.dispatch('on_pre_open')
            if self.auto_front:
                self.unbind(parent=self._trigger_restart)
                parent.remove_widget(self)
                parent.add_widget(self)
                self.bind(parent=self._trigger_restart)
            del ph[pos_key_c]
            await ak.animate(self, d=self.anim_duration, **{pos_key_o: get_parent_pos()})
            await ak.animate(tab, d=self.anim_duration, icon_angle=icon_angle_o)
            ph[pos_key_o] = ph_value
            self.dispatch('on_open')
            await ak.or_(ak.event(tab, 'on_press'), self._close_request.wait())
            self._close_request.clear()
            self.dispatch('on_pre_close')
            del ph[pos_key_o]
            await ak.animate(self, d=self.anim_duration, **{pos_key_c: get_parent_pos()})
            await ak.animate(tab, d=self.anim_duration, icon_angle=icon_angle_c)
            ph[pos_key_c] = ph_value
            self.dispatch('on_close')

    def open(self, *unused_args, **unused_kwargs):
        self._close_request.clear()
        self._open_request.set()

    def close(self, *unused_args, **unused_kwargs):
        self._open_request.clear()
        self._close_request.set()

    def on_pre_open(self):
        pass

    def on_open(self):
        pass

    def on_pre_close(self):
        pass

    def on_close(self):
        pass

    @staticmethod
    def _get_parent_pos_in_local_coordinates(parent, pos_key, vertical: bool):
        return getattr(parent, pos_key) + parent.to_local(0, 0)[vertical]

    __ = {
        'l': ('x', 'right'),
        't': ('top', 'y'),
        'r': ('right', 'x'),
        'b': ('y', 'top'),
    }
    @staticmethod
    def _get_poskeys(anchor, *, __=__):
        return __[anchor[0]]

    __ = {
        'bl': {'x': 0., },
        'tl': {'x': 0., },
        'lb': {'y': 0., },
        'rb': {'y': 0., },
        'bm': {'center_x': .5, },
        'tm': {'center_x': .5, },
        'rm': {'center_y': .5, },
        'lm': {'center_y': .5, },
        'br': {'right': 1., },
        'tr': {'right': 1., },
        'lt': {'top': 1., },
        'rt': {'top': 1., },
    }
    @staticmethod
    def _get_initial_pos_hint(anchor, *, __=__):
        return __[anchor].copy()

    __ = {'l': 0., 't': 270., 'r': 180., 'b': 90., }
    @staticmethod
    def _get_initial_icon_angle(anchor, *, __=__):
        return __[anchor[0]]

    del __
