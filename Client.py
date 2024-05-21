from tkinter import *
from tkinter import ttk
import tkinter.messagebox as tkMessageBox
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os
import ttkbootstrap as ttkb

from RtpPacket import RtpPacket

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"

class Client:
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
		self.createWidgets()
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

		# 设置初始窗口大小
		self.master.geometry("400x300")
		
	def createWidgets(self):
		self.master.grid_rowconfigure(0, weight=1)  # Allows row 0 to expand
		self.master.grid_columnconfigure(0, weight=1)  # Allows column 0 to expand


		# Button Frame
		self.buttonFrame = ttk.Frame(self.master)
		self.buttonFrame.grid(row=1, column=0, padx=2, pady=2, sticky="ew")
        
        # Control buttons
		self.setup = ttkb.Button(self.buttonFrame, text="Setup", bootstyle="primary", command=self.setupMovie)
		self.setup.pack(side=LEFT, padx=2, pady=2, expand=True)
        
		self.start = ttkb.Button(self.buttonFrame, text="Play", bootstyle="success", command=self.playMovie)
		self.start.pack(side=LEFT, padx=2, pady=2, expand=True)
        
		self.pause = ttkb.Button(self.buttonFrame, text="Pause", bootstyle="warning", command=self.pauseMovie)
		self.pause.pack(side=LEFT, padx=2, pady=2, expand=True)
        
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

       # Initialize hidden by default
		self.table_frame = Frame(self.master)
		self.table_label = Label(self.table_frame, text="Information Table", font=("Arial", 16))
		self.table_label.pack()
	
	def setupMovie(self):
		"""Setup button handler."""
		if self.state == self.INIT:
			self.sendRtspRequest(self.SETUP)
	
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
	
	def playMovie(self):
		"""Play button handler."""
		print("Playing...")
		if self.state == self.READY:
			# Create a new thread to listen for RTP packets
			print("Starting RTP listening thread...")
			threading.Thread(target=self.listenRtp).start()
			print("RTP listening thread started.")

			self.playEvent = threading.Event()
			self.playEvent.clear()
			self.sendRtspRequest(self.PLAY)
	
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
						self.updateMovie(self.writeFrame(rtpPacket.getPayload()))
			except:
				# Stop listening upon requesting PAUSE or TEARDOWN
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
