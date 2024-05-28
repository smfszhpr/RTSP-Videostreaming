from collections import deque

class VideoStream:
	def __init__(self, filename):
		self.filename = filename
		self.data_length_stack = deque()
		try:
			self.file = open(filename, 'rb')
		except IOError:
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
		try:
			data = self.file.read(5) # Get the framelength from the first 5 bits
			if data: 
				framelength = int(data)
				self.data_length_stack.append(framelength)
			# Read the current frame
				data = self.file.read(framelength)
				self.frameNum += 1
			return data
		except Exception as e:
			print(f"Error reading frame: {e}")
			return None
	def frameNbr(self):
		"""Get frame number."""
		return self.frameNum
	
	def get_total_frames_num(self):
		"""Get total number of frames."""
		return self.total_frameNum
	
	def movepoint(self, n):
		"""Move forward or backward n frames."""
		try:
			if n > 0:
				for _ in range(n):
					data = self.file.read(5)
					if data:
						framelength = int(data)
						self.data_length_stack.append(framelength)
						self.file.seek(framelength, 1)
						self.frameNum += 1
					else:
						break
			else:
				n = -n
				framelengths = 0
				for _ in range(n):
					if self.frameNum == 0:
						break
					framelength = self.data_length_stack.pop()
					framelengths += (framelength + 5)
					self.frameNum -= 1
				self.file.seek(-framelengths, 1)
		except Exception as e:
			print(f"Error in movepoint: {e}")
	def backpoint(self, n):
		"""Move backward n frames."""
		if n <= 0 or self.frameNum <= 0:
			return
		
		framelengths = 0
		for _ in range(n):
			if self.frameNum == 0:
				break
			framelength = self.data_length_stack.pop()
			framelengths += (framelength + 5)
			self.frameNum -= 1
		self.file.seek(-framelengths, 1)
	
	def reset(self):
		"""Reset the video stream to the beginning."""
		self.file.seek(0)
		self.frameNum = 0
		self.data_length_stack.clear()
