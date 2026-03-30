如何使用  在該test 資料夾下輸入
wget -O {your_jpg_name}.jpg "{Download url}"

test_image.py 中 修改{jpg_name}

with open("{jpg_name}.jpg", "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

