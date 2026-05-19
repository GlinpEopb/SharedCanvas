"""
共享画板 — WebSocket 客户端
通过 WebSocket 连接到云服务器，实时同步笔迹。
"""

import threading
import tkinter as tk
from tkinter import simpledialog, messagebox
import websocket


# ── 颜色常量 ─────────────────────────────────────────────
CANVAS_BG   = '#FFFEF9'   # 画布底色：暖白草稿纸
TOOLBAR_BG  = '#F5F0E8'   # 工具栏底色：暖灰
SELECTED_BG = '#444444'   # 选中态背景：深灰
CLEAR_BG    = '#E07070'   # 清空按钮：珊瑚红
ERASER_W    = 20          # 橡皮擦固定宽度（px）


class SharedCanvas:
    def __init__(self):
        # 1. 创建隐藏主窗口，用于弹出连接对话框
        self.root = tk.Tk()
        self.root.withdraw()

        # 2. 询问服务器地址
        server_input = simpledialog.askstring(
            "连接服务器", "请输入服务器地址：\n"
            "本地测试 → ws://localhost:9999\n"
            "云端部署 → 直接粘贴 Render 域名即可\n"
            "（如 sharedcanvas-xxxx.onrender.com）",
            initialvalue="ws://localhost:9999", parent=self.root
        )
        if not server_input:
            self.root.destroy()
            return

        # 自动转换 URL 为 WebSocket 格式
        server_url = server_input.strip()
        if server_url.startswith('https://'):
            server_url = 'wss://' + server_url[8:]
        elif server_url.startswith('http://'):
            server_url = 'ws://' + server_url[7:]
        elif not server_url.startswith(('ws://', 'wss://')):
            # 裸域名，默认用 wss://
            server_url = 'wss://' + server_url

        # 3. 询问昵称
        nickname = simpledialog.askstring(
            "昵称", "请输入你的昵称：",
            initialvalue="匿名", parent=self.root
        )
        if not nickname or not nickname.strip():
            nickname = "匿名"

        # 4. 连接 WebSocket 服务器
        try:
            self.ws = websocket.WebSocket()
            self.ws.connect(server_url)
        except Exception as e:
            messagebox.showerror(
                "连接失败",
                f"无法连接到 {server_url.strip()}\n\n{e}"
            )
            self.root.destroy()
            return

        # 5. 配置并显示主窗口
        self.root.deiconify()
        self.root.title(f"✏️ 共享画板 — {nickname.strip()}")
        self.root.configure(bg=TOOLBAR_BG)
        self.root.minsize(500, 400)

        # ── 状态变量 ──
        self.current_tool  = 'pen'        # 'pen' | 'eraser'
        self.current_color = '#000000'    # 当前画笔颜色
        self.current_width = 3            # 当前画笔粗细（1-20）
        self.drawing       = False        # 鼠标是否按下
        self.last_x        = None         # 上一笔迹点 x
        self.last_y        = None         # 上一笔迹点 y
        self.running       = True         # 接收线程运行标志
        self.color_swatches = []          # 颜色色块数据

        # ── 构建界面 ──
        self._build_toolbar()
        self._build_canvas()

        # ── 启动网络接收线程 ──
        self.recv_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.recv_thread.start()

        # 窗口关闭回调
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    # ═══════════════════════════════════════════════════════
    # 工具栏构建
    # ═══════════════════════════════════════════════════════

    def _build_toolbar(self):
        """构建顶部工具栏（一行）"""
        toolbar = tk.Frame(self.root, bg=TOOLBAR_BG)
        toolbar.pack(fill='x', padx=10, pady=(10, 5))

        # ── 画笔按钮 ──
        self.btn_pen = tk.Button(
            toolbar, text='画笔', command=self._select_pen,
            font=('Courier', 10), relief='flat', borderwidth=1,
            bg=SELECTED_BG, fg='white', activebackground='#555555',
            width=7, padx=4, pady=3, cursor='hand2'
        )
        self.btn_pen.pack(side='left', padx=2)

        # ── 橡皮擦按钮 ──
        self.btn_eraser = tk.Button(
            toolbar, text='橡皮擦', command=self._select_eraser,
            font=('Courier', 10), relief='flat', borderwidth=1,
            bg=TOOLBAR_BG, fg='black', activebackground='#E0D8C8',
            width=7, padx=4, pady=3, cursor='hand2'
        )
        self.btn_eraser.pack(side='left', padx=2)

        # 分隔
        tk.Frame(toolbar, width=12, bg=TOOLBAR_BG).pack(side='left')

        # ── 颜色色块（圆形） ──
        colors = [
            '#000000',   # 黑
            '#E74C3C',   # 红
            '#3498DB',   # 蓝
            '#2ECC71',   # 绿
            '#F39C12',   # 橙
            '#9B59B6',   # 紫
        ]

        for hex_color in colors:
            cf = tk.Frame(toolbar, bg=TOOLBAR_BG, width=26, height=26)
            cf.pack(side='left', padx=3)
            cf.pack_propagate(False)

            cv = tk.Canvas(cf, width=26, height=26,
                           bg=TOOLBAR_BG, highlightthickness=0, cursor='hand2')
            cv.pack()

            cv.create_oval(3, 3, 23, 23, fill=hex_color, outline=hex_color)
            ring = cv.create_oval(1, 1, 25, 25,
                                  outline='' if hex_color != '#000000' else '#555555',
                                  width=2)

            cv.bind('<Button-1>', lambda e, c=hex_color: self._select_color(c))

            self.color_swatches.append({
                'canvas': cv,
                'color':  hex_color,
                'ring':   ring,
            })

        # 分隔
        tk.Frame(toolbar, width=12, bg=TOOLBAR_BG).pack(side='left')

        # ── 粗细标签 & 滑块 ──
        tk.Label(toolbar, text='粗细', font=('Courier', 9),
                 bg=TOOLBAR_BG, fg='#555555').pack(side='left')

        self.width_slider = tk.Scale(
            toolbar, from_=1, to=20, orient='horizontal',
            command=self._on_width_change, length=100,
            bg=TOOLBAR_BG, highlightthickness=0, bd=0,
            troughcolor='#D0CDC5', sliderrelief='flat',
            sliderlength=12, showvalue=False
        )
        self.width_slider.set(3)
        self.width_slider.pack(side='left', padx=(4, 0))

        # ── 弹性空间（把清空按钮推到最右） ──
        tk.Frame(toolbar, bg=TOOLBAR_BG).pack(side='left', fill='x', expand=True)

        # ── 清空按钮 ──
        self.btn_clear = tk.Button(
            toolbar, text='清空', command=self._clear_canvas,
            font=('Courier', 10, 'bold'), relief='flat', borderwidth=1,
            bg=CLEAR_BG, fg='white', activebackground='#C05555',
            width=7, padx=4, pady=3, cursor='hand2'
        )
        self.btn_clear.pack(side='right', padx=2)

    # ═══════════════════════════════════════════════════════
    # 画布构建
    # ═══════════════════════════════════════════════════════

    def _build_canvas(self):
        """构建中间画布区域"""
        canvas_frame = tk.Frame(self.root, bg=TOOLBAR_BG)
        canvas_frame.pack(expand=True, fill='both', padx=10, pady=(5, 10))

        self.canvas = tk.Canvas(
            canvas_frame, bg=CANVAS_BG, highlightthickness=0,
            cursor='cross'
        )
        self.canvas.pack(expand=True, fill='both')

        # 绑定鼠标事件
        self.canvas.bind('<Button-1>',       self._on_mouse_down)
        self.canvas.bind('<B1-Motion>',      self._on_mouse_drag)
        self.canvas.bind('<ButtonRelease-1>', self._on_mouse_up)

    # ═══════════════════════════════════════════════════════
    # 工具切换
    # ═══════════════════════════════════════════════════════

    def _select_pen(self):
        """切换到画笔工具"""
        self.current_tool = 'pen'
        self.btn_pen.configure(bg=SELECTED_BG, fg='white')
        self.btn_eraser.configure(bg=TOOLBAR_BG, fg='black')

    def _select_eraser(self):
        """切换到橡皮擦工具"""
        self.current_tool = 'eraser'
        self.btn_pen.configure(bg=TOOLBAR_BG, fg='black')
        self.btn_eraser.configure(bg=SELECTED_BG, fg='white')

    def _select_color(self, color):
        """选择画笔颜色，更新色块选中环"""
        self.current_color = color
        for sw in self.color_swatches:
            if sw['color'] == color:
                sw['canvas'].itemconfig(sw['ring'], outline='#555555')
            else:
                sw['canvas'].itemconfig(sw['ring'], outline='')

    def _on_width_change(self, val):
        """粗细滑块回调"""
        self.current_width = int(val)

    # ═══════════════════════════════════════════════════════
    # 鼠标事件 — 绘图
    # ═══════════════════════════════════════════════════════

    def _on_mouse_down(self, event):
        """鼠标按下：开始一条笔迹"""
        self.drawing = True
        self.last_x = event.x
        self.last_y = event.y

    def _on_mouse_drag(self, event):
        """鼠标拖动：从上一个点画线到当前点，并发送给服务器"""
        if not self.drawing:
            return

        x, y = event.x, event.y

        # 根据工具决定颜色和宽度
        if self.current_tool == 'pen':
            color = self.current_color
            width = self.current_width
        else:  # 橡皮擦：使用画布底色覆盖
            color = CANVAS_BG
            width = ERASER_W

        # 本地绘制线段
        self.canvas.create_line(
            self.last_x, self.last_y, x, y,
            fill=color, width=width, capstyle='round', smooth=True
        )

        # 发送 DRAW 消息到服务器（WebSocket 自带帧边界，无需 \n）
        self._send(f"DRAW:{self.last_x},{self.last_y},{x},{y},{color},{width}")

        self.last_x = x
        self.last_y = y

    def _on_mouse_up(self, event):
        """鼠标抬起：结束当前笔迹"""
        self.drawing = False
        self.last_x = None
        self.last_y = None

    # ═══════════════════════════════════════════════════════
    # 清空
    # ═══════════════════════════════════════════════════════

    def _clear_canvas(self):
        """清空本地画布并广播 CLEAR 指令给所有其他客户端"""
        self.canvas.delete('all')
        self._send("CLEAR")

    # ═══════════════════════════════════════════════════════
    # 网络通信
    # ═══════════════════════════════════════════════════════

    def _send(self, msg):
        """发送消息到服务器（非阻塞，忽略发送失败）"""
        try:
            self.ws.send(msg)
        except Exception:
            pass

    def _receive_loop(self):
        """接收线程：持续读取服务器转发的消息，交给主线程渲染"""
        while self.running:
            try:
                msg = self.ws.recv()
            except Exception:
                break
            if not msg:
                break
            self._handle_message(msg)

        # 连接断开时弹窗提示
        if self.running:
            self.root.after(0, lambda: messagebox.showwarning(
                "连接断开", "与服务器的连接已断开。\n你仍可以在本地继续绘制，但无法同步。"
            ))

    def _handle_message(self, msg):
        """处理收到的消息，通过 after 安全地在主线程渲染"""
        print(f"[收到] {msg}")
        try:
            if msg == 'CLEAR':
                self.root.after(0, self.canvas.delete, 'all')
                print("[渲染] 清空画布")
            elif msg.startswith('DRAW:'):
                parts = msg[5:].split(',')
                if len(parts) == 6:
                    x1, y1, x2, y2, color, width = parts
                    x1 = int(x1); y1 = int(y1); x2 = int(x2); y2 = int(y2)
                    w = int(width)
                    self._draw_remote_line(x1, y1, x2, y2, color, w)
        except Exception as e:
            print(f"[错误] 处理消息失败: {e}")

    def _draw_remote_line(self, x1, y1, x2, y2, color, width):
        """通过 after 在主线程安全绘制远程线条"""
        self.root.after(0, self._do_draw_line, x1, y1, x2, y2, color, width)

    def _do_draw_line(self, x1, y1, x2, y2, color, width):
        """实际执行画线（在主线程中被 after 调用）"""
        self.canvas.create_line(
            x1, y1, x2, y2,
            fill=color, width=width,
            capstyle='round', smooth=True)

    def _on_close(self):
        """窗口关闭时清理网络资源"""
        self.running = False
        try:
            self.ws.close()
        except Exception:
            pass
        self.root.destroy()


if __name__ == '__main__':
    SharedCanvas()
