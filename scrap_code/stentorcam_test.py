from robocam.stentorcam import StentorCam, WellPlatePathGenerator
from robocam.pihqcamera import PiHQCamera
from robocam.laser import Laser
import time

stentorcam = StentorCam(baudrate=115200, laser_pin=17)
camera = PiHQCamera(resolution=(1280, 1024))
laser = Laser(laser_pin=17)

stentorcam.home()

path = WellPlatePathGenerator.generate_path(width=4, depth=3, upper_left_loc=(72, 149.4, 153), lower_left_loc=(72, 92.5, 153), upper_right_loc=(150, 147.9, 153), lower_right_loc=(150, 90.9, 153))

for index, loc in enumerate(path):
    X, Y, Z = loc
    stentorcam.move_absolute(X=X, Y=Y, Z=Z)
    time.sleep(1) # to compensate for shakes
    
    video_path = f"index-{index}_loc-{loc}_timestamp-{time.strftime('%Y%m%d_%H%M%S')}.h264"
    camera.start_recording_video(video_path)
    
    laser.switch(Laser.ON)
    time.sleep(3)
    laser.switch(Laser.OFF)
    time.sleep(5)
    
    camera.stop_recording_video()
