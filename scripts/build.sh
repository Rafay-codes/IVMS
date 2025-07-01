#!/bin/bash

# setup jenkins build environment before (in dockerfile) or just use agent
WD=$PWD
VERSION=`git describe --dirty |sed -e "s/^[^0-9]*//"`

mkdir -p $WD/build/code
mkdir -p $WD/build/data
mkdir -p $WD/build/whl

cp -r $WD/deps/code/* $WD/build/code/.
#cp -r $WD/deps/data/* $WD/build/data/.
cp -r $WD/deps/data/.paddleocr $WD/build/data/.
cp -r $WD/deps/whl/* $WD/build/whl/.

mkdir -p $WD/build/code/ivms
echo $VERSION >> $WD/build/code/ivms/ktc_sw_version.txt
rsync -av --progress $WD/* $WD/build/code/ivms/. --exclude deps --exclude build

cp $WD/scripts/install.sh $WD/build/.
cp $WD/scripts/ktc-run-install-sh-aarch64.AppImage $WD/build/.

# paddlepaddle-gpu supports only upto protobuf==3.20.0 and opencv==4.6.0.66
wget https://paddle-inference-lib.bj.bcebos.com/2.4.1/python/Jetson/jetpack5.0.2_gcc9.4/all/paddlepaddle_gpu-2.4.1-cp38-cp38-linux_aarch64.whl -P $WD/build/whl/

tar -czvf build_$VERSION.tar.gz build
