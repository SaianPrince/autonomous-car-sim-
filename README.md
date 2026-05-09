# Autonomous Driving Simulation

A real-time autonomous driving simulation built with **C++ (SFML)** and **Python (OpenCV)** using TCP socket communication.

This project simulates an autonomous vehicle that detects lane boundaries, identifies obstacles, and performs automatic lane changes in real time.

## Features
- Real-time lane detection
- PID-based steering control
- Red obstacle detection using HSV color segmentation
- Automatic lane changing / obstacle avoidance
- Closed-loop autonomous driving system
- Live debug visualization windows
- TCP socket communication between C++ and Python

## Technologies Used
- C++
- SFML 2.6.1
- Python
- OpenCV
- NumPy
- WinSock TCP sockets

## System Architecture

### C++ Simulation Module
- Creates the driving environment
- Draws the multi-lane road
- Captures the road view (ROI) in front of the vehicle
- Sends raw RGBA image frames to Python
- Receives steering commands
- Updates vehicle movement

### Python Vision / AI Module
- Receives image frames from C++
- Detects lane boundaries
- Detects red obstacles
- Calculates steering angles
- Sends commands back to the simulation

## Screenshots

### Simulation Images
![Simulation](image1.png)

![Simulation](image2.png)

![Simulation](image3.png)

![Simulation](image4.png)

![Simulation](image5.png)

## How It Works
1. The C++ simulation continuously captures the road view in front of the vehicle.
2. The captured frame is sent to Python via TCP socket communication.
3. Python processes the frame using OpenCV.
4. Lane boundaries are detected.
5. Red obstacles are detected.
6. Steering commands are calculated.
7. Commands are sent back to C++.
8. The vehicle autonomously changes lanes and continues driving.

## Run Order

Start the Python AI server first:

```bash
python brain.py
```

Then run the C++ simulation (`main.cpp`) from Visual Studio (or another IDE).

⚠️ Python must be started before the C++ application, otherwise the socket connection will fail.

## Future Improvements
- YOLO-based object detection
- Multiple moving obstacles
- Dynamic traffic simulation
- Better lane tracking
- More realistic vehicle physics
