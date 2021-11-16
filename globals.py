#------
# 
# globals.py
#
# Contains:
#    * color definitions
#    * the mapping between face matches from webcam/OpenCV and songNum
#
#
# Version log:
# -----------
# 30-Aug-2021 Mitch:  Initial version.
# 31-Aug-2021 Mitch:  Added morris_albert and dianna_ross.
#                     Added colors, createColorBoxImg(), drawStar()
# 8-Sep-2021  Mitch:  Changed songNumTab to make use of song numbers 0 through 4.
#
#==================================================
#==================================================
#   This project is Open Hardware
#   This work is licenses under the 
#   Creative Commons Attribution-ShareAlike 4.0
#   CC BY-SA 4.0
#   To view a copy of this license, visit
#   https://creativecommons.org/licenses/by-sa/4.0/
#==================================================
#==================================================



import numpy as np
import math
import cv2



global RED
global GREEN
global BLUE
global YELLOW
global MAGENTA
global PURPLE
global FLASH
global CARNIVAL
global VERMILLION_ORANGE
global LEMON_CHROME
global GRASS_GREEN
global CAPRI
global CYAN_BLUE
global BRIGHT_VIOLET
global PLUM
global HOT_PINK

# color definitions (R,G,B)

RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0)
MAGENTA = (255, 0, 255)
PURPLE = (76, 0, 153)
FLASH = (235, 40, 72)                # bright red
CARNIVAL = (252, 79, 75)             # red-orange
VERMILLION_ORANGE = (242, 122, 21)   # orange
LEMON_CHROME = (255, 211, 0)         # yellow
GRASS_GREEN = (130, 199, 118)        # pale green
CAPRI = (4, 202, 175)                # green-blue
CYAN_BLUE = (1, 174, 214)            # turquoise
BRIGHT_VIOLET = (117, 76, 155)       # purple
PLUM = (153, 42, 110)                # red-purple
HOT_PINK = (242, 122, 157)           # hot pink



#--------------------------------------------------
#--------------------------------------------------
#
# createColorBoxImg(width, height, rgb_color=(0, 0, 0))
#
#     Create a new box image for OpenCV functions
#        with the given width and height (in pixels)
#        that is filled with a given color given as (R,G,B).
#
#     returns the filled image
#
#
# This function is taken from the algorithm in 
#     "Opencv Code for Drawing a Star"the algorithm"  (written in C)
#        by Arjun Toshniwal 
# https://opencv-tutorials-hub.blogspot.com/2015/12/opencv-code-for-drawing-star-by-joining-lines-example.html
#
#--------------------------------------------------
#--------------------------------------------------

def createColorBoxImg(width, height, rgb_color=(0, 0, 0)):

    # Create a new image(numpy array) filled with black
    image = np.zeros((height, width, 3), np.uint8)

    # Since OpenCV uses BGR, convert the color first
    color = tuple(reversed(rgb_color))

    # Fill image with color
    image[:] = color

    return image



#--------------------------------------------------
#--------------------------------------------------
#
# drawStar(image, size, xpos, ypos, rgb_color=(0, 0, 0))
#
#     draw a star in the give image
#        with the given size (in pixels)
#        and the given x position and y position
#        that is filled with a given color given as (R,G,B).
#
#     returns the new image
#
#--------------------------------------------------
#--------------------------------------------------

def drawStar( image, size, xpos, ypos, rgb_color=(0, 0, 0) ):

    # convert from RGB to BGR (which is used by OpenCV)
    color = tuple(reversed(rgb_color))

    # create constants for trig functions needed for calculating end points of the lines that form the star
    a = int( size / ( 1 + math.cos( math.pi * 54 / 180 ) ) )
    b = int( a * math.cos( math.pi * 72 / 180) )
    c = int( a * math.sin( math.pi * 72 / 180) )

    # draw the 5 lines that comprise the star
    img = cv2.line(image, (0+xpos,size-c+ypos), (size+xpos,size-c+ypos), color, 5)
    img = cv2.line(image, (size+xpos,size-c+ypos), (b+xpos,size+ypos), color, 5)
    img = cv2.line(image, (b+xpos,size+ypos), ((int(size/2))+xpos,0+ypos), color, 5)
    img = cv2.line(image, ((int(size/2))+xpos,0+ypos), (size-b+xpos,size+ypos), color, 5)
    img = cv2.line(image, (size+xpos-b,size+ypos), (0+xpos,size-c+ypos), color, 5)

    return img



#============================================================

global SONG_NAME, SONG_NUM
global numElementsInSongNumTab
global songNumTab

# This is a list of names and the song numbers associated with them.
# This is used or translating names of matched faces to the songNum to play on the synths.
# How to use songNumTab:
#    once we have a name matched with a face, we search through all of the names in songNumTab by indexing through 
#        songNumTab[SONG_NAME][index]  which gives the name in the indexed entry of songNumTab
#    then, using the same index, we look in
#        songNumTab[SONG_NUM][index]   which gives the song number to play.
#    If the song number = "R", then we will choose a random song number to play.
SONG_NAME = 0
SONG_NUM = 1
songNumTab = [
    ["adrian", "ali_macgraw", "barry_manilow", "bert_kaempfert", "billy_joel", "catherine_deneuve", "claude_ciari", "dianna_ross", "frank_sinatra", "henry_mancini", "herb_alpert", "ian_malcolm", "michel_legrand", "mitch", "morris_albert", "robert_kool_bell", "sandra_dee", "walter_wanderley", "Unknown"],
#   ["9",      "12",          "0",             "10",             "1",          "8",                 "3",             "4",           "7",            "12",            "6",           "5",           "8",              "R",     "4",             "2",                "10",         "11",               "R"      ]
    ["0",      "1",           "2",             "3",              "4",          "0",                 "1",             "2",           "3",            "4",             "0",           "1",           "2",              "R",     "3",             "4",                "0",          "1",                "R"      ]
]
numElementsInSongNumTab = len(songNumTab[SONG_NAME])



# Planned songs (assuming I have enough time to enter the music and lyrics):
#
#      Num  Song                     face match           alternate face match
#      ---  ----------------------   -----------------    --------------------
#       0   Mandy                    barry_manilow
#       1   Piano Man                billy_joel
#       2   Celebration              robert_kool_bell
#       3   La Playa                 claude_ciari
#       4   Feelings                 dianna_ross            morris_albert
#       5   This Guy's In Love       ian_malcolm
#       6   Taste of Honey           herb_alpert
#       7   I Did It My Way          frank_sinatra      
#       8   I Will Wait for You      catherine_deneuve      michel_legrand
#       9   Spiritual Voyage         adrian
#      10   Strangers in the Night   bert_kaempfert         sandra_dee
#      11   Summer Samba             walter_wanderley
#      12   Theme from Love Story    ali_macgraw            henry_mancini
#
#       R   Random                   mitch                  Unknown
#
# The 1st and 2nd row of songNumTab reflect the above.  
#    (But, for now, the 2nd line is commented out.)
# The 3rd line is for temporary songNum matching while songs are being composed.
