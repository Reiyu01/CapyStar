將需要轉文字的影片放入該資料夾下
接著輸入ffmpeg -i test_voice.wav -ar 16000 -ac 1 -c:a pcm_s16le test_voice_fixed.wav -y
使其轉檔到合適格式
接著根據對應版本執行py檔
