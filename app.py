"""G Capture — local Windows screen capture and annotation."""
import datetime as dt
import queue
import sys
from copy import deepcopy
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, colorchooser
from PIL import Image, ImageTk, ImageDraw
from annotations import Annotation, composite
import windows
from imaging import stitch
from settings import DEFAULT_SHORTCUTS, KEYS, load_shortcuts, save_shortcuts, validate
from desktop import Tray, set_startup, startup_enabled

BG = '#101722'
PANEL = '#182332'
TEXT = '#e7edf5'
ACCENT = '#58d5b2'


class Selection(tk.Toplevel):
    def __init__(self, parent, mode, callback, size):
        super().__init__(parent)
        self.mode, self.callback, self.size = mode, callback, size
        self.x, self.y, width, height = windows.desktop_bounds()
        self.shot = windows.grab()
        self.overrideredirect(True)
        self.geometry(f'{width}x{height}+0+0')
        self.attributes('-topmost', True)
        self.canvas = tk.Canvas(self, highlightthickness=0, cursor='crosshair')
        self.canvas.pack(fill='both', expand=True)
        self.photo = ImageTk.PhotoImage(self.shot)
        self.canvas.create_image(0, 0, anchor='nw', image=self.photo)
        self.canvas.create_rectangle(12, 12, 700, 54, fill=BG, outline=ACCENT)
        self.canvas.create_text(28, 33, anchor='w', fill='white', font=('Segoe UI', 12),
                                text='Click to place' if mode == 'Fixed size' else 'Drag to select • Esc to cancel')
        self.start = None
        self.points = []
        self.bind('<Escape>', lambda e: self.finish(None, None))
        self.canvas.bind('<ButtonPress-1>', self.down)
        self.canvas.bind('<B1-Motion>', self.move)
        self.canvas.bind('<ButtonRelease-1>', self.up)
        windows.position_overlay(self, self.x, self.y, width, height)
        self.focus_force()
        self.grab_set()

    def down(self, e):
        self.start = (e.x, e.y)
        self.points = [self.start]

    def move(self, e):
        if self.start is None:
            return
        self.canvas.delete('selection')
        if self.mode == 'Freehand':
            self.points.append((e.x, e.y))
            if len(self.points) > 1:
                self.canvas.create_line(self.points, fill=ACCENT, width=2, tags='selection')
        else:
            self.canvas.create_rectangle(*self.start, e.x, e.y, outline=ACCENT, width=2, tags='selection')
            self.canvas.create_text(e.x+8, e.y+15, anchor='w', text=f'{abs(e.x-self.start[0])} × {abs(e.y-self.start[1])}', fill='white', tags='selection')

    def up(self, e):
        if self.start is None:
            return
        if self.mode == 'Fixed size':
            w, h = self.size
            left = min(max(0, e.x), max(0, self.shot.width-w))
            top = min(max(0, e.y), max(0, self.shot.height-h))
            box = (left, top, min(self.shot.width, left+w), min(self.shot.height, top+h))
        elif self.mode == 'Freehand':
            self.points.append((e.x, e.y))
            if len(self.points) < 3:
                return self.finish(None, None)
            xs, ys = zip(*self.points)
            box = (min(xs), min(ys), max(xs), max(ys))
        else:
            box = (min(self.start[0], e.x), min(self.start[1], e.y), max(self.start[0], e.x), max(self.start[1], e.y))
        box = (max(0, box[0]), max(0, box[1]), min(self.shot.width, box[2]), min(self.shot.height, box[3]))
        if box[2]-box[0] < 2 or box[3]-box[1] < 2:
            return self.finish(None, None)
        result = self.shot.crop(box)
        if self.mode == 'Freehand':
            mask = Image.new('L', self.shot.size)
            ImageDraw.Draw(mask).polygon(self.points, fill=255)
            result = result.convert('RGBA')
            result.putalpha(mask.crop(box))
        absolute = (box[0]+self.x, box[1]+self.y, box[2]+self.x, box[3]+self.y)
        self.finish(result, absolute)

    def finish(self, image, box):
        self.grab_release()
        self.destroy()
        self.callback(image, box)


class App(tk.Tk):
    def __init__(self, start_in_tray=False):
        super().__init__()
        self.title('G Capture')
        icon = str(Path(__file__).resolve().parent / 'assets' / 'capture-studio.ico')
        self.iconbitmap(icon, default=icon)
        self.geometry('1280x820')
        self.minsize(940, 640)
        self.configure(bg=BG)
        self.image = None
        self.base_image = None
        self.annotations = []
        self.selected = None
        self.drag_original = None
        self.undo_stack, self.redo_stack, self.history = [], [], []
        self.busy = False
        self.shortcut_dialog = None
        self.shortcuts = load_shortcuts()
        self.shortcut_summary = tk.StringVar()
        self.dirty = False
        self.scale = 1.0
        self.color = '#ff535f'
        self.tool = tk.StringVar(value='Pen')
        self.stroke = tk.IntVar(value=4)
        self.font_size = tk.IntVar(value=24)
        self.delay = tk.IntVar(value=0)
        self.fixed_w, self.fixed_h = tk.IntVar(value=800), tk.IntVar(value=600)
        self.zoom = tk.StringVar(value='Fit')
        self.status = tk.StringVar(value='Ready • Everything stays on your computer')
        self.build_ui()
        self.bind('<Control-z>', lambda e: self.undo())
        self.bind('<Control-y>', lambda e: self.redo())
        self.bind('<Control-s>', lambda e: self.save())
        self.bind('<Control-c>', lambda e: self.copy())
        self.bind('<Control-o>', lambda e: self.open_image())
        self.protocol('WM_DELETE_WINDOW', self.close)
        failed = windows.hotkeys(shortcuts=self.shortcuts)
        self.update_shortcut_summary(failed)
        if failed:
            self.status.set('Some global shortcuts are in use. Capture buttons remain available.')
        self.poll_timer = self.after(100, self.poll)
        self.tray = None
        try:
            self.tray = Tray()
        except Exception as exc:
            self.status.set(f'System tray unavailable: {exc}')
        if start_in_tray and self.tray is not None:
            self.withdraw()

    def button(self, parent, text, command, accent=False):
        return tk.Button(parent, text=text, command=command, bg=ACCENT if accent else PANEL,
                         fg=BG if accent else TEXT, activebackground='#2b4854', activeforeground='white',
                         relief='flat', bd=0, padx=14, pady=9, cursor='hand2', font=('Segoe UI', 10))

    def label(self, parent, text, **kwargs):
        return tk.Label(parent, text=text, bg=BG, fg=TEXT, font=('Segoe UI', 10), **kwargs)

    def build_ui(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        top = tk.Frame(self, bg=BG, padx=22, pady=16)
        top.pack(fill='x')
        tk.Label(top, text='G Capture', font=('Segoe UI', 22, 'bold'), bg=BG, fg=TEXT).pack(side='left')
        self.label(top, '  /  Capture. Annotate. Share.').pack(side='left')
        for text, command in [('Save as…', self.save), ('Copy image', self.copy), ('Open…', self.open_image)]:
            self.button(top, text, command, text == 'Save as…').pack(side='right', padx=4)
        captures = tk.Frame(self, bg=BG, padx=22)
        captures.pack(fill='x')
        for name in ['Region', 'Freehand', 'Window', 'Control', 'Full screen', 'Fixed size', 'Scrolling']:
            self.button(captures, name, lambda m=name: self.capture(m), name == 'Region').pack(side='left', padx=(0, 6))
        options = tk.Frame(self, bg=BG, padx=22, pady=10)
        options.pack(fill='x')
        self.label(options, 'Delay (s)').pack(side='left')
        tk.Spinbox(options, from_=0, to=30, textvariable=self.delay, width=4).pack(side='left', padx=8)
        self.label(options, 'Fixed size').pack(side='left')
        tk.Spinbox(options, from_=10, to=10000, textvariable=self.fixed_w, width=6).pack(side='left', padx=8)
        self.label(options, '×').pack(side='left')
        tk.Spinbox(options, from_=10, to=10000, textvariable=self.fixed_h, width=6).pack(side='left', padx=8)
        self.button(options, 'Shortcuts…', self.show_shortcuts).pack(side='right')
        shortcut_bar = tk.Frame(self, bg=BG, padx=22)
        shortcut_bar.pack(fill='x')
        tk.Label(shortcut_bar, textvariable=self.shortcut_summary, bg=BG, fg='#a6b7cc', anchor='w').pack(fill='x', pady=(0, 8))
        body = tk.Frame(self, bg=BG, padx=22)
        body.pack(fill='both', expand=True)
        sidebar = tk.Frame(body, bg=BG, width=155)
        sidebar.pack(side='left', fill='y', padx=(0, 16))
        self.label(sidebar, 'EDIT TOOLS').pack(anchor='w', pady=(8, 10))
        for tool in ['Select', 'Pen', 'Highlighter', 'Arrow', 'Rectangle', 'Ellipse', 'Text', 'Mosaic', 'Crop']:
            tk.Radiobutton(sidebar, text=tool, variable=self.tool, value=tool, indicatoron=False,
                           bg=PANEL, fg=TEXT, selectcolor='#28554f', activebackground='#28554f',
                           activeforeground='white', relief='flat', width=14, pady=4, command=self.tool_changed).pack(fill='x', pady=2)
        self.button(sidebar, '●  Color', self.choose_color).pack(fill='x', pady=(12, 4))
        self.label(sidebar, 'Stroke width').pack(anchor='w')
        tk.Spinbox(sidebar, from_=1, to=40, textvariable=self.stroke, width=6).pack(fill='x', pady=6)
        self.button(sidebar, 'Undo  Ctrl+Z', self.undo).pack(fill='x', pady=2)
        self.button(sidebar, 'Redo  Ctrl+Y', self.redo).pack(fill='x', pady=2)
        center = tk.Frame(body, bg=PANEL)
        center.pack(side='left', fill='both', expand=True)
        toolbar = tk.Frame(center, bg=PANEL)
        toolbar.pack(fill='x')
        tk.Label(toolbar, text='CANVAS', fg='#98a9bf', bg=PANEL, padx=12, pady=9).pack(side='left')
        tk.Label(toolbar, text='Font size', bg=PANEL, fg=TEXT).pack(side='left')
        tk.Spinbox(toolbar, from_=6, to=300, textvariable=self.font_size, width=5).pack(side='left')
        self.button(toolbar, 'Apply style', self.apply_style).pack(side='left', padx=4)
        self.button(toolbar, 'Edit text', self.edit_text).pack(side='left')
        self.button(toolbar, 'Delete', self.delete_annotation).pack(side='left', padx=4)
        zoom = ttk.Combobox(toolbar, textvariable=self.zoom, values=['Fit', '25%', '50%', '100%', '150%', '200%'], state='readonly', width=7)
        zoom.pack(side='right', padx=8)
        zoom.bind('<<ComboboxSelected>>', lambda e: self.render())
        area = tk.Frame(center, bg=PANEL)
        area.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(area, bg='#0b111b', highlightthickness=0)
        vscroll = ttk.Scrollbar(area, orient='vertical', command=self.canvas.yview)
        hscroll = ttk.Scrollbar(area, orient='horizontal', command=self.canvas.xview)
        self.canvas.configure(xscrollcommand=hscroll.set, yscrollcommand=vscroll.set)
        vscroll.pack(side='right', fill='y')
        hscroll.pack(side='bottom', fill='x')
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda e: self.render())
        self.canvas.bind('<ButtonPress-1>', self.edit_start)
        self.canvas.bind('<B1-Motion>', self.edit_move)
        self.canvas.bind('<ButtonRelease-1>', self.edit_end)
        self.canvas.bind('<Double-Button-1>', lambda e: self.edit_text())
        self.canvas.bind('<Delete>', lambda e: self.delete_annotation())
        self.canvas.bind('<MouseWheel>', lambda e: self.canvas.yview_scroll(-int(e.delta/120)*3, 'units'))
        history_panel = tk.Frame(body, bg=BG)
        history_panel.pack(side='right', fill='y', padx=(14, 0))
        self.label(history_panel, 'RECENT CAPTURES').pack(anchor='w', pady=10)
        self.history_list = tk.Listbox(history_panel, bg=PANEL, fg=TEXT, selectbackground='#28554f',
                                      bd=0, highlightthickness=0, width=22, font=('Segoe UI', 10))
        self.history_list.pack(fill='both', expand=True)
        self.history_list.bind('<<ListboxSelect>>', self.restore_history)
        self.button(history_panel, 'Clear history', self.clear_history).pack(fill='x')
        tk.Label(self, textvariable=self.status, bg=BG, fg='#a6b7cc', anchor='w', padx=22, pady=12).pack(fill='x')

    def update_shortcut_summary(self, failed=()):
        self.shortcut_summary.set('   |   '.join(
            f'{mode}: {self.shortcuts[key]}' + (' (unavailable)' if int(key) in failed else '')
            for key, mode in [('1', 'Region'), ('2', 'Full screen'), ('3', 'Window')]))

    def apply_shortcuts(self, candidate):
        candidate = validate(candidate)
        previous = self.shortcuts.copy()
        failed = windows.hotkeys(shortcuts=candidate)
        if failed:
            restored_failed = windows.hotkeys(shortcuts=previous)
            self.update_shortcut_summary(restored_failed)
            names = ', '.join(candidate[str(key)] for key in failed)
            raise ValueError(f'Windows could not register: {names}. Another app or Windows may be using it.\n\n'
                             'For Print Screen, check Windows Settings > Accessibility > Keyboard and turn off '
                             'the option to open screen capture with Print Screen, then try again. '
                             'Your previous preferences were kept.')
        try:
            save_shortcuts(candidate)
        except OSError:
            restored_failed = windows.hotkeys(shortcuts=previous)
            self.update_shortcut_summary(restored_failed)
            raise
        self.shortcuts = candidate
        self.update_shortcut_summary()
        self.status.set('Capture shortcuts saved. They work while G Capture is running, including when minimized.')

    def show_shortcuts(self):
        if self.shortcut_dialog is not None:
            self.shortcut_dialog.lift()
            return
        dialog = tk.Toplevel(self)
        self.shortcut_dialog = dialog
        dialog.title('Capture shortcuts')
        dialog.configure(bg=BG, padx=22, pady=18)
        dialog.resizable(False, False)
        dialog.transient(self)
        rows = {}
        self.label(dialog, 'Choose a global shortcut for each capture mode.').grid(row=0, column=0, columnspan=5, pady=(0, 16), sticky='w')
        for row, (identifier, mode) in enumerate([('1', 'Region'), ('2', 'Full screen'), ('3', 'Window')], 1):
            self.label(dialog, mode).grid(row=row, column=0, sticky='w', padx=(0, 16), pady=8)
            parts = self.shortcuts[identifier].split('+')
            key = tk.StringVar(value=parts[-1])
            modifiers = {}
            for column, modifier in enumerate(['Ctrl', 'Alt', 'Shift'], 1):
                value = tk.BooleanVar(value=modifier in parts[:-1])
                modifiers[modifier] = value
                tk.Checkbutton(dialog, text=modifier, variable=value, bg=BG, fg=TEXT,
                               selectcolor=PANEL, activebackground=BG, activeforeground=TEXT).grid(row=row, column=column)
            ttk.Combobox(dialog, textvariable=key, values=['Disabled'] + KEYS, state='readonly', width=16).grid(row=row, column=4, padx=8)
            rows[identifier] = (key, modifiers)
        self.label(dialog, 'Print Screen alone is supported. Letters/numbers require a modifier.\n'
                           'If Windows opens its snipping tool, disable the Print Screen option\n'
                           'under Windows Settings > Accessibility > Keyboard.').grid(row=4, column=0, columnspan=5, sticky='w', pady=16)

        def close_dialog():
            dialog.grab_release()
            self.shortcut_dialog = None
            dialog.destroy()

        def apply():
            candidate = {identifier: ('Disabled' if key.get() == 'Disabled' else '+'.join(
                [name for name, value in modifiers.items() if value.get()] + [key.get()]))
                for identifier, (key, modifiers) in rows.items()}
            try:
                self.apply_shortcuts(candidate)
            except (ValueError, OSError) as error:
                messagebox.showerror('Shortcut not saved', str(error), parent=dialog)
                return
            close_dialog()

        def defaults():
            for identifier, (key, modifiers) in rows.items():
                parts = DEFAULT_SHORTCUTS[identifier].split('+')
                key.set(parts[-1])
                for name, value in modifiers.items():
                    value.set(name in parts[:-1])

        actions = tk.Frame(dialog, bg=BG)
        actions.grid(row=5, column=0, columnspan=5, sticky='ew')
        self.button(actions, 'Reset defaults', defaults).pack(side='left')
        self.button(actions, 'Save', apply, True).pack(side='right', padx=(8, 0))
        self.button(actions, 'Cancel', close_dialog).pack(side='right')
        dialog.protocol('WM_DELETE_WINDOW', close_dialog)
        dialog.bind('<Escape>', lambda e: close_dialog())
        dialog.grab_set()

    def safe(self, action):
        try:
            return action()
        except Exception as error:
            messagebox.showerror('G Capture', str(error), parent=self)

    def capture(self, mode):
        if self.busy:
            return
        try:
            delay = max(0, min(30, self.delay.get()))
            size = (self.fixed_w.get(), self.fixed_h.get())
            if min(size) < 2:
                raise ValueError()
        except (ValueError, tk.TclError):
            return messagebox.showerror('Invalid value', 'Enter valid positive dimensions and a delay from 0 to 30.')
        if mode in ('Window', 'Control'):
            self.status.set('Move the pointer over the target. Capture happens after at least 3 seconds.')
            delay = max(3, delay)
        self.busy = True
        self.withdraw()
        self.after(max(250, delay*1000), lambda: self.begin_capture(mode, size))

    def begin_capture(self, mode, size):
        try:
            if mode == 'Full screen':
                self.capture_done(windows.grab(), None)
            elif mode in ('Window', 'Control'):
                self.capture_done(windows.grab(windows.target_rect(mode == 'Window')), None)
            else:
                Selection(self, mode, self.start_scroll if mode == 'Scrolling' else self.capture_done, size)
        except Exception as error:
            self.capture_done(None, None)
            messagebox.showerror('Capture failed', str(error))

    def capture_done(self, image, box):
        self.busy = False
        if image is not None:
            self.deiconify()
            self.lift()
            self.set_image(image, add_history=True)
            try:
                windows.copy_image(image)
                self.status.set('Capture copied to clipboard • Ctrl+V to paste')
            except Exception as error:
                self.status.set(f'Capture kept, but automatic copy failed: {error} Use Ctrl+C to retry.')

    def start_scroll(self, image, box):
        if image is None:
            return self.capture_done(None, None)
        if image.height < 80:
            self.capture_done(None, None)
            return messagebox.showerror('Region too small', 'Select a scrolling region at least 80 pixels tall.')
        self.scroll_image, self.scroll_box, self.scroll_count = image, box, 0
        # The overlay is gone; allow the target to repaint before the first wheel event.
        self.after(350, self.scroll_step)

    def scroll_step(self):
        if windows.escape_pressed() or self.scroll_count >= 20:
            return self.capture_done(self.scroll_image, None)
        windows.scroll_at(self.scroll_box)
        self.after(700, self.scroll_collect)

    def scroll_collect(self):
        try:
            frame = windows.grab(self.scroll_box)
            self.scroll_image, added = stitch(self.scroll_image, frame)
            self.scroll_count += 1
            if added == 0 or windows.escape_pressed():
                self.capture_done(self.scroll_image, None)
            else:
                self.after(100, self.scroll_step)
        except Exception as error:
            self.capture_done(self.scroll_image, None)
            messagebox.showwarning('Scrolling stopped — partial capture kept', str(error))

    def set_image(self, image, add_history=False):
        self.base_image = image.copy()
        self.image = image.copy()
        self.annotations = []
        self.selected = None
        self.editing = False
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.dirty = True
        self.zoom.set('Fit')
        if add_history:
            name = dt.datetime.now().strftime('%H:%M:%S') + f'  {image.width} × {image.height}'
            self.history.insert(0, (name, image.copy()))
            self.history = self.history[:10]
            self.history_list.delete(0, 'end')
            for name, _ in self.history:
                self.history_list.insert('end', name)
        self.render()

    def render(self):
        self.canvas.delete('all')
        if self.image is None:
            w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
            self.canvas.create_text(w/2, h/2-30, text='Your next idea, captured.', fill=TEXT, font=('Segoe UI', 24, 'bold'))
            self.canvas.create_text(w/2, h/2+18, text='Choose a capture mode above, or open an image.\n\nScrolling capture: select content, then press Esc to stop.', justify='center', fill='#8295ad', font=('Segoe UI', 11))
            return
        w, h = max(1, self.canvas.winfo_width()-24), max(1, self.canvas.winfo_height()-24)
        self.scale = max(.01, min(w/self.image.width, h/self.image.height, 1)) if self.zoom.get() == 'Fit' else int(self.zoom.get()[:-1])/100
        size = (max(1, round(self.image.width*self.scale)), max(1, round(self.image.height*self.scale)))
        self.photo = ImageTk.PhotoImage(self.image.resize(size, Image.Resampling.LANCZOS))
        self.canvas.create_image(12, 12, image=self.photo, anchor='nw')
        self.canvas.configure(scrollregion=(0, 0, size[0]+24, size[1]+24))
        if self.selected is not None and self.tool.get() == 'Select':
            box = [12+v*self.scale for v in self.annotations[self.selected].bounds()]
            self.canvas.create_rectangle(*box, outline=ACCENT, dash=(4, 3))
            for x, y in self.handles(box):
                self.canvas.create_rectangle(x-5, y-5, x+5, y+5, fill=ACCENT, outline=BG)
        self.status.set(f'{self.image.width} × {self.image.height} px  •  {self.scale:.0%}  •  {self.tool.get()}  •  Ctrl+S save / Ctrl+C copy')

    def image_point(self, e):
        return (max(0, min(self.image.width-1, round((self.canvas.canvasx(e.x)-12)/self.scale))),
                max(0, min(self.image.height-1, round((self.canvas.canvasy(e.y)-12)/self.scale))))

    def snapshot(self):
        return self.base_image.copy(), deepcopy(self.annotations)

    def rebuild(self):
        self.image = composite(self.base_image, self.annotations)
        self.render()

    def checkpoint(self):
        self.undo_stack.append(self.snapshot())
        while len(self.undo_stack) > 20 or (len(self.undo_stack) > 1 and sum(i[0].width*i[0].height for i in self.undo_stack) > 60_000_000):
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self.dirty = True

    @staticmethod
    def handles(box):
        x0, y0, x1, y1 = box
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

    def tool_changed(self):
        self.editing = False
        self.render()

    def select_at(self, point):
        tolerance = 7 / self.scale
        self.drag_handle = None
        if self.selected is not None:
            for index, (x, y) in enumerate(self.handles(self.annotations[self.selected].bounds())):
                if abs(point[0]-x) <= tolerance and abs(point[1]-y) <= tolerance:
                    self.drag_handle = index
                    break
        if self.drag_handle is None:
            self.selected = None
            for index in range(len(self.annotations)-1, -1, -1):
                x0, y0, x1, y1 = self.annotations[index].bounds()
                if x0-tolerance <= point[0] <= x1+tolerance and y0-tolerance <= point[1] <= y1+tolerance:
                    self.selected = index
                    break
        self.drag_original = None
        self.drag_checkpoint = False
        if self.selected is not None:
            item = self.annotations[self.selected]
            self.drag_original = deepcopy(item)
            self.color = item.color
            self.stroke.set(item.width)
            self.font_size.set(item.font_size)
        self.render()

    def transform_selection(self, point):
        if self.drag_original is None or (point == self.points[0] and not self.drag_checkpoint):
            return
        if not self.drag_checkpoint:
            self.checkpoint()
            self.drag_checkpoint = True
        item = deepcopy(self.drag_original)
        if self.drag_handle is None:
            item.move(point[0]-self.points[0][0], point[1]-self.points[0][1])
        else:
            corners = self.handles(item.bounds())
            anchor = corners[(self.drag_handle+2) % 4]
            left = self.drag_handle in (0, 3)
            top = self.drag_handle in (0, 1)
            x = min(point[0], anchor[0]-1) if left else max(point[0], anchor[0]+1)
            y = min(point[1], anchor[1]-1) if top else max(point[1], anchor[1]+1)
            item.resize((min(x, anchor[0]), min(y, anchor[1]), max(x, anchor[0]), max(y, anchor[1])))
        self.annotations[self.selected] = item
        self.font_size.set(item.font_size)
        self.rebuild()

    def apply_style(self):
        try:
            width = max(1, min(40, self.stroke.get()))
            size = max(6, min(300, self.font_size.get()))
        except tk.TclError:
            return messagebox.showerror('Invalid style', 'Enter a numeric stroke width and font size.', parent=self)
        if self.selected is not None and self.tool.get() == 'Select':
            self.checkpoint()
            item = self.annotations[self.selected]
            item.width, item.font_size, item.color = width, size, self.color
            self.rebuild()

    def edit_text(self):
        if self.selected is None or self.tool.get() != 'Select':
            return
        item = self.annotations[self.selected]
        if item.kind != 'Text':
            return
        self.editing = False
        text = simpledialog.askstring('Edit text', 'Text:', initialvalue=item.text, parent=self)
        if text is not None and text != item.text:
            self.checkpoint()
            item.text = text
            self.rebuild()

    def delete_annotation(self):
        if self.selected is not None and self.tool.get() == 'Select':
            self.checkpoint()
            self.annotations.pop(self.selected)
            self.selected = None
            self.rebuild()

    def edit_start(self, e):
        if self.image is None:
            return
        self.points = [self.image_point(e)]
        self.editing = True
        self.canvas.focus_set()
        if self.tool.get() == 'Select':
            self.select_at(self.points[0])
        else:
            self.selected = None

    def edit_move(self, e):
        if self.image is None or not getattr(self, 'editing', False):
            return
        p = self.image_point(e)
        if self.tool.get() == 'Select':
            self.transform_selection(p)
            return
        self.points.append(p)
        self.canvas.delete('preview')
        start = self.points[0]
        coords = [12+v*self.scale for point in (start, p) for v in point]
        tool = self.tool.get()
        if tool in ('Pen', 'Highlighter'):
            coords = [12+v*self.scale for point in self.points for v in point]
            self.canvas.create_line(coords, fill=self.color, width=3, tags='preview')
        elif tool == 'Arrow':
            self.canvas.create_line(coords, fill=self.color, width=2, arrow='last', tags='preview')
        elif tool == 'Ellipse':
            self.canvas.create_oval(coords, outline=self.color, width=2, tags='preview')
        else:
            self.canvas.create_rectangle(coords, outline=self.color, width=2, tags='preview')

    def edit_end(self, e):
        if self.image is None or not getattr(self, 'editing', False):
            return
        self.editing = False
        self.canvas.delete('preview')
        if self.tool.get() == 'Select':
            self.transform_selection(self.image_point(e))
            return
        start, end = self.points[0], self.image_point(e)
        self.points.append(end)
        tool = self.tool.get()
        try:
            width = max(1, min(40, self.stroke.get()))
            font_size = max(6, min(300, self.font_size.get()))
        except tk.TclError:
            return
        box = (min(start[0], end[0]), min(start[1], end[1]), max(start[0], end[0]), max(start[1], end[1]))
        if tool in ('Crop', 'Mosaic', 'Rectangle', 'Ellipse') and (box[2] <= box[0] or box[3] <= box[1]):
            return
        text = simpledialog.askstring('Add text', 'Text to place at the selected point:', parent=self) if tool == 'Text' else None
        if tool == 'Text' and not text:
            return
        self.checkpoint()
        if tool == 'Crop':
            self.base_image = self.base_image.crop(box)
            for item in self.annotations:
                item.move(-box[0], -box[1])
        else:
            points = list(self.points) if tool in ('Pen', 'Highlighter') else [start, end]
            self.annotations.append(Annotation(tool, points, self.color, width, text or '', font_size))
            self.selected = len(self.annotations)-1
            self.tool.set('Select')
        self.rebuild()

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(self.snapshot())
            self.base_image, self.annotations = self.undo_stack.pop()
            self.selected = None
            self.editing = False
            self.dirty = True
            self.rebuild()

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self.snapshot())
            self.base_image, self.annotations = self.redo_stack.pop()
            self.selected = None
            self.editing = False
            self.dirty = True
            self.rebuild()

    def choose_color(self):
        color = colorchooser.askcolor(self.color, parent=self)[1]
        if color:
            self.color = color

    def save(self):
        if self.image is None:
            return
        path = filedialog.asksaveasfilename(parent=self, defaultextension='.png',
            initialfile=dt.datetime.now().strftime('Capture_%Y-%m-%d_%H-%M-%S.png'),
            filetypes=[('PNG image', '*.png'), ('JPEG image', '*.jpg'), ('Bitmap', '*.bmp')])
        if path:
            def write():
                image = self.image
                if Path(path).suffix.lower() in ('.jpg', '.jpeg', '.bmp'):
                    background = Image.new('RGB', image.size, 'white')
                    background.paste(image, mask=image.getchannel('A') if image.mode == 'RGBA' else None)
                    image = background
                image.save(path)
                self.dirty = False
                self.status.set(f'Saved to {path}')
            self.safe(write)

    def copy(self):
        if self.image is not None:
            def perform():
                windows.copy_image(self.image)
                self.status.set('Image copied to clipboard')
            self.safe(perform)

    def open_image(self):
        path = filedialog.askopenfilename(filetypes=[('Images', '*.png *.jpg *.jpeg *.bmp *.webp')])
        if path:
            def read():
                with Image.open(path) as image:
                    self.set_image(image.convert('RGBA'), add_history=True)
            self.safe(read)

    def restore_history(self, e):
        selection = self.history_list.curselection()
        if selection:
            self.set_image(self.history[selection[0]][1])

    def clear_history(self):
        self.history.clear()
        self.history_list.delete(0, 'end')

    def poll(self):
        if self.tray is not None:
            while True:
                try:
                    command = self.tray.commands.get_nowait()
                except queue.Empty:
                    break
                if command == 'quit':
                    if not self.busy:
                        self.destroy()
                        return
                elif command == 'open' and not self.busy:
                    self.deiconify()
                    self.lift()
                elif command == 'capture' and not self.busy and self.shortcut_dialog is None:
                    self.capture('Region')
                elif command == 'startup':
                    try:
                        set_startup(not startup_enabled())
                        self.tray.icon.update_menu()
                    except Exception as exc:
                        messagebox.showerror('Startup setting', str(exc), parent=self)
        for identifier in windows.poll_hotkeys():
            if not self.busy and self.shortcut_dialog is None:
                self.capture({1: 'Region', 2: 'Full screen', 3: 'Window'}[identifier])
        self.poll_timer = self.after(100, self.poll)

    def destroy(self):
        if getattr(self, 'tray', None) is not None:
            self.tray.stop()
            self.tray = None
        if getattr(self, 'poll_timer', None):
            self.after_cancel(self.poll_timer)
            self.poll_timer = None
        windows.hotkeys(False)
        super().destroy()

    def close(self):
        if getattr(self, 'tray', None) is not None:
            if not self.busy:
                self.withdraw()
        else:
            self.destroy()


if __name__ == '__main__':
    windows.set_app_id()
    windows.dpi_aware()
    App(start_in_tray='--tray' in sys.argv).mainloop()
