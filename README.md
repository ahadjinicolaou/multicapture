# Overview
This Python 3 program interfaces with multiple Point Grey cameras to capture video. It makes use of the parallel port to send analog signals that can be used for synchronization.

# Requirements
Multicapture was developed under Windows 10 (64-bit) using Python 3.5, FlyCapture v2.12.3.2, and PyCapture v2.11. It should generally run under versions of Python 3+, although the code may be sensitive to the particular versions of Fly/PyCapture you are using (see [Point Grey's site](https://www.ptgrey.com/support/downloads) for details).

The output of parallel port signals requires the installation of [InpOut32 and InpOutx64](http://www.highrez.co.uk/downloads/inpout32/), and a copy of inpoutx64.dll from the linked package to be located in the same directory as the Python script.

# Operation
Running `python multicapture.py` will create a timestamp-like session directory (`YYYYMMDD_HHMMSS`) within the `datapath` directory specified in `config.ini`. Within the session directory, each connected camera will have its own subdirectory, e.g in the case of three cameras:

- `<datapath>\20180316_102100\cam0`
- `<datapath>\20180316_102100\cam1`
- `<datapath>\20180316_102100\cam2`

Each output video file (e.g. `cam0_000168.avi`) will be accompanied by a frame timing file (e.g. `cam0_000168.txt`) which stores a) the frame number and b) the time at which the frame was written to disk.

The program will acquire video indefinitely until it receives a keyboard interrupt via CTRL-C, after which the current video file will be finalized and a summary of the captured video data will be printed.

To record video for a fixed duration (seconds), run the command:
`python multicapture_console.py -t <duration>`

# Issues
Unfortunately, as of the time of writing, the video files are initially prefixed with "-0000" (e.g. `cam0_000168-0000.avi`) after closure. To accommodate for this, at the end of each recording session, the video filenames are checked against the frame timing filenames and renamed accordingly.

If the program is terminated without a keyboard interrupt, thus leaving the video files with their original filenames intact, they can be renamed by running the command:
`python multicapture_console.py -r "<sessionpath>"`
