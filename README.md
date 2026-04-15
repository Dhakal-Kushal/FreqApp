# Note Detector Pro: Real-Time Audio Analysis & Tuning

Note Detector Pro is a real-time audio analysis tool developed as passion project of mine. The app combines my love for programming and my interest in learning to play music.

![Project Demo](demo/demo.gif)

## Project Overview
The primary goal of this project was to explore how software can handle live inputs from peripherals. By capturing audio and applying pitch-tracking algorithms, the app provides immediate feedback on musical notes and their precision relative to standard tuning.

## Core Functionality
* **Real-Time Note Detection**: Instantly identifies the fundamental frequency of an audio source and converts it into its corresponding musical note.
* **Visual Tuning Gauge**: Features a custom-built interface that displays "cents" deviation (±50¢), allowing users to see exactly how sharp or flat a note is.
* **Scale Verification**: Includes a system that validates whether the detected note fits within a user-selected key and scale, such as Major, Minor, Pentatonic, Blues, or Chromatic.
* **Data Management**: Automatically logs performance history and allows users to export their session data to a CSV file for future review.

## AI Collaboration & Learning
Throughout the development process, I utilized AI as a collaborative tool to help navigate complex technical requirements and accelerate my learning in specific domains:

* **Tuning Needle Logic**: I leveraged AI to implement the mathematical calculations required to translate pitch deviation into visual movement on the canvas. This ensured the needle accurately reflects tuning status in real-time.
* **GUI Construction**: Designing a responsive layout for live data can be challenging in Tkinter. AI assisted in organizing the interface components to ensure the graph and history logs remained aligned and user-friendly.
* **Concurrency & Threading**: Managing a microphone feed while keeping the user interface active requires multiple "threads" of execution. AI played a critical role in helping me understand how to implement background threads safely, preventing the application from freezing or crashing during audio capture.

## Development Highlights
* **Efficient Visualization**: The app uses optimized data structures like deques to ensure the "Pitch over Time" graph remains smooth and responsive during long sessions.
* **Algorithm Integration**: By incorporating the Praat pitch-tracking method via the `parselmouth` library, the tool achieves higher accuracy for human voice and acoustic instruments than standard detection methods.