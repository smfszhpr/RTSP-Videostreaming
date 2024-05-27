# RTSP-Videostreaming
SJTU 计算机网络大作业，使用python、RTSP和RTP协议制作mjpeg视频流

启动示例：

python Server.py 8554 

python ClientLauncher.py localhost 8554 5114 video.mjpeg

1.0版本：实现基本要求和添加了订阅按钮用于展示文字

1.1版本：美化了按钮样式，添加了控制视频大小的功能

1.2版本，基本实现了进度条功能，但视频帧率固定为15帧每秒

1.3版本，继续美化了按钮，删除setup按钮，合并暂停与播放按钮，实现点击视频来播放与暂停功能

1.6版本，实现了快进和回退功能，暂未整合丢包率等功能
