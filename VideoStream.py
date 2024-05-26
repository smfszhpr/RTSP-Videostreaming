class VideoStream:
	def __init__(self, filename):
		self.filename = filename
		try:
			self.file = open(filename, 'rb')
		except:
			raise IOError
		self.frameNum = 0

		# 统计总的帧数
		self.total_frameNum = 0
		tmp_length = self.file.read(5)

		while tmp_length:
			framelength = int(tmp_length)
            # Read the current frame
			self.file.seek(framelength, 1)

			self.total_frameNum += 1
			tmp_length = self.file.read(5)
		self.file.seek(0, 0)
	
	def nextFrame(self):
		"""Get next frame."""
		data = self.file.read(5) # Get the framelength from the first 5 bits
		if data: 
			framelength = int(data)
							
			# Read the current frame
			data = self.file.read(framelength)
			self.frameNum += 1
		return data
		
	def frameNbr(self):
		"""Get frame number."""
		return self.frameNum
	
	def get_total_frames_num(self):
		return self.total_frameNum

	def fastForward(self):
		"""Fast forward the video by 50 frames."""
		self.frameNum = min(self.frameNum + 50, self.total_frameNum - 1)
		self.file.seek(self.getFramePosition(self.frameNum))

	def rewind(self):
		"""Rewind the video by 50 frames."""
		self.frameNum = max(self.frameNum - 50, 0)
		self.file.seek(self.getFramePosition(self.frameNum))
  
	def getFramePosition(self, frameNumber):
		"""Calculate byte position for the given frame number."""
		position = 0
		self.file.seek(0)
		for _ in range(frameNumber):
			frame_length = int(self.file.read(5))
			position += frame_length + 5
			self.file.seek(position)
		self.file.seek(0)
		return position