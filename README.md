# To start backend:
cd ~/ivmsbackend
source venv/bin/activate
gunicorn django_project.wsgi --bind 0.0.0.0:8000

# To start simulated camera feed (execute below commands in different terminals)
cd ~
./ivms_test_feed_4 "multifilesrc location=/home/nvidia/ivms_timeless_file.mp4 loop=true ! decodebin ! videoflip method=horizontal-flip ! textoverlay text=\"IVMS-RearCam-4\" valignment=top halignment=left font-desc=\"Sans, 8\" ! x264enc ! rtph264pay name=pay0 pt=96"

cd ~
./ivms_test_feed_5 "multifilesrc location=/home/nvidia/ivms_timeless_file.mp4 loop=true ! decodebin ! videoflip method=horizontal-flip ! textoverlay text=\"IVMS-RearCam-5\" valignment=top halignment=left font-desc=\"Sans, 8\" ! x264enc ! rtph264pay name=pay0 pt=96"

cd ~
./ivms_test_feed_6 "multifilesrc location=/home/nvidia/ivms_timeless_file.mp4 loop=true ! decodebin ! videoflip method=horizontal-flip ! textoverlay text=\"IVMS-RearCam-6\" valignment=top halignment=left font-desc=\"Sans, 8\" ! x264enc ! rtph264pay name=pay0 pt=96"

## Handy Commands  
L4T version corresponds to jetpack version  
sudo apt-cache show nvidia-jetpack # 5.1.1-b56  
dpkg-query --show nvidia-l4t-core # 35.3.1-20230319081403  


