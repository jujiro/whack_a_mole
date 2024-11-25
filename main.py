#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2017-18 Richard Hull and contributors
# See LUMA_LICENSE.rst for details. (For luma libraries)

import re
from inputimeout import inputimeout, TimeoutOccurred
from multiprocessing import Process, Value
from random import randint

from luma.led_matrix.device import max7219
from luma.core.interface.serial import spi, noop
from luma.core.render import canvas
from luma.core.virtual import viewport
from luma.core.legacy import text, show_message
from luma.core.legacy.font import proportional, CP437_FONT, TINY_FONT, SINCLAIR_FONT, LCD_FONT

from gpiozero import LED, Button, BadPinFactory
from time import sleep, perf_counter
from sys import exit

class GameState:
  btns = []
  leds = []
  matrix = None
  current_state = "init"
  previous_state = "???"
  next_state = None
  score = 0
  matrix_process = None
  core_parallel_process = None
  addl_parallel_process_1 = None
 
class GameButton:
  button_pin = None
  btn=None
  btn_pressed_time=0.0
  
class GameLED:
  led_pin = None
  led=None
 
MAX_LED_AND_BUTTONS = 5
BTN_LED_PINS=[
  #Btn GPIO pin, LED GPIO pin, LED color
  [17,18, "green"],
  [27,22, "yellow"],
  [23,24, "white"],
  [13,12, "red"],
  [5,6, "blue"]
]

GREEN="green"
YELLOW="yellow"
WHITE="white"
RED="red"
BLUE="blue"

IDLE="idle"
DEBUG="debug"
PLAYING="playing"
PROMPT_TO_STOP="prompt_to_stop"
PROMPT_TO_RESET="prompt_to_reset"
PROMPT_TO_SHUTDOWN="prompt_to_shutdown"
PAUSED="paused"
RESUMEPLAYING="resume_playing"
SHUTTINGDOWN="shuttingdown"

global game_state
game_state=GameState()
  
def reset_matrix():
  device=game_state.matrix
  if  not game_state.matrix_process is None:
    game_state.matrix_process.kill()
    game_state.matrix_process=None
    device.clear()

def reset_leds():
  for o in game_state.leds:
    o.led.off()

def reset_all_displays():
  reset_leds()
  reset_matrix()  

def initialize_hardware():
  try:
    for x in range(MAX_LED_AND_BUTTONS):
      b=GameButton()
      l=GameLED()
      # Customize as necessary
      b.button_pin=BTN_LED_PINS[x][0]
      l.led_pin=BTN_LED_PINS[x][1]
      b.btn=Button(b.button_pin, hold_time=2)
      #Wire the button events
      b.btn.when_pressed = process_button_pressed
      b.btn.when_released = process_button_released
      b.btn.when_held = process_button_held_long
      b.btn.hold_repeat=False
      l.led=LED(l.led_pin)
      #
      game_state.leds.append(l)
      game_state.btns.append(b)
      # create matrix device
      serial = spi(port=0, device=0, gpio=noop())
      device = max7219(serial, cascaded=4, block_orientation=-90, rotate=0, blocks_arranged_in_reverse_order=False)
      game_state.matrix=device
  except BadPinFactory:
    pass

def activate_state(state, tgt=None, tgt_args=None):
  print(f"Activating state {state} from {game_state.current_state}")
  game_state.previous_state=game_state.current_state
  game_state.current_state=state 
  p = Process(target=dummy_controller if tgt is None else tgt, args=() if tgt_args is None else tgt_args)
  p.start()
  game_state.core_parallel_process = p
  p.join()

def set_next_state(next_state=None):
  print(f"Terminating state {game_state.current_state} starting {next_state}")
  if not next_state is None:
    game_state.next_state=next_state
  if  not game_state.addl_parallel_process_1 is None:
    game_state.addl_parallel_process_1.kill()
    game_state.addl_parallel_process_1=None
  reset_all_displays()    
  if not game_state.core_parallel_process is None:
    game_state.core_parallel_process.kill()
    game_state.core_parallel_process=None

def dummy_controller():
  while True:
    sleep(1)

def set_idle_state():
  show_message_async("Ready to play?  Press any button to start.",True,)
  activate_state(IDLE, show_blinking_leds, (game_state.leds,))

def get_button_led_index(btn_pin_number):
  for i in range(MAX_LED_AND_BUTTONS):
    if BTN_LED_PINS[i][0]==btn_pin_number:
      return i
  return None

def set_prompt_to_shutdown():
  show_message_async("Shutdown game? Green=Yes, Red=No", True)
  for i in range(MAX_LED_AND_BUTTONS):
    color=BTN_LED_PINS[i][2]
    if  color in [RED, GREEN]:
      game_state.leds[i].led.on()
    else:
      game_state.leds[i].led.off()
  activate_state(PROMPT_TO_SHUTDOWN)
  
def prompt_to_reset():
  show_message_async("Reset game? Green=Yes, Red=No", True)
  for i in range(MAX_LED_AND_BUTTONS):
    color=BTN_LED_PINS[i][2]
    if  color in [RED, GREEN]:
      game_state.leds[i].led.on()
    else:
      game_state.leds[i].led.off()
  activate_state(PROMPT_TO_RESET)
  
def loop_game_cycle(leds, score):
  while True:
    device=game_state.matrix
    device.clear()
    with canvas(device) as draw:
      text(draw, (0, 0), f"{score.value}", fill="white")
    lit=randint(0, MAX_LED_AND_BUTTONS-1)
    for x in range(MAX_LED_AND_BUTTONS):
      if x==lit:
        leds[x].led.on()
      else:
        leds[x].led.off()
    sleep(.5) #This should be variable

def set_state_to_playing(resume=False):
  if not resume:
    game_state.score=Value('i', 0)
    device=game_state.matrix
    with canvas(device) as draw:
        text(draw, (0, 0), "1", fill="white")
    sleep(.5)

    with canvas(device) as draw:
        text(draw, (8, 0), "2", fill="white")
    sleep(.5)

    with canvas(device) as draw:
        text(draw, (16, 0), "3", fill="white")
    sleep(.5)

    with canvas(device) as draw:
        text(draw, (8, 0), "Go!", fill="white")
    sleep(.5)   
  activate_state(PLAYING, loop_game_cycle, (game_state.leds,game_state.score,))

def process_button_released(btn):
  i=get_button_led_index(btn.pin.number)
  btn=game_state.btns[i]
  btn_held_time=perf_counter() - btn.btn_pressed_time
  if btn_held_time < 2.0:
    mimic_button_pressed(i)
    return
    
def process_button_pressed(btn):
  i=get_button_led_index(btn.pin.number)
  game_state.btns[i].btn_pressed_time=perf_counter()
  
def process_button_held_long(btn):
  i=get_button_led_index(btn.pin.number)
  btn=game_state.btns[i]
  btn_color=BTN_LED_PINS[i][2]
  if game_state.current_state==PLAYING:
    if  btn_color==RED:
      set_next_state(IDLE)
      return
  if game_state.current_state==IDLE:
    if  btn_color==RED:
      set_next_state(PROMPT_TO_SHUTDOWN)
      return
  if game_state.current_state==PLAYING:
    if btn_color==YELLOW:
      set_next_state(PAUSED)
      return  

def mimic_button_pressed(led_index):
  btn_color=BTN_LED_PINS[led_index][2]
  led=game_state.leds[led_index].led
  if game_state.current_state==IDLE:
    set_next_state(PLAYING)
    return
  if game_state.current_state==PROMPT_TO_RESET:
    if btn_color==GREEN:
      set_next_state(IDLE)
      return
    elif btn_color==RED:
      set_next_state(RESUMEPLAYING)
      return
  elif game_state.current_state==PROMPT_TO_SHUTDOWN:
    if btn_color==GREEN:
      set_next_state(SHUTTINGDOWN)
      return
    elif btn_color==RED:
      set_next_state(game_state.previous_state)
      return
  elif game_state.current_state==PAUSED:
    if btn_color==YELLOW:
      set_next_state(RESUMEPLAYING)
      return
  if game_state.current_state==PLAYING:
    if  led.value:
      game_state.score.value+=1

def show_message_after_clear(device, msg, loop=False):
  while  True:
    device.clear()
    show_message(device, msg, fill="white")
    if not loop:
      break
    sleep(.25)
  
# Use this to invoke marquee like function.  Displaying a scrolling message is a blocking call.
# Using multiprocessing, we are going to make this call asynchronous.
def show_message_async(msg, loop=False):
  reset_matrix()
  p = Process(target=show_message_after_clear, args=(game_state.matrix,msg,loop,))
  p.start()
  game_state.matrix_process=p

def show_blinking_leds(leds):
  while True:
    for x in range(4):
      y=range(MAX_LED_AND_BUTTONS)
      if (x % 2) != 0:
        y=reversed(range(MAX_LED_AND_BUTTONS))
      for i in y:
        o=leds[i]
        o.led.on()
        sleep(0.2)
        o.led.off()
    # Now blink all LEDs four times
    for x in range(4):
      for o in leds:
        o.led.on()
      sleep(0.2)
      for o in leds:
        o.led.off()
      sleep(0.2)
  
def set_game_to_pause():
  for x in range(MAX_LED_AND_BUTTONS):
    if  BTN_LED_PINS[x][2]==YELLOW:
      game_state.leds[x].led.blink()
    else:
      game_state.leds[x].led.off()
  activate_state(PAUSED)

def main():
  initialize_hardware()
  game_state.next_state=IDLE
  while True:
    if game_state.next_state==SHUTTINGDOWN:
      break
    if game_state.next_state==IDLE:
      set_idle_state()
    elif game_state.next_state==PLAYING:
      set_state_to_playing()
    elif game_state.next_state==PAUSED:
      set_game_to_pause()
    elif game_state.next_state==RESUMEPLAYING:
      set_state_to_playing(resume=True)
    elif game_state.next_state==PROMPT_TO_RESET:
      prompt_to_reset()
    elif game_state.next_state==PROMPT_TO_SHUTDOWN:
      set_prompt_to_shutdown()

if __name__ == "__main__":
  main()
