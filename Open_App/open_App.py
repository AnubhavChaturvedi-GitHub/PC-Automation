import pyautogui as gui
import subprocess
import time

def open_App():
    text = input("Please enter the app name:")
    try:
       subprocess.run(text)
    except Exception as e:
        gui.press("win")
        time.sleep(0.2)
        gui.write(text)
        time.sleep(0.2)
        gui.press("enter")