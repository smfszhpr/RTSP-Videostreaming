import time
from threading import Timer
from tkinter import *
from tkinter import messagebox as tkMessageBox
from tkinter import ttk
import ttkbootstrap as ttkb
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os
from RtpPacket import RtpPacket
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"

class Client(ttkb.Frame):
    INIT = 0
    READY = 1
    PLAYING = 2
    state = INIT

    SETUP = 0
    PLAY = 1
    PAUSE = 2
    TEARDOWN = 3
    FAST_FORWARD = 4
    REWIND = 5
    REPLAY = 6  # New request code for replay

    # Initiation..
    def __init__(self, master, serveraddr, serverport, rtpport, filename):
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self.handler)

        self.serverAddr = serveraddr
        self.serverPort = int(serverport)
        self.rtpPort = int(rtpport)
        self.fileName = filename
        self.rtspSeq = 0
        self.sessionId = 0
        self.requestSent = -1
        self.teardownAcked = 0
        self.connectToServer()
        self.frameNbr = 0
        self.request = True

        self.total_frames = 0
        self.total_frames_updated = False

        self.frame_rate = 15

        self.current_frame_image = None

        self.packet_count = 0
        self.total_data_received = 0
        self.start_time = None
        self.packet_loss = 0

        self.update_interval = 1.0  # Update interval for info table in seconds
        self.timer = None  # Timer for updating info table
        self.info_window = None  # Info window

        self.packet_loss_rates = []
        self.bitrates = []
        self.time_stamps = []

        # References to graph windows
        self.bitrate_window = None
        self.packet_loss_window = None

        # 设置初始窗口大小
        self.master.geometry("400x300")

        self.elapsed_var = ttkb.DoubleVar(value=0)  # progress meter
        self.remain_var = ttkb.DoubleVar(value=self.total_frames)  # progress meter

        self.createWidgets()

        self.sendRtspRequest(self.SETUP)
        self.master.bind("<space>", self.toggle_play_pause_key)
        self.master.bind("<Right>", self.fast_forward_key)
        self.master.bind("<Left>", self.rewind_key)
        self.master.bind("<Return>", self.replay_key)

    def createWidgets(self):
        self.master.grid_rowconfigure(0, weight=1)  # Allows row 0 to expand
        self.master.grid_columnconfigure(0, weight=1)  # Allows column 0 to expand

        # Button Frame
        self.buttonFrame = ttk.Frame(self.master)
        self.buttonFrame.grid(row=1, column=0, padx=2, pady=2, sticky="ew")

        # Control button
        self.play_pause_button = ttkb.Button(self.buttonFrame, text="---Play---", bootstyle="success", command=self.toggle_play_pause)
        self.play_pause_button.pack(side=LEFT, padx=2, pady=2, expand=True)

        self.teardown = ttkb.Button(self.buttonFrame, text="Teardown", bootstyle="danger", command=self.exitClient)
        self.teardown.pack(side=LEFT, padx=2, pady=2, expand=True)

        # 快进按钮
        self.fast_forward_button = ttkb.Button(self.buttonFrame, text=">>", bootstyle="info", command=self.fastForwardMovie)
        self.fast_forward_button.pack(side=LEFT, padx=2, pady=2, expand=True)

        # 回退按钮
        self.rewind_button = ttkb.Button(self.buttonFrame, text="<<", bootstyle="info", command=self.rewindMovie)
        self.rewind_button.pack(side=LEFT, padx=2, pady=2, expand=True)

        # 重播按钮
        self.replay_button = ttkb.Button(self.buttonFrame, text="Replay", bootstyle="info", command=self.replayMovie)
        self.replay_button.pack(side=LEFT, padx=2, pady=2, expand=True)

        # Create Subscribe button
        self.subscribe = ttkb.Button(self.buttonFrame, text="Subscribe", bootstyle="info", command=self.toggleInfoWindow)
        self.subscribe.pack(side=LEFT, padx=2, pady=2, expand=True)

        # Create Graph button
        self.graph_button = ttkb.Button(self.buttonFrame, text="Graph", bootstyle="info", command=self.toggleGraphWindows)
        self.graph_button.pack(side=LEFT, padx=2, pady=2, expand=True)

        self.fullscreen = ttkb.Button(self.buttonFrame, text="Fullscreen", bootstyle="secondary", command=self.toggleFullscreen)
        self.fullscreen.pack(side=LEFT, padx=2, pady=2, expand=True)

        # Label for displaying video
        # Create a label to display the movie
        self.label = Label(self.master, height=19)
        self.label.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.label.bind("<Button-1>", self.toggle_play_pause)  # 绑定鼠标左键点击事件

        # 创建一个覆盖在视频上的透明图标Label
        self.icon_label = Label(self.master, bg='black')
        self.icon_label.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.icon_label.bind("<Button-1>", self.toggle_play_pause)  # 绑定鼠标左键点击事件

        self.create_progress_meter()

    def setupMovie(self):
        """Setup button handler."""

    def exitClient(self):
        """Teardown button handler."""
        if self.request:
            self.sendRtspRequest(self.TEARDOWN)
        else:
            self.request = False
        self.master.destroy()  # Close the gui window
        os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT)  # Delete the cache image from video

    def pauseMovie(self):
        """Pause button handler."""
        if self.state == self.PLAYING:
            self.sendRtspRequest(self.PAUSE)
            self.show_play_icon()

    def playMovie(self):
        """Play button handler."""
        if self.state == self.INIT:  # 如果当前状态是初始化，则先进行设置
            self.setupMovie()  # 调用设置函数

        if self.state == self.READY:
            # Create a new thread to listen for RTP packets
            print("Starting RTP listening thread...")
            threading.Thread(target=self.listenRtp).start()
            print("RTP listening thread started.")

            self.playEvent = threading.Event()
            self.playEvent.clear()
            self.sendRtspRequest(self.PLAY)

            self.hide_play_icon()

    def create_progress_meter(self):
        container = ttkb.Frame(self.master)
        container.grid(row=2, column=0, sticky="ew", padx=10, pady=10)  # 使用 grid 管理几何布局

        self.elapse = ttkb.Label(container, text='Time: {}'.format(int(self.elapsed_var.get())))
        self.elapse.grid(row=0, column=0, padx=10, pady=10)

        self.scale = ttkb.Scale(
            master=container,
            command=self.on_progress,
            bootstyle='secondary'
        )
        self.scale.grid(row=0, column=1, sticky="ew", padx=10, pady=10, columnspan=2)  # Make sure to set columnspan if needed

        self.remain = ttkb.Label(container, text='Time: {}'.format(int(self.remain_var.get())))
        self.remain.grid(row=0, column=3, padx=10, pady=10)

    def listenRtp(self):
        """Listen for RTP packets."""
        self.startInfoUpdateTimer()
        while True:
            try:
                data = self.rtpSocket.recv(20480)
                if data:
                    if self.start_time is None:
                        self.start_time = time.time()
                    self.total_data_received += len(data)
                    self.packet_count += 1

                    rtpPacket = RtpPacket()
                    rtpPacket.decode(data)

                    currFrameNbr = rtpPacket.seqNum()
                    print("Current Seq Num: " + str(currFrameNbr))

                    if currFrameNbr > self.frameNbr + 1:
                        self.packet_loss += currFrameNbr - self.frameNbr - 1

                    self.frameNbr = currFrameNbr
                    self.scale.set(self.frameNbr / self.total_frames)  # 更新进度条
                    self.updateMovie(self.writeFrame(rtpPacket.getPayload()))

                    # Update graph data
                    self.updateGraphData()

            except:
                # Stop listening upon requesting PAUSE or TEARDOWN
                if self.state == self.PLAYING:
                    print("Error receiving RTP Packet")
                if self.playEvent.isSet():
                    break

                # Upon receiving ACK for TEARDOWN request,
                # close the RTP socket
                if self.teardownAcked == 1:
                    self.rtpSocket.shutdown(socket.SHUT_RDWR)
                    self.rtpSocket.close()
                    break

    def writeFrame(self, data):
        """Write the received frame to a temp image file. Return the image file."""
        cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
        file = open(cachename, "wb")
        file.write(data)
        file.close()

        return cachename

    def updateMovie(self, imageFile):
        """Update the image file as video frame in the GUI."""
        try:
            img = Image.open(imageFile)
            if self.frameNbr == 0:  # 假设 frameNbr 是帧号，第一帧时 frameNbr 应为 0
                # 根据第一帧的尺寸设置窗口大小
                self.master.geometry(f"{img.width}x{img.height}")
            orig_width, orig_height = img.size  # 获取原始图像大小
            # 获取label的当前尺寸
            max_width = self.label.winfo_width()
            max_height = self.label.winfo_height()

            # 计算保持原始宽高比的目标大小
            ratio = min(max_width / orig_width, max_height / orig_height)
            new_width = int(orig_width * ratio)
            new_height = int(orig_height * ratio)
            # 调整图像大小以适应label的当前尺寸，同时保持宽高比
            img_resized = img.resize((new_width, new_height), Image.LANCZOS)

            self.current_frame_image = img_resized

            photo = ImageTk.PhotoImage(img_resized)
            self.label.configure(image=photo)
            self.label.image = photo  # 保持对photo的引用
        except Exception as e:
            print(f"Error updating movie: {e}")

    def connectToServer(self):
        """Connect to the Server. Start a new RTSP/TCP session."""
        self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.rtspSocket.connect((self.serverAddr, self.serverPort))
        except:
            tkMessageBox.showwarning('Connection Failed', 'Connection to \'%s\' failed.' % self.serverAddr)

    def sendRtspRequest(self, requestCode):
        """Send RTSP request to the server."""
        # Increase RTSP sequence number for each request
        self.rtspSeq += 1

        # Setup request
        if requestCode == self.SETUP and self.state == self.INIT:
            threading.Thread(target=self.recvRtspReply).start()
            request = "SETUP " + self.fileName + " RTSP/1.0\nCSeq: " + str(self.rtspSeq) + "\nTransport: RTP/UDP; client_port= " + str(self.rtpPort)
            self.requestSent = self.SETUP

        # Play request
        elif requestCode == self.PLAY and self.state == self.READY:
            request = "PLAY " + self.fileName + " RTSP/1.0\nCSeq: " + str(self.rtspSeq) + "\nSession: " + str(self.sessionId)
            self.requestSent = self.PLAY

        # Pause request
        elif requestCode == self.PAUSE and self.state == self.PLAYING:
            request = "PAUSE " + self.fileName + " RTSP/1.0\nCSeq: " + str(self.rtspSeq) + "\nSession: " + str(self.sessionId)
            self.requestSent = self.PAUSE

        # Teardown request
        elif requestCode == self.TEARDOWN:
            request = "TEARDOWN " + self.fileName + " RTSP/1.0\nCSeq: " + str(self.rtspSeq) + "\nSession: " + str(self.sessionId)
            self.requestSent = self.TEARDOWN

        elif requestCode == self.FAST_FORWARD:
            #self.resetPacketStats()  # Reset packet stats before fast forward
            request = f"FAST_FORWARD {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nSession: {self.sessionId}\nFrames: 50"
            self.requestSent = self.FAST_FORWARD
            self.frameNbr+=100

        elif requestCode == self.REWIND:
            #self.resetPacketStats()  # Reset packet stats before rewind
            request = f"REWIND {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nSession: {self.sessionId}\nFrames: 50"
            self.requestSent = self.REWIND

        # Replay request
        elif requestCode == self.REPLAY:
            self.resetPacketStats()  # Reset packet stats before replay
            request = f"REPLAY {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nSession: {self.sessionId}\nFrame: 0"
            self.requestSent = self.REPLAY

        # Send the RTSP request using rtspSocket
        if requestCode in [self.SETUP, self.PLAY, self.PAUSE, self.TEARDOWN, self.FAST_FORWARD, self.REWIND, self.REPLAY]:
            self.rtspSocket.send(request.encode())
            print('\nData sent:\n' + request)

    def resetPacketStats(self):
        """Reset packet stats for accurate loss rate calculation."""
        self.packet_count = 0
        self.packet_loss = 0

    def recvRtspReply(self):
        """Receive RTSP reply from the server."""
        while True:
            reply = self.rtspSocket.recv(1024)

            if reply:
                self.parseRtspReply(reply.decode("utf-8"))

            # Close the RTSP socket upon requesting Teardown
            if self.requestSent == self.TEARDOWN:
                self.rtspSocket.shutdown(socket.SHUT_RDWR)
                self.rtspSocket.close()
                break

    def parseRtspReply(self, data):
        """Parse the RTSP reply from the server."""
        lines = data.split('\n')
        seqNum = int(lines[1].split(' ')[1])

        # Process only if the server reply's sequence number is the same as the request's
        if seqNum == self.rtspSeq:
            session = int(lines[2].split(' ')[1])
            # New RTSP session ID
            if self.sessionId == 0:
                self.sessionId = session
                print("Session ID set to:", self.sessionId)

            # Process only if the session ID is the same
            if self.sessionId == session:
                if int(lines[0].split(' ')[1]) == 200:
                    if self.requestSent == self.SETUP:
                        self.state = self.READY

                        self.total_frames = int(lines[3].split(' ')[1])

                        print("State updated to READY")
                        self.openRtpPort()
                    elif self.requestSent == self.PLAY:
                        self.state = self.PLAYING
                        print("State updated to PLAYING")
                    elif self.requestSent == self.PAUSE:
                        self.state = self.READY
                        print("State updated to READY")
                        self.playEvent.set()  # Ensure the play thread is allowed to exit cleanly
                    elif self.requestSent == self.TEARDOWN:
                        self.state = self.INIT
                        print("State reset to INIT")
                        self.teardownAcked = 1  # Flag the teardownAcked to close the socket.
                    elif self.requestSent == self.REPLAY:
                        self.state = self.READY  # Set state to READY after receiving replay ACK
                        print("State updated to READY for REPLAY")
                        self.frameNbr = 0  # Reset the frame number to 0
                        self.playMovie()  # Start playing the movie from the beginning

    def openRtpPort(self):
        """Open RTP socket binded to a specified port."""
        self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rtpSocket.settimeout(0.5)
        try:
            self.rtpSocket.bind(('0.0.0.0', self.rtpPort))
            print(f"Successfully bound to port {self.rtpPort}")
        except Exception as e:
            tkMessageBox.showwarning('Unable to Bind', f'Unable to bind PORT={self.rtpPort}')
            print(f"Error binding to port {self.rtpPort}: {e}")

    def handler(self):
        """Handler on explicitly closing the GUI window."""
        self.pauseMovie()
        if tkMessageBox.askokcancel("Quit?", "Are you sure you want to quit?"):
            self.exitClient()
        else:  # When the user presses cancel, resume playing.
            self.playMovie()

    def toggleInfoWindow(self):
        """Toggle the display of the information window."""
        if self.info_window and self.info_window.winfo_exists():
            if self.timer:
                self.timer.cancel()
            self.info_window.destroy()
            self.info_window = None
        else:
            self.info_window = Toplevel(self.master)
            self.info_window.title("Information Table")
            self.info_table = Frame(self.info_window)
            self.info_table.pack(fill="both", expand=True)
            self.updateInfoTable()  # Call this to update table contents dynamically

    def updateInfoTable(self):
        """Update the contents of the information table."""
        if self.info_window and self.info_window.winfo_exists():
            if self.start_time:
                elapsed_time = time.time() - self.start_time
                bitrate = (self.total_data_received * 8) / elapsed_time  # bits per second
                packet_loss_rate = (self.packet_loss / self.packet_count) * 100 if self.packet_count > 0 else 0
            else:
                bitrate = 0
                packet_loss_rate = 0

            # Example data - replace with your actual data update logic
            data = [
                ("Name", "Value"),
                ("Frame", self.frameNbr),
                ("Status", "Subscribed"),
                ("Bitrate (bps)", int(bitrate)),
                ("Packet Loss Rate (%)", round(packet_loss_rate, 2))
            ]

            self.master.after(0, self.updateInfoTableUI, data)

            self.startInfoUpdateTimer()

    def updateInfoTableUI(self, data):
        """Update the info table UI elements."""
        if self.info_window and self.info_window.winfo_exists():
            for widget in self.info_table.winfo_children():
                widget.destroy()  # 清除现有的控件，避免重复添加

            for i, (name, value) in enumerate(data):
                Label(self.info_table, text=name).grid(row=i, column=0, sticky='w')
                Label(self.info_table, text=value).grid(row=i, column=1, sticky='w')

    def startInfoUpdateTimer(self):
        """Start a timer to update the info table periodically."""
        self.timer = Timer(self.update_interval, self.updateInfoTable)
        self.timer.start()

    def toggleFullscreen(self):
        """Toggle the fullscreen state of the window."""
        self.is_fullscreen = not getattr(self, 'is_fullscreen', False)  # Toggle state and default to False if not set
        self.master.attributes("-fullscreen", self.is_fullscreen)  # Set the fullscreen attribute

        if self.is_fullscreen:
            self.label.grid_forget()  # Remove the label from grid
            self.label.grid(row=0, column=0, sticky="nsew")  # Re-add the label to grid to fill the whole window
        else:
            self.label.grid_forget()  # Remove the label from grid
            self.label.grid(row=0, column=0, columnspan=4, sticky="nsew")  # Restore the original grid configuration

    def on_progress(self, val: float):
        if self.total_frames_updated is False and self.total_frames > 0:
            self.remain_var.set(self.total_frames)
            self.total_frames_updated = True

        # 当前进度条位置代表的总帧数
        current_frame = int(float(val) * self.total_frames)

        # 计算时间（假设frame_rate是已知的）
        elapsed_time = current_frame / self.frame_rate
        total_time = self.total_frames / self.frame_rate

        # 将时间转换为分钟和秒
        elapsed_minutes = int(elapsed_time // 60)
        elapsed_seconds = int(elapsed_time % 60)
        total_minutes = int(total_time // 60)
        total_seconds = int(total_time % 60)

        # 设置进度条变量
        self.elapsed_var.set(current_frame)
        self.remain_var.set(self.total_frames - current_frame)

        # 更新进度条的显示为时间格式
        self.elapse.configure(text=f'Time: {elapsed_minutes:02d}:{elapsed_seconds:02d}')
        self.remain.configure(text=f'Time: {total_minutes:02d}:{total_seconds:02d}')

    def toggle_play_pause(self, event=None):
        if self.state == self.PLAYING:
            self.pauseMovie()
            self.play_pause_button.config(text="---Play---")
            # 显示播放图标
            self.show_play_icon()
        else:
            self.playMovie()
            self.play_pause_button.config(text="--Pause--")
            # 隐藏播放图标
            self.hide_play_icon()
    def toggle_play_pause_key(self, event=None):
        self.toggle_play_pause()
    def fast_forward_key(self, event=None):
        self.fastForwardMovie()
    def rewind_key(self, event=None):
        self.rewindMovie()
    def replay_key(self, event=None):
        self.replayMovie()
    def show_play_icon(self):
        # 加载播放图标
        frame_image = self.current_frame_image
        play_image = Image.open("path_to_play_icon.png").convert("RGBA")  # 确保图标文件存在
        # 获取透明通道作为蒙版
        mask = play_image.split()[3]

        # 获取两个图像的尺寸
        frame_width, frame_height = frame_image.size
        icon_width, icon_height = play_image.size

        # 计算图标的位置（视频帧的中心）
        x = (frame_width - icon_width) // 2
        y = (frame_height - icon_height) // 2

        # 将图标粘贴到视频帧上，需要确保使用带透明的paste方法
        frame_image.paste(play_image, (x, y), mask)

        # 将更新后的图像转换为Tkinter兼容的PhotoImage
        play_photo = ImageTk.PhotoImage(frame_image)

        self.icon_label.config(image=play_photo)
        self.icon_label.image = play_photo  # 保持对PhotoImage的引用
        self.icon_label.grid()

    def hide_play_icon(self):
        # 清除图标
        self.icon_label.grid_remove()

    def fastForwardMovie(self):
        """处理快进动作。"""
        if self.state == self.PLAYING:
            self.sendRtspRequest(self.FAST_FORWARD)

    def rewindMovie(self):
        if self.state == self.PLAYING:
            self.sendRtspRequest(self.REWIND)

    def replayMovie(self):
        """处理重播动作。"""
        if self.state == self.PLAYING or self.state == self.READY:
            self.sendRtspRequest(self.REPLAY)

    def updateGraphData(self):
        """Update graph data for plotting."""
        if self.start_time:
            elapsed_time = time.time() - self.start_time
            bitrate = (self.total_data_received * 8) / elapsed_time  # bits per second
            packet_loss_rate = (self.packet_loss / self.packet_count) * 100 if self.packet_count > 0 else 0
        else:
            bitrate = 0
            packet_loss_rate = 0

        self.time_stamps.append(time.time() - self.start_time if self.start_time else 0)
        self.bitrates.append(bitrate)
        self.packet_loss_rates.append(packet_loss_rate)

    def toggleGraphWindows(self):
        """Toggle the display of the graph windows."""

        if not self.bitrate_window and not self.packet_loss_window:
            self.showGraph()
        else:
            if self.bitrate_window and self.bitrate_window.winfo_exists():
                self.bitrate_window.destroy()
                self.bitrate_window = None

            if self.packet_loss_window and self.packet_loss_window.winfo_exists():
                self.packet_loss_window.destroy()
                self.packet_loss_window = None

    def showGraph(self):
        """Show the bitrate and packet loss rate graphs."""
        # Create a new window for bitrate graph
        self.bitrate_window = Toplevel(self.master)
        self.bitrate_window.title("Bitrate Over Time")
        fig_bitrate, ax_bitrate = plt.subplots()
        line_bitrate, = ax_bitrate.plot([], [], 'b-')
        ax_bitrate.set_xlabel("Time (s)")
        ax_bitrate.set_ylabel("Bitrate (bps)")
        ax_bitrate.set_title("Bitrate Over Time")

        # Create a new window for packet loss rate graph
        self.packet_loss_window = Toplevel(self.master)
        self.packet_loss_window.title("Packet Loss Rate Over Time")
        fig_packet_loss, ax_packet_loss = plt.subplots()
        line_packet_loss, = ax_packet_loss.plot([], [], 'r-')
        ax_packet_loss.set_xlabel("Time (s)")
        ax_packet_loss.set_ylabel("Packet Loss Rate (%)")
        ax_packet_loss.set_title("Packet Loss Rate Over Time")

        def animate_bitrate(i):
            line_bitrate.set_data(self.time_stamps, self.bitrates)
            ax_bitrate.relim()
            ax_bitrate.autoscale_view()

        def animate_packet_loss(i):
            line_packet_loss.set_data(self.time_stamps, self.packet_loss_rates)
            ax_packet_loss.relim()
            ax_packet_loss.autoscale_view()

        ani_bitrate = animation.FuncAnimation(fig_bitrate, animate_bitrate, interval=1000)
        ani_packet_loss = animation.FuncAnimation(fig_packet_loss, animate_packet_loss, interval=1000)

        canvas_bitrate = FigureCanvasTkAgg(fig_bitrate, master=self.bitrate_window)
        canvas_bitrate.get_tk_widget().pack(fill=BOTH, expand=True)
        canvas_bitrate.draw()

        canvas_packet_loss = FigureCanvasTkAgg(fig_packet_loss, master=self.packet_loss_window)
        canvas_packet_loss.get_tk_widget().pack(fill=BOTH, expand=True)
        canvas_packet_loss.draw()