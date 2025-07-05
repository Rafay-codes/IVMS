#!/bin/bash
WD=$1
group=docker

service_exists() {
    local n=$1
    if [[ $(systemctl list-units --all -t service --full --no-legend "$n.service" | sed 's/^\s*//g' | cut -f1 -d' ') == $n.service ]]; then
        return 0
    else
        return 1
    fi
}

#if [ $(id -gn) != $group ]; then
#  exec sg $group "$0 $*"
#fi

# uninstall previous
if service_exists detect_mobile; then
	echo "[KTC Installer] Stopping all previous IVMS services"
	sudo systemctl stop detect_ivms
	sudo systemctl disable detect_ivms
	sudo rm /etc/systemd/system/detect_ivms.service
	sudo rm -r /etc/systemd/system/detect_ivms
fi

echo "[KTC Installer] Reload daemon"
sudo systemctl daemon-reload

echo "[KTC Installer] Removing previous /srv/ivms directory"
if [ -d "/srv/ivms" ]; then
	sudo rm -r /srv/ivms
fi

echo "[KTC Installer] Removing previous /srv/ivms_venv directory"
if [ -d "/srv/ivms_venv" ]; then
	sudo rm -r /srv/ivms_venv
fi

echo "[KTC Installer] Removing previous /home/nvidia/.paddleocr directory"
if [ -d "/home/nvidia/.paddleocr" ]; then
	sudo rm -r /home/nvidia/.paddleocr
fi

if [ ! "$(sudo docker ps -a -q -f name=rabbitmq)" ]; then
    if [ "$(sudo docker ps -aq -f status=exited -f name=rabbitmq)" ]; then
        # cleanup
        sudo docker rm rabbitmq
    fi
fi

# date set - assuming hwclock is set right during OS installation - better do with ntp server later
#hwclock --hctosys

# prerequistes
wget https://nvidia.box.com/shared/static/ssf2v7pf5i245fk4i0q926hy4imzs2ph.whl -O $WD/whl/torch-1.11.0-cp38-cp38-linux_aarch64.whl
sudo chmod -R 777 /srv
mkdir -p /srv/ivms
sudo apt --fix-broken install
sudo apt-get update

# Add Docker's official GPG key:
sudo apt-get install ca-certificates curl -y
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository to Apt sources:
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# without apt-get update command - docker-ce docker-ce-cli etc. are not recognised packages
sudo apt-get update
sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin python3-gi python3-venv python3-pip python3-dev python3-gst-1.0 python-gi-dev git libcairo2-dev libxt-dev libgirepository1.0-dev libcanberra-gtk-module libcanberra-gtk3-module libgstreamer-plugins-base1.0-dev libgstreamer1.0-dev libgstrtspserver-1.0-dev libx11-dev python3 python3.8-dev cmake g++ build-essential libglib2.0-dev libglib2.0-dev-bin libtool m4 autoconf automake apt-transport-https ca-certificates gir1.2-gst-plugins-bad-1.0 libgstreamer-opencv1.0-0 libgstreamer-plugins-bad1.0-0 libgstreamer-plugins-bad1.0-dev libgstreamer-plugins-good1.0-0 libgstreamer-plugins-good1.0-dev libopenblas-base libopenmpi-dev libomp-dev libjpeg-dev zlib1g-dev libpython3-dev libopenblas-dev libavcodec-dev libavformat-dev libswscale-dev gstreamer1.0-rtsp v4l-utils -y
sudo update-ca-certificates
python3 -m venv /srv/ivms_venv
source /srv/ivms_venv/bin/activate
pip install build wheel setuptools==69.5.1 Cython
# paddlepaddle-gpu supports only upto protobuf==3.20.0 and opencv==4.6.0.66
pip install numpy easydict pycairo PyGObject pika shapely lxml==5.4.0 pyyaml ipython tqdm psutil scipy protobuf==3.20.0 absl_py astor requests paddleocr==2.10.0 $WD/whl/*.whl opencv-python==4.6.0.66 seaborn==0.13.2 matplotlib==3.7.5 onnx==1.12 pycuda
#ln -s /usr/lib/python3.8/dist-packages/tensorrt /srv/ivms_venv/lib/python3.8/site-packages/tensorrt

# torchvision
# Jetpack 5.1.2 - doesnt have ffmpeg
#sudo mv /usr/local/bin/ffmpeg /usr/local/bin/ffmpeg_old
cd $WD/code/torchvision
export BUILD_VERSION=0.12
python setup.py install
#sudo mv /usr/local/bin/ffmpeg_old /usr/local/bin/ffmpeg

# setup for ivms
cp -r $WD/code/ivms/auto-start /srv/ivms/.
rsync -av --progress $WD/code/ivms/* /srv/ivms/detect --exclude deps --exclude auto-start --exclude ivmsbackend

cp -r $WD/data/.paddleocr /home/nvidia/.

mkdir -p /srv/ivms/detect/runs
mkdir -p /srv/ivms/detect/logs
mkdir -p /srv/ivms/detect/tmp

mkdir -p /home/nvidia/ivms/event_recordings
mkdir -p /home/nvidia/ivms/lpr
mkdir -p /home/nvidia/ivms/violations

chmod +x /srv/ivms/auto-start/*.sh
sudo cp /srv/ivms/auto-start/*.service /etc/systemd/system/.

echo "[KTC Installer] Reload daemon"
sudo systemctl daemon-reload

sudo systemctl enable detect_ivms.service
sudo systemctl start detect_ivms.service

# ffmpeg setup
# echo "[KTC Installer] FFMPEG installing.."
# cd $WD/code/jetson-ffmpeg
# mkdir -p build && cd build
# cmake ..
# make -j8
# sudo make install
# sudo ldconfig

# cd $WD/code/ffmpeg
# chmod +x configure
# chmod +x ./ffbuild/version.sh
# chmod +x ./ffbuild/libversion.sh
# chmod +x ./ffbuild/pkgconfig_generate.sh
# ./configure --enable-nvmpi
# make -j8
# sudo make install
# sudo ldconfig

# Docker setup
echo "[KTC Installer] Adding docker to local user group to make it run without sudo"
if [ $(getent group docker) ]; then
	sudo groupadd docker
fi
echo "[KTC Installer] Adding current user to docker group"
sudo usermod -aG docker nvidia
echo "[KTC Installer] Refresh docker group"
newgrp docker <<EONG
EONG
sudo systemctl enable docker.service
sudo systemctl enable containerd.service
if [ ! "$(sudo docker ps -a -q -f name=rabbitmq)" ]; then
    if [ "$(sudo docker ps -aq -f status=exited -f name=rabbitmq)" ]; then
        # cleanup
        sudo docker rm rabbitmq
    fi
    sudo docker run -d --restart always --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management
fi

# clean builds if any
#sudo rm -r $WD/code/jetson-ffmpeg/build 
#cd $WD/code/ffmpeg
#make clean
#cd $WD
sudo systemctl daemon-reload
echo "[KTC Installer] Done. Installation successful"
