activate labelimg
cd /D E:\SmartLarder\AnnotationEvaluation\labelImg\labelImg

D:\BoyangDeng\Biang\Topic\SmartLarder\labelImg\resources
labelimg_shortcut
labelme_to_VOC_use_guide


#conda install pyqt=5
pip install pyqt5==5.15.2 lxml exif

pip install --upgrade opencv-python
pip install --upgrade pyinstaller

pip install opencv-python==3.4.18.65	
pip install opencv-contrib-python==3.4.18.65	

pyrcc5 resources.qrc -o libs/resources.py

pip install pyinstaller
pyinstaller --hidden-import=pyqt5 --hidden-import=lxml -F -n "labelImg" -c labelImg.py -p ./libs -p ./


# cyw
# vic


