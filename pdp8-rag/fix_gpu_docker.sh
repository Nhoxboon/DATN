#!/bin/bash

# Dừng app nếu có lỗi
set -e

echo "🔍 [1/5] Kiểm tra NVIDIA Driver trên Host..."
if ! command -v nvidia-smi &> /dev/null; then
    echo "❌ LỖI: nvidia-smi không tồn tại! Bạn phải cài đặt Nvidia Driver cho RTX A5000 trước."
    exit 1
fi
nvidia-smi

echo "🛠️ [2/5] Cài đặt NVIDIA Container Toolkit cho Ubuntu 24.04..."
# Config repository
if ! command -v nvidia-ctk &> /dev/null; then
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
      sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
      sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

    sudo apt-get update
    sudo apt-get install -y nvidia-container-toolkit
else
    echo "✅ NVIDIA Container Toolkit đã được cài đặt."
fi

echo "⚙️ [3/5] Cấu hình Docker để sử dụng NVIDIA runtime..."
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

echo "🧪 [4/5] Chạy test thử GPU bên trong môi trường Docker..."
# Thử chạy image nvidia/cuda base để kiểm tra vòng lặp truyền GPU
if sudo docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi; then
    echo "✅ THÀNH CÔNG: Docker đã có thể nhìn thấy GPU RTX A5000!"
else
    echo "❌ LỖI: Không thể pass GPU vào Docker. Hãy kiểm tra lại log."
    exit 1
fi

echo "🚀 [5/5] Rebuild lại dự án pdp8-rag với GPU"
cd /home/nhatanh/DATN/pdp8-rag

# Xóa container cũ và build lại sạch sẽ
sudo docker compose down
sudo docker compose build --no-cache
sudo docker compose up -d

echo "🎉 Hoàn tất! Vui lòng dùng lệnh 'sudo docker compose logs -f' để kiểm tra xem hệ thống đã nhận GPU và worker tải model ổn định chưa."
