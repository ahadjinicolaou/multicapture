# Overview
This Python 3 program interfaces with multiple Point Grey cameras to capture video. It makes use of the parallel port to send analog signals that can be used for synchronization. This requires the installation of [InpOut32 and InpOutx64](http://www.highrez.co.uk/downloads/inpout32/), and a copy of inpoutx64.dll from the linked package to be located in the same directory as the Python script.

# Requirements
Multicapture was developed under Windows 10 using Python 3.5, FlyCapture v2.12.3.2, and PyCapture v2.11. It should generally run under versions of Python 3+, although the code may be sensitive to the particular versions of Fly/PyCapture you are using (see [Point Grey's site](https://www.ptgrey.com/support/downloads) for details).
