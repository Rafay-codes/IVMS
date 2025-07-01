#!/bin/bash
# https://forums.developer.nvidia.com/t/trouble-initializing-nvtracker-lib/269893/5?u=smartguy9996
export LD_PRELOAD=/opt/nvidia/cupva-2.3/lib/aarch64-linux-gnu/libcupva_host.so.2.3.0
source /srv/ivms_venv/bin/activate
cd /srv/ivms/detect
python3 detect_ivms.py 
