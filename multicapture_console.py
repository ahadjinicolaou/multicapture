import PyCapture2

import os
import sys
import logging
import random
import time
from datetime import date, datetime, timedelta

import configparser
import multiprocessing as mp
from ctypes import windll

def initializeCameras():
    bus = PyCapture2.BusManager()
    nCameras = bus.getNumOfCameras()
    cameras = [None for _ in range(nCameras)]

    # enforce a frame rate of 30 or 60 fps (even if the camera supports others)
    frameRateCode = getFrameRateCode(config["DEFAULT"]["frameRate"])
    videoModeCode = getVideoModeCode(config["DEFAULT"]["videoMode"])
    asyncSpeedCode = getBusSpeedCode(config["DEFAULT"]["asyncBusSpeed"])
    isochSpeedCode = getBusSpeedCode(config["DEFAULT"]["isochBusSpeed"])
    if frameRateCode is None:
        raise ValueError("Unhandled frame rate ({}).".format(config["DEFAULT"]["frameRate"]))
    if videoModeCode is None:
        raise ValueError("Unhandled video mode ({}).".format(config["DEFAULT"]["videoMode"]))

    for ii in range(nCameras):
        # create and connect each camera
        cam = PyCapture2.Camera()
        cam.connect(bus.getCameraFromIndex(ii))
        # make sure the requested video mode is supported
        if not cam.getVideoModeAndFrameRateInfo(videoModeCode, frameRateCode):
            raise ValueError("Unsupported video mode/frame rate.")
        # set video mode and other settings before saving camera object
        cam.setVideoModeAndFrameRate(videoModeCode, frameRateCode)
        cam.setEmbeddedImageInfo(timestamp=config["DEFAULT"].getboolean("embedTimestamp"))
        cam.setEmbeddedImageInfo(frameCounter=config["DEFAULT"].getboolean("embedFrameCounter"))
        cam.setConfiguration(asyncBusSpeed=asyncSpeedCode)
        cam.setConfiguration(isochBusSpeed=isochSpeedCode)
        cameras[ii] = cam

    # all or nothing
    validated = validateCameras(cameras)
    return (validated, (nCameras if validated else 0))

def validateCameras(cameras):
    nCameras = len(cameras)
    userRateCode = getFrameRateCode(config["DEFAULT"]["frameRate"])
    userVideoCode = getVideoModeCode(config["DEFAULT"]["videoMode"])
    userAsyncCode = getBusSpeedCode(config["DEFAULT"]["asyncBusSpeed"])
    userIsochCode = getBusSpeedCode(config["DEFAULT"]["isochBusSpeed"])
    for ii in range(nCameras):
        cam = cameras[ii]
        cfg = cam.getConfiguration()

        # validation fails if the camera video mode/frame rate couldn't be set
        videoCode, rateCode = cam.getVideoModeAndFrameRate()
        if videoCode is not userVideoCode or rateCode is not userRateCode:
            print("cam{}: requested video mode/frame rate could not be set.".format(ii))
            return False

        # warn the user if async/isoch speed differ from requested config
        # note that these attribute names need an extra space at the end!
        asyncCode = getattr(cfg,"asyncBusSpeed ")
        isochCode = getattr(cfg,"isochBusSpeed ")
        if asyncCode is not userAsyncCode:
            print("cam{}: requested async bus speed could not be set.".format(ii))
        if isochCode is not userIsochCode:
            print("cam{}: requested isoch bus speed could not be set.".format(ii))
        if asyncCode is not userAsyncCode or isochCode is not userIsochCode:
            return False

    return True

def getFrameRateCode(frameRate):
    if frameRate == "30":
        return PyCapture2.FRAMERATE.FR_30
    elif frameRate == "60":
        return PyCapture2.FRAMERATE.FR_60
    else:
        return None

def getVideoModeCode(videoMode):
    if videoMode == "640x480_Y8":
        return PyCapture2.VIDEO_MODE.VM_640x480Y8
    else:
        return None

def getBusSpeedCode(busSpeed):
    if busSpeed == "S400":
        return PyCapture2.BUS_SPEED.S400
    elif busSpeed == "ANY":
        return PyCapture2.BUS_SPEED.ANY
    else:
        return None

def setSessionName():
    now = datetime.now()
    timestamp = "{:04}{:02}{:02}_{:02}{:02}{:02}".format(
        now.year, now.month, now.day, now.hour, now.minute, now.second)
    config["DEFAULT"]["sessionName"] = timestamp

def getTimestamp(datetime):
    return datetime.strftime("%Y-%m-%d %H:%M:%S.%f")

def getVideoExtension(videoType):
    if videoType not in validVideoTypes:
        raise ValueError("Invalid video type: {}.".format(type))
    else:
        return "mp4" if videoType == "H264" else "avi"

# output encoded value to LPT1 (address 0xE010)
def setAnalogOutputValue(value, pinMap, address):
    n = encodeNumber(value, pinMap)
    windll.inpoutx64.Out32(address, n)

def setAnalogOutputHigh(address):
    windll.inpoutx64.Out32(address, 255)

def setAnalogOutputLow(address):
    windll.inpoutx64.Out32(address, 0)

def getRandomFrameOffset(maxOffset, frameRate):
    return int(random.uniform(-maxOffset, maxOffset) * frameRate)

def captureVideo(idxCam, config, startEvent, abortEvent):
    nVideos = 0
    nFrames = 0
    videoType = config["DEFAULT"]["videoType"]
    videoDuration = config["DEFAULT"].getfloat("videoDuration")
    frameRate = config["DEFAULT"].getfloat("frameRate")
    nPulseFrames = int(config["DEFAULT"].getfloat("analogOutDuration") * frameRate)
    nPeriodFrames = int(config["DEFAULT"].getfloat("analogOutPeriod") * frameRate)
    nSessionFrames = int(config["DEFAULT"].getfloat("sessionDuration") * frameRate)
    nVideoFrames = int(videoDuration * frameRate)

    # initialize our random frame offset
    maxPeriodOffset = config["DEFAULT"].getfloat("analogOutPeriodRange")
    nOffsetFrames = nPeriodFrames + getRandomFrameOffset(maxPeriodOffset, frameRate)

    recordIndefinitely = nSessionFrames == 0

    ext = getVideoExtension(videoType)
    cameraName = "cam{:01}".format(idxCam)
    cameraPath = os.path.join(config["DEFAULT"]["dataPath"],
        config["DEFAULT"]["sessionName"], cameraName)
    processName = mp.current_process().name
    vid = PyCapture2.AVIRecorder()

    # get the analog input mapping for frame code output
    pinMap, maxValue = getAnalogPinMap(config["DEFAULT"]["analogPinMap"])
    address = int(config["DEFAULT"]["analogOutAddress"], base=16)
    analogValue = 1

    # get and connect the camera
    bus = PyCapture2.BusManager()
    camera = PyCapture2.Camera()
    camera.connect(bus.getCameraFromIndex(idxCam))

    # wait for the go signal
    startEvent.wait(0.5)
    camera.startCapture()
    time.sleep(0.1)

    capturingVideo = True
    while capturingVideo:
        # open up new video and log files
        videoFileName = "{}_{:06}".format(cameraName, nVideos)
        videoFilePath = os.path.join(cameraPath, "{}.{}".format(
            videoFileName, ext))
        logFilePath = os.path.join(cameraPath, "{}.txt".format(videoFileName))
        if videoType == "H264":
            vid.H264Open(filename=videoFilePath.encode("utf8"),
                width=640, height=480, framerate=frameRate,
                bitrate=config["DEFAULT"].getint("bitrateH264"))
        elif videoType == "MJPG":
            vid.MJPGOpen(filename=videoFilePath.encode("utf8"),
                framerate=frameRate, quality=config["DEFAULT"].getint("qualityMJPG"))
        elif videoType == "AVI":
            vid.AVIOpen(filename=videoFilePath.encode("utf8"), framerate=frameRate)

        with open(logFilePath, 'w') as log:
            # the frame of the first trigger
            lastTriggerFrame = 0

            # acquire and append camera images indefinitely until
            # the user cancels the operation
            for ii in range(nVideoFrames):
                # end session if recording duration exceeds user specified
                # duration or if user aborts
                if recordIndefinitely and abortEvent.is_set():
                    capturingVideo = False
                    break
                elif not recordIndefinitely and nFrames >= nSessionFrames:
                    capturingVideo = False
                    abortEvent.set()
                    break

                try:
                    # acquire camera image and stamp logfile
                    image = camera.retrieveBuffer()
                    vid.append(image)
                    log.write("{}\t{}\n".format(ii+1, getTimestamp(datetime.now())))
                    nFrames += 1
                except PyCapture2.Fc2error as error:
                    print("{}: error retrieving buffer ({}): dropping frame {}.".format(processName, error, ii))
                    continue
                except:
                    pass

                try:
                    if idxCam == 0:
                        # output an analog value to synchronize (and code info)
                        # set special analog value for start of files
                        if ii == 0:
                            setAnalogOutputValue(maxValue, pinMap, address)
                        elif ii in (2*nPulseFrames, 4*nPulseFrames):
                            setAnalogOutputValue(0, pinMap, address)
                        elif ii == 3*nPulseFrames:
                            setAnalogOutputValue(nVideos % (maxValue + 1), pinMap, address)
                        elif ii > 4*nPulseFrames and (ii - lastTriggerFrame) == nOffsetFrames:
                            setAnalogOutputValue(analogValue, pinMap, address)
                            analogValue = analogValue+1 if analogValue < maxValue else 1
                            lastTriggerFrame = ii
                        elif ii > 4*nPulseFrames and (ii - lastTriggerFrame) == nPulseFrames:
                            setAnalogOutputLow(address)
                            # set a new random trigger shift
                            nOffsetFrames = nPeriodFrames + getRandomFrameOffset(maxPeriodOffset, frameRate)

                except:
                    pass

        # save and write the last video file
        # note that this will silently fail if file size >2 GB!
        vid.close()
        try:
            print("\t\t{}: wrote {}.{} @ {}.".format(processName,
                videoFileName, ext, getTimestamp(datetime.now())))
        except:
            pass

        # increment the video counter (unless interrupted)
        if capturingVideo: nVideos += 1

def makeDirectories(nCameras):
    setSessionName()
    sessionPath = os.path.join(config["DEFAULT"]["dataPath"], config["DEFAULT"]["sessionName"])
    if not os.path.exists(sessionPath):
        try:
            os.makedirs(sessionPath)
            for idxCam in range(nCameras):
                os.makedirs(os.path.join(sessionPath, "cam{}".format(idxCam)))
            return True
        except:
            pass

    return False

def pinMapFromSpec(spec):
    pinMap = list(spec)
    for idx, e in enumerate(pinMap):
        pinMap[idx] = None if e == '-' else int(e)
    return pinMap

def getAnalogPinMap(spec):
    pinMap = pinMapFromSpec(spec)
    bitSlots = [int(k) for k in pinMap if k is not None]
    maxPower = max(bitSlots)
    maxValue = 2 ** (maxPower+1) - 1
    if len(bitSlots) != maxPower+1 or len(pinMap) != 8:
        raise ValueError("Invalid analog pin configuration: {}.".format(spec))

    return (pinMap, maxValue)

def encodeNumber(n, ainpMap):
    bits = "{:08b}".format(n)
    for idx, bidx in enumerate(ainpMap):
        if idx == 0: encoded = 0
        if bidx is not None: encoded = encoded + (2 ** idx)*int(bits[7-bidx])

    return encoded

def printSessionSummary(tStart, tEnd, sessionPath):
    totalSecs = (tEnd-tStart).total_seconds()
    if totalSecs > 86400:
        nDays, rem = divmod(totalSecs, 60*60*60)
        nHours, rem = divmod(rem, 60*60)
        nMins, nSecs = divmod(rem, 60)
        print("\n\tSession ended @ {} ({:0.0f} d {:0.0f} hr {:0.0f} min {:0.0f} sec).".format(
            getTimestamp(tEnd), nDays, nHours, nMins, nSecs))
    else:
        nHours, rem = divmod(totalSecs, 60*60)
        nMins, nSecs = divmod(rem, 60)
        print("\n\tSession ended @ {} ({:0.0f} hr {:0.0f} min {:0.0f} sec).".format(
            getTimestamp(tEnd), nHours, nMins, nSecs))

def listFilesInPath(path, fExt):
    if not os.path.isdir(path): return []
    return [(f, os.path.getsize(os.path.join(path,f))) for f in os.listdir(path)
        if f.endswith("." + fExt)]

def listCamDirsInPath(path):
    if not os.path.isdir(path): return []
    return [d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))
        and d.startswith("cam")]

def checkVideoData(sessionPath, nCameras):
    videoType = config["DEFAULT"]["videoType"]
    ext = getVideoExtension(videoType)
    namesAreDifferent = False

    # assume we're dealing with at least one camera (cam0)
    for ii in range(nCameras):
        cameraName = "cam{:0d}".format(ii)
        path = os.path.join(sessionPath, cameraName)
        vidFiles = listFilesInPath(path, ext)
        txtFiles = listFilesInPath(path, "txt")
        nVideos = len(vidFiles)
        nLogs = len(txtFiles)
        vidSize = sum(data[1] for data in vidFiles)/(1024*1024*1024)

        # nothing to do if no files
        if ii == 0 and not len(vidFiles[0]):
            print("\tNo files written.")
            return

        # check to see if filenames are different, and if they are, it's
        # likely the video file that has the extra -0000 prefix
        namesAreDifferent = len(vidFiles[0][0]) != len(txtFiles[0][0])
        # something's up if the number of text/avi files don't match
        diffVidTxtCount = nVideos != nLogs

        # rename video filenames
        if namesAreDifferent:
            for name in vidFiles:
                os.rename(os.path.join(path,name[0]), os.path.join(path,name[0].replace("-0000",'')))

        print("\t * {}: {} videos ({:1.1f} GB) [{}{}]".format(
            cameraName, nVideos, vidSize,
            'r' if namesAreDifferent else '-',
            'M' if diffVidTxtCount else '-'))

# adapted from https://gist.github.com/dideler/2395703
def getOptions(argv):
    opts = {}
    isValid = False
    while argv:
        # enforce name/value option pairs
        if not isValid:
            nArgs = len(argv)-1 % 2
            isValid = nArgs % 2 == 0
            if isValid:
                continue
            else:
                print("\tOptions must come in name/value pairs.")
                sys.exit(0)

        if argv[0][0] == "-":
            if argv[0] in opts:
                opts[argv[0]].append(argv[1])
            elif argv[0] in ('-r','-t'):
                opts[argv[0]] = [argv[1]]
            else:
                print("\tInvalid option: {}.".format(argv[0]))
                sys.exit(0)
        argv = argv[1:]
    return opts


# load configuration from file
# 1) there is some issue with libx264 (or Point Grey's libs) where
#    h264 MP4s are encoded at an extremely high rate (>30 Mbps)
#     => avoid using this format for now
# 2) MJPG: q85 ~ 11MB for 10s ~ 4GB for 1hr
# 3) trigger duration of 100 ms -> 3 frames @ 30 fps
config = configparser.ConfigParser()
config.read("config.ini")

# now set some options invisible to the end user
config["DEFAULT"]["asyncBusSpeed"] = "ANY"
config["DEFAULT"]["isochBusSpeed"] = "S400"
config["DEFAULT"]["sessionDuration"] = "0"

validVideoTypes = ("H264", "MJPG", "AVI")
validVideoModes = ("640x480_Y8")

if __name__ == "__main__":

    from sys import argv
    options = getOptions(argv)

    if "-r" in options:
        # check the directory offered by the user, look for cam* directories
        sessionPath = options["-r"][0]
        dirs = listCamDirsInPath(sessionPath)
        if len(dirs) > 0:
            print("\n\tExisting video directory: {}".format(sessionPath))
            nCameras = len(dirs)
        else:
            print("\n\tNo camera folders found in this directory.")
            sys.exit(0)
    else:
        # record indefinitely unless the user specifies a session duration
        if "-t" in options: config["DEFAULT"]["sessionDuration"] = options["-t"][0]
        address = int(config["DEFAULT"]["analogOutAddress"], base=16)
        setAnalogOutputLow(address)
        camerasStarted, nCameras = initializeCameras()
        directoriesMade = makeDirectories(nCameras)
        if camerasStarted and directoriesMade:
            sessionPath = os.path.join(config["DEFAULT"]["dataPath"], config["DEFAULT"]["sessionName"])
            # copy the current configuration file into the session directory
            with open(os.path.join(sessionPath,"config.ini"), 'w') as configfile:
                config.write(configfile)
            print("\n\tCameras ({}) initialized successfully.".format(nCameras))
            print("\tVideo directory: {}".format(sessionPath))
        else:
            if not camerasStarted: print("\n\tCamera initialization failed.")
            elif not directoriesMade: print("\n\tCould not create directories.")
            sys.exit(0)

        # capture start/abort events
        startEvent = mp.Event()
        abortEvent = mp.Event()

        processes = []
        for ii in range(nCameras):
            processName = "p-cam{}".format(ii)
            p = mp.Process(name=processName, target=captureVideo,
                args=(ii, config, startEvent, abortEvent))
            p.start()
            processes.append(p)

        # send the start capture signal
        time.sleep(0.1)
        tStart = datetime.now()
        startEvent.set()
        print("\tSession started @ {}.\n".format(getTimestamp(tStart)))

        tEnd = None
        # main thread waits around until interrupted by the user
        while not abortEvent.is_set():
            try:
                time.sleep(0.1)
            except KeyboardInterrupt:
                print("\tAborting video capture.")
                abortEvent.set()
                tEnd = datetime.now()
                setAnalogOutputLow(address)

        # if we reached this point and tEnd wasn't set, the session had a
        # fixed duration (specified by the user)
        if tEnd is None:
            tEnd = datetime.now()
            setAnalogOutputLow(address)

        time.sleep(0.1)

        # summarize video data and correct filenames if needed
        printSessionSummary(tStart, tEnd, sessionPath)

    checkVideoData(sessionPath, nCameras)
    sys.exit(0)
