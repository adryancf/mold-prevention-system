# Mold Prevention System

Embedded real-time system for indoor humidity and temperature monitoring and control, developed for the Systems Operating Systems course.

## Overview

This project uses an ESP32 running FreeRTOS to monitor temperature and humidity with a DHT22 sensor. The system processes the readings in concurrent tasks, controls representative actuators through LEDs, and communicates with a desktop application using sockets.

The desktop application, written in Python, displays live data, charts, and system status, and also allows the user to configure operating thresholds remotely.

## Main Features

- Real-time environmental monitoring.
- Multitasking with FreeRTOS.
- Inter-task communication using queues, semaphores, and mutexes.
- Socket-based communication with a desktop application.
- Python desktop interface for visualization and configuration.

## Technologies

- ESP32
- FreeRTOS
- DHT22
- Python
- Sockets

## Course Context

Project developed for the Operating Systems course at UTFPR.
