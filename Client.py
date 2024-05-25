from tkinter import *
from tkinter import messagebox
from tkinter.messagebox import *
from tkinter import ttk
import ttkbootstrap as ttkb
import tkinter.messagebox as tkMessageBox
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os

from RtpPacket import RtpPacket

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

		# 设置初始窗口大小
		self.master.geometry("400x300")

		self.elapsed_var = ttkb.DoubleVar(value=0)  # progress meter
		self.remain_var = ttkb.DoubleVar(value=self.total_frames)  # progress meter

		self.createWidgets()

		self.sendRtspRequest(self.SETUP)
		
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

		# Create Subscribe button
		self.subscribe = ttkb.Button(self.buttonFrame, text="Subscribe", bootstyle="info", command=self.toggleInfoTable)
		self.subscribe.pack(side=LEFT, padx=2, pady=2, expand=True)
        
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

       # Initialize hidden by default
		self.table_frame = Frame(self.master)
		self.table_label = Label(self.table_frame, text="Information Table", font=("Arial", 16))
		self.table_label.pack()

		
	
	def setupMovie(self):
		"""Setup button handler."""
	
	def exitClient(self):
		"""Teardown button handler."""
		if self.request:
			self.sendRtspRequest(self.TEARDOWN)		
		else:
			self.request = False
		self.master.destroy() # Close the gui window
		os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT) # Delete the cache image from video

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
		while True:
			try:
				data = self.rtpSocket.recv(20480)
				if data:
					rtpPacket = RtpPacket()
					rtpPacket.decode(data)
					
					currFrameNbr = rtpPacket.seqNum()
					print("Current Seq Num: " + str(currFrameNbr))
										
					if currFrameNbr > self.frameNbr: # Discard the late packet
						self.frameNbr = currFrameNbr
						self.scale.set(self.frameNbr / self.total_frames)  # 更新进度条
						self.updateMovie(self.writeFrame(rtpPacket.getPayload()))
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
			tkMessageBox.showwarning('Connection Failed', 'Connection to \'%s\' failed.' %self.serverAddr)
	
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

		# Send the RTSP request using rtspSocket
		if requestCode in [self.SETUP, self.PLAY, self.PAUSE, self.TEARDOWN]:
			self.rtspSocket.send(request.encode())
			print('\nData sent:\n' + request)


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

	
	def openRtpPort(self):
		"""Open RTP socket binded to a specified port."""
		#-------------
		# TO COMPLETE
		#-------------
		# Create a new datagram socket to receive RTP packets from the server
		# self.rtpSocket = ...
		
		# Set the timeout value of the socket to 0.5sec
		# ...
		
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
		else: # When the user presses cancel, resume playing.
			self.playMovie()

	def toggleInfoTable(self):
			"""Toggle the display of the information table."""
			if self.table_frame.winfo_viewable():
				self.table_frame.grid_remove()
			else:
				self.table_frame.grid(row=3, column=0, columnspan=4, sticky="ew")
				self.updateInfoTable()  # Call this to update table contents dynamically
				
	def updateInfoTable(self):
		"""Update the contents of the information table."""
		# Example data - replace with your actual data update logic
		data = [("Name", "Value"), ("Frame", self.frameNbr), ("Status", "Subscribed")]
		for widget in self.table_frame.winfo_children():
			widget.destroy()  # 清除现有的控件，避免重复添加

		for i, (name, value) in enumerate(data):
			Label(self.table_frame, text=name).grid(row=i, column=0, sticky='w')
			Label(self.table_frame, text=value).grid(row=i, column=1, sticky='w')

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

	def toggle_play_pause(self,event=None):
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
