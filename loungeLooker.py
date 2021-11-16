#------
#
# loungLooker.py
#
# Using a webcam to "look" at the face of the person in front of it,
#    "choose" a song to play
#    on three ArduTouch boards, and speak lyrics ("sing along") using eSpeak while the song is playing.
#
# This Python 3 program was created to run on a Raspberry Pi 4 with 8GB RAM.
# It has a 32GB micro SD card with 100MB/s speed (SanDisk Extreme microSDHC UHS-I A1).
#
# This program requires an external square wave generator 
#    to provide interrupts every 50ms.
#
# The "singing" (actually, just speaking) of the lyrics is done with eSpeak Text To Speach engine.
#
# This program requires a USB webcam compatible with Raspberry Pi 4.
# Currently in use:  Microsoft LifeCam HD-3000
#
#------
#
# To generate an external square wave for producing interrupts on the Raspberry Pi
#   I use a NodeMCU-ESP32 DEVKITV1 board.
#
# The ESP32 generates a square wave with a 50ms period (25ms High / 25ms Low).
#       This assumes that:
#           a whole note is 800ms
#           a half note is 400ms
#           a quater note is 200ms
#           an eighth note is 100ms
#           a sixteenth note is 50ms
#
# The ESP32 GPIO4 pin goes to the Raspberry Pi GPIO23 pin (16)
#   set up to generate an interrupt on every falling edge.
#
# The hardware for this:
#      ESP32 pin     RPi pin
#      ---------  ------------
#         VIN          5V (2)
#         GND         GND (14)
#          D4      GPIO23 (16)
#
#
# The processor gets hot, and requires a fan.
# I use a Joy-It Magnetic Plastic Case with Dual Fan (article #:  RB-CaseP4+03B):
#      Fan wire      RPi pin
#      --------   ------------
#         Red          5V (4)
#        Black        GND (14)
#
# 
# The three ArduTouch synth boards are connected to the Rasberry Pi 4
#    through ttyUSB0, ttyUSB1, and USBtty2
#       ttyUSB0 -- Thick
#       ttyUSB1 -- Hocus
#       ttyUSB2 -- Dronetic
#
#  -------------   -------------   ---------------
#  |           |   |           |   |             |
#  |  ttyUSB2  |   |  ttyUSB0  |   |             |
#  |  Dronetic |   |   Thick   |   |             |
#  -------------   -------------   |             |
#  -------------   -------------   |   Ethernet  |
#  |           |   |           |   |             |
#  |    hub    |   |  ttyUSB1  |   |             |
#  |           |   |   Hocus   |   |             |
#  -------------   -------------   ---------------
#
# The hub is a Hama 4-port USB hub, with 4 female USB-A inputs and one male USB-A output.
#    A Raspberry Pi keyboard and a Logitech mouse and the Microsoft LifeCam HD-3000 are plugged into the hub.
#
#
# Version log:
# -----------
# 23-Aug-2021 Mitch:  Plays notes for all three synths from song lists.  
#                     Need to add duration of notes and rests.
# 23-Aug-2021 Mitch:  Plays notes for all three synths from song lists.  Durations now working.
# 24-Aug-2021 Mitch:  Added "singing" of lyrics using eSpeak Text To Speech engine.
#                     Problem:  Calling eSpeak is blocking, so it prolongs any notes being played on the synths.
# 25-Aug-2021 Mitch:  To lessen problem of eSpeak blocking, when send a word to eSpeak, set the other 3 synths TickCounts to 0 (so thez don't play so long).
#                     Create and use low-level functions for sending info to serial ports to play ArduTouch synths.
#                     Added setting volume level for each note played.
#                     Fix bug: last note to play on each synth didn't play for its full duration.
# 26-Aug-2021 Mitch:  Fix bug: I don't know why, but stopping notes in shutDownSynthPlaying() 
#                     made it so taht subsequent restarts of this program 
#                     wouldn't play synth 0 (Thick) or synth 1 (Hocus), so I commented that out.
# 26-Aug-2021 Mitch:  Comment out DEBUG prints.
#                     Add infinite loop to cycle through the three songs.
# 27-Aug-2021 Mitch:  Fix bug: Added and made use of physical reset (toggling serial port RTS line) to fix syths getting into weird states after repeated playing of songs.
# 28-Aug-2021 Mitch:  Fix bug: resetSynth() now works for all portNum.
#
# 30-Aug-2021 Mitch:  Convert playSongsSing.py into this program (loungeLooker.py).
# 31-Aug-2021 Mitch:  Add mod graphics window for displaying text.
#  1-Sep-2021 Mitch:  Added stripes to right of graphics windows for a more filled in mod look.
#  7-Sep-2021 Mitch:  Updated comments for wiring of fan, ESP32.
#                     Start adding "Strangers in the Night".
#  8-Sep-2021 Mitch:  Finish adding "Strangers in the Night".
#  8-Sep-2021 Mitch:  Add "Theme from Love Story".
#  8-Sep-2021 Mitch:  Add "This Guy's in Love", place holders for "My Way" and "Moon River".
#                     Removed DEBUG statements.
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


# import the necessary packages
import time
import serial
from subprocess import call
from os import system, name
import RPi.GPIO as GPIO
import lookChoose as lc
import modGraphicTextWindow as mgtw



#--------------------------------------------------
#--------------------------------------------------
#
# metronome  --  threaded callback function (Interrupt Service Routine)
#
# This executes every falling edge on GPIO23 (pin 16).
# GPIO23 is connected to ESP32 generating a square wave with a period of 50ms.
#
# To set up GPIO23 (pin 16) as input with pull-up resistor enabled:
#      GPIO.setup(23, GPIO.IN, pull_up_down=GPIO.PUD_UP)
# To start interrupts for every falling edge on GPIO23:
#      GPIO.add_event_detect(23, GPIO.FALLING, callback=metronome)
# To stop interrupts on GPIO23:
#      GPIO.remove_event_detect(23)
#
# This function is executed every "tick" (a "tick" is a falling edge of the square wave on GPIO 23).
# This function does the following:
#    * Read info from the song list for the next note to play on each synth.
#    * Play the notes or rests on the three synths at the given volumes for the given durations.
#    * The duration is given as a number of ticks.  
#      The choices are
#           16 (whole note), 8 (half note), 4 (quarter note), 2 (eighth note), 1 (sixteenth note)
#      so, unless a note has a duration of a sixteenth note (1 tick)
#      the note or rest will play for multiple execution cycles of this function.
#    * eSpeak (for speaking the lyrics) is considered another synth, but it is software.
#
# To determine the end of the song for each synth:
#    After starting to play the last note of the song for the synth, 
#        lastNotePlaying for the synth is set True.
#    After the last note for the song for the synth finished its duration, 
#        endOfSongSynth for the synth is set True
#        and the note is stopped.
# We do not need to deal with this for eSpeak (synth3), since the lyric words don't have duration.
#
# NOTE:  It takes about 1 second for eSpeak to be called, say its word, and return.
#        And eSpeak is blocking, so, no notes are updated for any of the 3 ArduTouch synths 
#        while eSpeak is doing its thing.  
#
#        So, as a way to help (but not really fix) this problem, when a word is sent to eSpeak,
#        all of the other synth's TickCounts are set to 0.
#
#--------------------------------------------------
#--------------------------------------------------

def metronome(channel):

    global count   # DEBUG
    global metronomeON
    global noteCount0, noteCount1, noteCount2, noteCount3
    global songList
    global songChoice
    global endOfSongSynth0, endOfSongSynth1, endOfSongSynth2, endOfSongSynth3
    global synth0TickCount, synth1TickCount, synth2TickCount, synth3TickCount
    global lastNotePlaying0, lastNotePlaying1, lastNotePlaying2

    # If the metronome isn't on, then do nothing.
    if ( not metronomeON ):
        pass

    # If the metronome is on, then play notes.
    else:
        #print ("\nTICK", count, endOfSongSynth0, endOfSongSynth1, endOfSongSynth2, endOfSongSynth3, 
                #"  synthTickCount: ", synth0TickCount, synth1TickCount, synth2TickCount, synth3TickCount, 
                #"  noteCount:", noteCount0, noteCount1, noteCount2, noteCount3)   # DEBUG

        # synth 0 (Thick):
        # If synth 0 is still active for this song then play notes from the song on this synth.
        if ( not endOfSongSynth0 ):
            # If synth0TickCount is 0, then it is time to send the next note to the Thick synth on ttyUSB0,
            # otherwise, simply decriment synth0TickCount so that the note keeps playing.
            if ( synth0TickCount != 0 ):
                synth0TickCount -= 1
            else:
                # If there are more notes to play for this synth, then play them
                if ( not lastNotePlaying0 ):
                    #print ("0:  ", songList[songChoice][0][noteCount0][0])   # DEBUG
                    # Transform the strings from the current record in the song list into note0, oct0, vol0, dur0
                    xformNoteData(0)
                    #print ("                                       note0: ", note0, "  ", end="")   # DEBUG
                    synth0TickCount = dur0
                    # if the note is a Rest, then we stop playing the previous note and deal with duration, 
                    # otherwise we send octave and note to the synth
                    if ( note0 != 'R'):
                        setVolume(0, vol0)         # set volume for this note on this synth
                        sendNote(0, note0, oct0)   # send note to this synth
                    else:
                        stopNote(0)                # this is a Rest, so stop note on this synth
                    # increment to the next note for this synth
                    noteCount0 += 1
                    # If the next note is '0', then we are playing the last note of the song for this synth
                    if ( songList[songChoice][0][noteCount0][0] == '0' ):
                        lastNotePlaying0 = True
                        #print ("                                       synth0 last note")   # DEBUG
                    # If we're playing the last note of the song for this synth and TickCount has reached 0,
                    # then we just finished playing the last note for this synth.
                elif ( synth0TickCount == 0 ):
                        endOfSongSynth0 = True
                        #fadeSynth(0)              # fade out synth0 (Thick)
                        stopNote(0)                # stop note on synth 0 (Thick)
                        #print ("                                       END OF SYNTH0")   # DEBUG
                # DEBUG
                #else:
                    #print ("")

        # synth 1 (Hocus):
        # If synth 1 is still active for this song then play notes from the song on this synth.
        if ( not endOfSongSynth1 ):
            # If synth1TickCount is 0, then it is time to send the next note to the Hocus synth on ttyUSB1,
            # otherwise, simply decriment synth1TickCount so that the note keeps playing.
            if ( synth1TickCount != 0 ):
                synth1TickCount -= 1
            else:
                # If there are more notes to play for this synth, then play them     
                if ( not lastNotePlaying1 ):
                    #print ("1:  ", songList[songChoice][1][noteCount1][0])   # DEBUG
                    # Transform the strings from the current record in the song list into note1, oct1, vol1, dur1
                    xformNoteData(1)
                    #print ("                                       note1: ", note1, "  ", end="")   # DEBUG
                    synth1TickCount = dur1
                    # if the note is a Rest, then we stop playing the previous note and deal with duration, 
                    # otherwise we send octave and note to the synth
                    if ( note1 != 'R'):
                        setVolume(1, vol1)         # set volume for this note on the synth
                        sendNote(1, note1, oct1)   # send note to the synth
                    else:
                        stopNote(1)                # this is a Rest, so stop note on the synth
                    # increment to the next note for this synth
                    noteCount1 += 1
                    # If the next note is '0', then we are playing the last note of the song for this synth
                    if ( songList[songChoice][1][noteCount1][0] == '0' ):
                        lastNotePlaying1 = True
                        #print ("                                       synth1 last note")   # DEBUG
                    # If we're playing the last note of the song for this synth and TickCount has reached 0,
                    # then we just finished playing the last note for this synth.
                elif ( synth1TickCount == 0 ):
                        endOfSongSynth1 = True
                        #fadeSynth(1)              # fade out synth1 (Hocus)
                        stopNote(1)                # stop note on this synth
                        #print ("                                       END OF SYNTH1")   # DEBUG
                # DEBUG
                #else:
                    #print ("")

        # synth 2 (Dronetic):
        # If synth 2 is still active for this song then play notes from the song on this synth.
        if ( not endOfSongSynth2 ):
            # If synth2TickCount is 0, then it is time to send the next note to the Dronetic synth on ttyUSB2,
            # otherwise, simply decriment synth2TickCount so that the note keeps playing.
            if ( synth2TickCount != 0 ):
                synth2TickCount -= 1
            else:
                # If there are more notes to play for this synth, then play them     
                if ( not lastNotePlaying2 ):
                    #print ("2:  ", songList[songChoice][2][noteCount2][0])   # DEBUG
                    # Transform the strings from the current record in the song list into note2, oct2, vol2, dur2
                    xformNoteData(2)
                    #print ("                                       note2: ", note2, "  ")   # DEBUG
                    synth2TickCount = dur2
                    # if the note is a Rest, then we stop playing the previous note and deal with duration, 
                    # otherwise we send octave and note to the synth
                    if ( note2 != 'R'):
                        setVolume(2, vol2)         # set volume for this note on the synth
                        sendNote(2, note2, oct2)   # send note to the synth
                    else:
                        stopNote(2)                # this is a Rest, so stop note on the synth
                        setVolume(2, "0")          # set volume for this note to 0
                    # increment to the next note for this synth
                    noteCount2 += 1
                    # If the next note is '0', then we are playing the last note of the song for this synth
                    if ( songList[songChoice][2][noteCount2][0] == '0' ):
                        lastNotePlaying2 = True
                        #print ("                                       synth2 last note")   # DEBUG
                    # If we're playing the last note of the song for this synth and TickCount has reached 0,
                    # then we just finished playing the last note for this synth.
                elif ( synth2TickCount == 0 ):
                        endOfSongSynth2 = True
                        fadeSynth(2)               # fade out the drone playing on synth2 (Dronetic)
                        stopNote(2)                # stop note on this synth
                        #print ("                                       END OF SYNTH2")   # DEBUG
                # DEBUG
                #else:
                    #print ("")   # DEBUG

        # synth 3 (eSpeak):
        # If synth3TickCount is 0, then it is time to send the next lyric word to "sing" to eSpeak 
        # (though, the next word may be a Rest),
        # otherwise, simply decriment synth3TickCount 
        # (which is only used in the case where the previous lyric word was a Rest).
        if ( synth3TickCount != 0 ):
            synth3TickCount -= 1
        else:
            if ( not endOfSongSynth3 ):
                #print ("3:  ", songList[songChoice][3][noteCount3][0])   # DEBUG
                # print lyric word to screen
                if ( songList[songChoice][3][noteCount3][0] != 'R'):
                    print ("   ", songList[songChoice][3][noteCount3][0])
                # Transform the strings from the current record in the song list into note3, dur3
                # For this "synth" (eSpeak), note3 will either be a lyric word or 'R' (Rest).
                # dur3 is only relevant if note3 is 'R'.
                xformNoteData(3)
                #print ("                                       note3: ", note3, "  ")   # DEBUG
                synth3TickCount = dur3
                # if note3 is a Rest, then we we just pass here (and wait for the next tick), 
                # otherwise we send the lyric word in note3 to eSpeak
                if ( note3 != 'R' ):
                    # Call eSpeak TTS engine to "sing" the lyric word in note3
                    call (['espeak '+note3+' 2>/dev/null'], shell=True)
                    #print ("send to eSpeak: ", note3)   # DEBUG
                    # since the call to eSpeak is blocking, and takes about 1 second to return,
                    # set the other three synth's TickCounts to 0, so that the notes currently playing on them
                    # play a bit less too long
                    synth0TickCount = 0
                    synth1TickCount = 0
                    synth2TickCount = 0
                    pass
                else:
                    pass                                       # nothing to do for a Rest for eSpeak except wait till the next tick
                # increment to the next note for this synth
                noteCount3 += 1
                # If the next note is '0', then we just sent the last lyric word of this song to eSpeak.
                if ( songList[songChoice][3][noteCount3][0] == '0' ):
                    endOfSongSynth3 = True
                    #print ("                                       end of synth3")   # DEBUG
            # DEBUG
            #else:
                #print ("")

        count += 1   # DEBUG
        #print ("End of ISR")



#--------------------------------------------------
#--------------------------------------------------
# 
# A song is a list with the following structure:
#     song[synthNum][noteNum][noteData]
#
#          synthNum is:  0  --  ArduTouch synth connected to ttyUSB0 (Thick)
#                        1  --  ArduTouch synth connected to ttyUSB1 (Hocus)
#                        2  --  ArduTouch synth connected to ttyUSB2 (Dronetic)
#                        3  --  eSpeak Text To Speech engine (to "sing" lyrics along to the music)
#
#          noteNum is:   0 through last note's number  --  one entry per note (or rest) to play in the song
#
#          noteData is:  0  --  note:      'C' 'C#' 'D' 'D#' 'E' 'F' 'F#' 'G' 'G#' 'A' 'A#' 'B'    'R' (Rest)
#                        1  --  octave:    '0' '1' '2' '3' '4' '5' '6' '7'
#                        2  --  volume:    '0' through '255'
#                        3  --  duration:  'w' (whole)  'h' (half)  'q' (quarter)  'e' (eighth)  's' (sixteenth)
#
#     NOTE:  When the note in noteData is a Rest ('R') there is no relevant octave or volume information.
#     NOTE:  When the synth is eSpeak (synthNum is 3) the noteData is the lyric word or 'R' (Rest).
#            If the note in noteData is a word then there is no relevant octave or volume or duration.
#
#     NOTE:  A lyric word entry for eSpeak (synth 3) can be more than one word.
#            To have a multi-word entry, put a '_' (unserscore) character between words.
#            For example:  'in_the'
#
#     The last entry in every song for each synth is:  ['0','0','0','0']
#
# Here is an example:
#   This simple song has 4 notes, each a quarter note, each played at full volume:
#      synth 0 (Thick)    will play:    C4, E4, G4, C4                 (all on octave 3) 
#      synth 1 (Hocus)    will play:    G4, R (quarter note), D5, G4   (all on octave 3, except the D is on octave 4, and the 2nd note is a Rest)
#      synth 2 (Dronetic) will play:    D5, F#5, A5, D5                (all on octave 4)
#      eSpeak             will "sing":  'strangers', Rest a half note, 'in', 'the', 'night'
#
#   song = [
#       [  ['C','3','255','q'], ['E','3','255','q'], ['G','3','255','q'], ['C','3','255','q'], ['0','0','0','0']  ], 
#       [  ['G','3','255','q'], ['R','.','.','q'], ['D','4','255','q'], ['G','3','255','q'], ['0','0','0','0']  ], 
#       [  ['D','4','255','q'], ['F#','4','255','q'], ['A','4','255','q'], ['D','4','255','q'], ['0','0','0','0']  ] 
#       [  ['strangers','.','.','.'], ['R','.','.','h'], ['in','.','.','.'], ['the','.','.','.'], ['night','.','.','.'], ['0','0','0','0']  ]
#   ]
#
#
#--------------------------------------------------
#--------------------------------------------------


MyWay = [
    [  ['C','2','255','w'], ['R','.','.','w'], ['G','2','255','h'], ['E','2','255','h'], ['D#','2','255','q'],
       ['D#','2','255','w'], ['D#','2','255','w'], 
       ['D#','2','200','w'], ['D#','2','200','w'], 
       ['D#','2','170','w'], ['D#','2','170','w'], 
       ['D#','2','130','w'], ['D#','2','130','w'], 
       ['D#','2','100','w'], ['D#','2','100','w'], 
       ['D#','2','100','w'], ['D#','2','100','w'], 
       ['D#','2','100','w'], ['D#','2','100','w'], 
       ['D#','2','100','w'], ['D#','2','100','w'], 
       ['D#','2','100','w'], ['D#','2','100','w'], 
       ['D#','2','100','w'], ['D#','2','100','w'], 
       ['D#','2','130','w'], ['D#','2','130','w'], 
       ['D#','2','170','w'], ['D#','2','170','w'], 
       ['D#','2','200','w'], ['D#','2','200','w'], 
       ['D#','2','255','w'], ['D#','2','255','w'], 
       ['D#','2','255','w'], ['D#','2','255','w'], 
       ['D#','2','255','w'], ['D#','2','255','w'], 
       ['0','0','0','0']  ],

    [  ['G','2','255','w'], ['A','2','255','h'], ['B','2','255','h'], ['B','1','255','h'], ['E','2','255','q'],
       ['E','2','200','w'], ['E','2','200','w'], 
       ['E','2','170','w'], ['E','2','170','w'], 
       ['E','2','130','w'], ['E','2','130','w'], 
       ['E','2','100','w'], ['E','2','100','w'], 
       ['E','2','100','w'], ['E','2','100','w'], 
       ['E','2','100','w'], ['E','2','100','w'], 
       ['E','2','100','w'], ['E','2','255','w'], 
       ['E','2','100','w'], ['E','2','100','w'], 
       ['E','2','100','w'], ['E','2','100','w'], 
       ['E','2','100','w'], ['E','2','255','w'], 
       ['E','2','130','w'], ['E','2','130','w'], 
       ['E','2','170','w'], ['E','2','170','w'], 
       ['E','2','200','w'], ['E','2','200','w'], 
       ['E','2','255','w'], ['E','2','255','w'], 
       ['E','2','255','w'], ['E','2','255','w'], 
       ['E','2','255','w'], ['E','2','255','w'], 
       ['0','0','0','0']  ],

    [  ['D','2','150','w'], ['E','2','150','h'], ['R','.','.','h'], ['G','2','150','w'],
       ['G','2','130','w'], ['G','2','130','w'], 
       ['G','2','100','w'], ['G','2','100','w'], 
       ['G','2','100','w'], ['G','2','100','w'], 
       ['G','2','100','w'], ['G','2','100','w'], 
       ['G','2','100','w'], ['G','2','100','w'], 
       ['G','2','100','w'], ['G','2','100','w'], 
       ['G','2','100','w'], ['G','2','100','w'], 
       ['G','2','100','w'], ['G','2','100','w'], 
       ['G','2','100','w'], ['G','2','100','w'], 
       ['G','2','100','w'], ['G','2','100','w'], 
       ['G','2','130','w'], ['G','2','130','w'], 
       ['G','2','150','w'], ['G','2','150','w'], 
       ['G','2','150','w'], ['G','2','150','w'], 
       ['G','2','150','w'], ['G','2','150','w'], 
       ['G','2','150','w'], ['G','2','150','w'], 
       ['G','2','150','w'], ['G','2','150','w'], 
       ['0','0','0','0']  ],

    [  ['I','.','.','.'], ['did','.','.','h'], ['it','.','.','.'], ['my','.','.','.'], ['way','.','.','.'], 
       ['R','.','.','w'], ['R','.','.','w'],
       ['R','.','.','w'], ['R','.','.','w'],

       ['I','.','.','.'], ['always','.','.','h'], ['did','.','.','.'], ['what','.','.','.'], ['I','.','.','.'], ['wanted','.','.','.'], 
       ['R','.','.','w'], ['but','.','.','.'], ['R','.','.','e'], ['then','.','.','h'], ['I','.','.','.'], ['got','.','.','.'], ['cancelled','.','.','.'],
       ['R','.','.','e'], ['on','.','.','.'], ['R','.','.','e'], ['social','.','.','h'], ['media','.','.','.'], 

       ['R','.','.','w'], ['R','.','.','w'],
       ['R','.','.','w'], ['R','.','.','w'],
       ['I','.','.','.'], ['did','.','.','h'], ['it','.','.','.'], ['my','.','.','.'], ['way','.','.','.'], 
       ['0','0','0','0']  ]
]


MoonRiver = [
    [  ['E','3','255','w'], ['R','.','.','w'], ['B','3','255','h'], ['G#','3','255','h'], ['G','3','255','w'], 
       ['G','3','200','w'], ['G','3','200','w'],
       ['G','3','170','w'], ['G','3','170','w'],
       ['G','3','130','w'], ['G','3','130','w'],
       ['G','3','100','w'], ['G','3','100','w'],
       ['G','3','100','w'], ['G','3','100','w'],
       ['G','3','100','w'], ['G','3','100','w'],
       ['G','3','100','w'], ['G','3','100','w'],
       ['G','3','100','w'], ['G','3','100','w'],
       ['G','3','100','w'], ['G','3','100','w'],
       ['G','3','100','w'], ['G','3','100','w'],
       ['G','3','100','w'], ['G','3','100','w'],
       ['G','3','100','w'], ['G','3','100','w'],
       ['G','3','100','w'], ['G','3','100','w'],
       ['G','3','100','w'], ['G','3','100','w'],
       ['G','3','130','w'], ['G','3','130','w'],
       ['G','3','170','w'], ['G','3','170','w'],
       ['G','3','200','w'], ['G','3','200','w'],
       ['G','3','255','w'], ['G','3','255','w'],
       ['0','0','0','0']  ],

    [  ['B','3','255','w'], ['C#','4','255','h'], ['D#','4','255','h'], ['D#','3','255','h'], ['G#','3','255','w'], 
       ['G#','3','200','w'], ['G#','3','200','w'],
       ['G#','3','170','w'], ['G#','3','170','w'],
       ['G#','3','130','w'], ['G#','3','130','w'],
       ['G#','3','100','w'], ['G#','3','100','w'],
       ['G#','3','100','w'], ['G#','3','100','w'],
       ['G#','3','100','w'], ['G#','3','100','w'],
       ['G#','3','100','w'], ['G#','3','100','w'],
       ['G#','3','100','w'], ['G#','3','100','w'],
       ['G#','3','100','w'], ['G#','3','100','w'],
       ['G#','3','100','w'], ['G#','3','100','w'],
       ['G#','3','100','w'], ['G#','3','100','w'],
       ['G#','3','100','w'], ['G#','3','100','w'],
       ['G#','3','100','w'], ['G#','3','100','w'],
       ['G#','3','130','w'], ['G#','3','130','w'],
       ['G#','3','170','w'], ['G#','3','170','w'],
       ['G#','3','200','w'], ['G#','3','200','w'],
       ['G#','3','255','w'], ['G#','3','255','w'],
       ['G#','3','255','w'], ['G#','3','255','w'],
       ['0','0','0','0']  ],

    [  ['F#','3','150','w'], ['G#','3','150','h'], ['R','.','.','h'], ['B','3','150','W'], 
       ['B','3','150','W'],  ['B','3','150','W'],
       ['B','3','130','W'],  ['B','3','130','W'],
       ['B','3','100','W'],  ['B','3','100','W'],
       ['B','3','80','W'],  ['B','3','80','W'],
       ['B','3','50','W'],  ['B','3','50','W'],
       ['B','3','50','W'],  ['B','3','50','W'],
       ['B','3','50','W'],  ['B','3','50','W'],
       ['B','3','50','W'],  ['B','3','50','W'],
       ['B','3','50','W'],  ['B','3','50','W'],
       ['B','3','50','W'],  ['B','3','50','W'],
       ['B','3','50','W'],  ['B','3','50','W'],
       ['B','3','50','W'],  ['B','3','50','W'],
       ['B','3','50','W'],  ['B','3','50','W'],
       ['B','3','50','W'],  ['B','3','50','W'],
       ['B','3','50','W'],  ['B','3','50','W'],
       ['B','3','50','W'],  ['B','3','50','W'],
       ['B','3','50','W'],  ['B','3','50','W'],
       ['B','3','80','W'],  ['B','3','80','W'],
       ['B','3','100','W'],  ['B','3','100','W'],
       ['B','3','130','W'],  ['B','3','130','W'],
       ['B','3','150','W'],  ['B','3','150','W'],
       ['B','3','150','W'],  ['B','3','150','W'],
       ['B','3','150','W'],  ['B','3','150','W'],
       ['0','0','0','0']  ],

    [  ['Moon','.','.','.'], ['R','.','.','h'], ['River','.','.','.'], 
       ['R','.','.','w'], ['R','.','.','w'],
       ['R','.','.','w'], ['R','.','.','w'],

       ['R','.','.','w'], ['have','.','.','.'], ['R','.','.','s'], ['you','.','.','.'], ['R','.','.','s'],
       ['thought','.','.','.'], ['R','.','.','s'], ['about','.','.','.'], ['R','.','.','s'],
       ['the','.','.','.'], ['R','.','.','s'], ['camera','.','.','.'], ['R','.','.','s'],
       ['R','.','.','w'], ['it','.','.','.'], ['R','.','.','s'], ['seems','.','.','.'], ['R','.','.','s'],
       ['like','.','.','.'], ['R','.','.','s'],
       ['something','.','.','.'], ['R','.','.','s'], ['for','.','.','.'], ['R','.','.','s'], ['surveillance','.','.','.'], ['R','.','.','s'],
       ['R','.','.','w'], ['doesnt','.','.','.'], ['R','.','.','s'], ['it','.','.','.'], ['R','.','.','s'],
       ['R','.','.','w'], ['are','.','.','.'], ['R','.','.','s'], ['your','.','.','.'], ['R','.','.','s'],
       ['face','.','.','.'], ['R','.','.','s'], ['and','.','.','.'], ['R','.','.','s'], ['your','.','.','.'], ['R','.','.','s'],
       ['desires','.','.','.'], ['R','.','.','e'], ['now','.','.','.'], ['R','.','.','s'],
       ['stored_on','.','.','.'], ['R','.','.','e'], ['the_internet','.','.','.'], ['R','.','.','s'],

       ['R','.','.','w'], ['R','.','.','w'],
       ['R','.','.','w'], ['R','.','.','w'],
       ['wider','.','.','.'], ['R','.','.','q'], ['than','.','.','.'], ['R','.','.','q'], ['a_mile','.','.','.'], 
       ['0','0','0','0']  ]
]


StrangersInTheNight = [
       # Thick (bass)
    [  ['F','2','150','h'], ['F','2','150','q'], ['C','3','150','q'], ['R','.','.','s'], ['C','3','150','h'], ['C','2','150','h'], 
       ['F','2','150','h'], ['F','2','150','q'], ['C','3','150','q'], ['R','.','.','s'], ['C','3','150','h'], ['C','2','150','h'], 
       ['F','2','150','h'], ['F','2','150','q'], ['C','3','150','q'], ['R','.','.','s'], ['C','3','150','h'], ['C','2','150','h'], 
       ['G','2','150','h'], ['G','2','150','q'], ['C','3','150','q'], ['R','.','.','s'], ['C','3','150','h'], ['C','2','150','h'], 
       ['F','2','150','h'], ['F','2','150','q'], ['C','3','150','q'], ['R','.','.','s'], ['C','3','150','h'], ['C','2','150','h'], 
       ['F','2','150','h'], ['F','2','150','q'], ['C','3','150','q'], ['R','.','.','s'], ['C','3','150','h'], ['C','2','150','h'], 
       ['F','2','150','h'], ['F','2','150','q'], ['C','3','150','q'], ['R','.','.','s'], ['C','3','150','h'], ['C','2','150','h'], 
       ['F','2','150','h'], ['F','2','150','q'], ['C','3','150','q'], ['R','.','.','s'], ['C','3','150','h'], ['C','2','150','h'], 
       ['F','2','150','h'], ['F','2','150','q'], ['C','3','150','q'], ['R','.','.','s'], ['C','3','150','h'], ['C','2','150','h'], 
       ['A','2','150','w'], ['G#','2','150','w'], 
       ['G','2','150','h'], ['G','2','150','q'],  ['D','2','150','q'],  ['A','3','150','h'], ['A','3','150','q'], ['D','2','150','q'],
       ['G','3','150','h'], ['G','3','150','q'],  ['D','2','150','q'],  ['F#','3','150','h'], ['F','3','150','h'],

       ['G','2','150','h'], ['G','2','150','q'], ['D','3','150','q'], ['R','.','.','s'], ['D','3','150','h'], ['D','2','150','h'], 
       ['G','2','150','h'], ['G','2','150','q'], ['D','3','150','q'], ['R','.','.','s'], ['D','3','150','h'], ['D','2','150','h'], 
       ['G','2','150','h'], ['G','2','150','q'], ['D','3','150','q'], ['R','.','.','s'], ['D','3','150','h'], ['D','2','150','h'], 
       ['G','2','150','h'], ['G','2','150','q'], ['D','3','150','q'], ['R','.','.','s'], ['D','3','150','h'], ['G','2','150','h'], 
       ['C','2','150','h'], ['C','2','150','q'], ['G','2','150','q'], ['C','3','150','h'], ['C','2','150','h'], 
       ['G','2','150','h'], ['G','2','150','q'], ['C','3','150','q'], ['R','.','.','s'], ['C','3','150','h'], ['C','2','150','h'], 
       ['F','2','150','h'], ['F','2','150','q'],  ['E','2','150','q'],  ['G','3','150','h'], ['G','3','150','q'], ['F','2','150','q'],
       ['E','3','150','h'], ['E','3','150','q'],  ['C','2','150','q'],  ['D','3','150','h'], ['C','3','150','h'],

       ['G','2','150','h'], ['G','2','150','q'], ['D','3','150','q'], ['R','.','.','s'], ['D','3','150','h'], ['D','2','150','h'], 
       ['G','2','150','h'], ['G','2','150','q'], ['D','3','150','q'], ['R','.','.','s'], ['D','3','150','h'], ['D','2','150','h'], 
       ['G','2','150','h'], ['G','2','150','q'], ['D','3','150','q'], ['R','.','.','s'], ['D','3','150','h'], ['D','2','150','h'], 
       ['G','2','150','h'], ['G','2','150','q'], ['D','3','150','q'], ['R','.','.','s'], ['D','3','150','h'], ['G','2','150','h'], 
       ['C','2','150','h'], ['C','2','150','q'], ['G','2','150','q'], ['C','3','150','h'], ['C','2','150','h'], 
       ['G','2','150','h'], ['G','2','150','q'], ['C','3','150','q'], ['R','.','.','s'], ['C','3','150','h'], ['C','2','150','h'], 
       ['F','2','150','h'], ['F','2','150','q'],  ['E','2','150','q'],  ['G','3','150','h'], ['G','3','150','q'], ['F','2','150','q'],
       ['E','3','150','h'], ['E','3','150','q'],  ['C','2','150','q'],  ['D','3','150','h'], ['C','3','150','h'],

       ['A','2','150','w'], ['A','3','150','h'], ['G','3','150','h'], 
       ['G','3','150','w'], ['A','3','150','h'], ['G','3','150','h'], 
       ['D','3','150','w'], ['R','.','.','s'], ['D','3','150','h'], ['D','2','150','h'], 
       ['D','3','150','w'], ['D','2','150','h'], ['D','3','150','h'], 
       ['G','3','150','w'], ['D','3','150','h'], ['D','2','150','h'], 
       ['A#','2','150','w'], ['A#','2','150','h'], ['C#','3','150','h'], 
       ['C','2','150','w'], ['D','2','150','w'], 
       ['F','3','150','w'], ['C','3','150','w'], 
       ['F','2','150','h'], ['F','2','150','q'], ['C','3','150','q'], ['R','.','.','s'], ['C','3','150','h'], ['C','2','150','h'], 
       ['F','2','150','h'], ['F','2','150','q'], ['C','3','150','q'], ['R','.','.','s'], ['C','3','150','h'], ['C','2','150','h'], 
       ['F','2','150','h'], ['F','2','150','q'], ['C','3','150','q'], ['R','.','.','s'], ['C','3','150','h'], ['C','2','150','h'], 
       ['F','2','150','h'], ['F','2','150','q'], ['C','3','150','q'], ['R','.','.','s'], ['C','3','150','h'], ['C','2','150','h'], 
       ['F','2','150','h'], ['F','2','150','q'], ['C','3','150','q'], ['R','.','.','s'], ['C','3','150','h'], ['C','2','150','h'], 
       ['C','3','150','w'], ['R','.','.','s'], ['C','3','150','h'], ['C','2','150','h'], 
       ['F','2','150','h'], ['F','2','150','q'], ['C','3','150','q'], ['D#','2','150','h'], ['C#','2','150','h'], 
       ['F','2','150','h'], ['C','2','150','h'], ['F','2','150','w'],    ['F','2','255','w'], ['F','2','255','w'], ['F','2','255','w'], ['F','2','255','w'], ['F','2','255','w'], ['F','2','255','w'], ['F','2','255','w'], ['F','2','255','w'], ['F','2','255','w'], ['F','2','255','w'], 

       ['0','0','0','0']  ],


       # Hocus (melody)
    [  ['F','4','255','q'], ['G','4','255','q'], ['R','.','.','s'], ['G','4','255','q'], ['F','4','255','q'], ['G','4','255','w'], 
       ['G','4','255','q'], ['F','4','255','q'], ['G','4','255','q'], ['A','4','255','q'], ['G','4','255','h'], ['F','4','255','h'],
       ['E','4','255','q'], ['F','4','255','q'], ['R','.','.','s'], ['F','4','255','q'], ['E','4','255','q'], ['F','4','255','w'],
       ['F','4','255','q'], ['E','4','255','q'], ['F','4','255','q'], ['G','4','255','q'], ['F','4','255','h'], ['E','4','255','h'],
       ['F','4','255','q'], ['G','4','255','q'], ['R','.','.','s'], ['G','4','255','q'], ['F','4','255','q'], ['G','4','255','w'], 
       ['G','4','255','q'], ['F','4','255','q'], ['G','4','255','q'], ['A','4','255','q'], ['G','4','255','h'], ['F','4','255','h'],
       ['E','4','255','q'], ['F','4','255','q'], ['R','.','.','s'], ['F','4','255','q'], ['E','4','255','q'], ['F','4','255','w'],
       ['F','4','255','q'], ['E','4','255','q'], ['F','4','255','q'], ['G','4','255','q'], ['F','4','255','h'], ['E','4','255','h'],
       ['D','4','255','q'], ['E','4','255','q'], ['R','.','.','s'], ['E','4','255','q'], ['D','4','255','q'], ['E','4','255','w'],
       ['E','4','255','q'], ['D','4','255','q'], ['E','4','255','q'], ['F','4','255','q'], ['E','4','255','h'], ['D','4','255','h'],
       ['A#','4','255','w'], ['A#','4','255','w'],
       ['A#','4','255','w'], ['A#','4','255','h'], ['R','.','.','h'],

       ['G','4','255','q'], ['A','4','255','q'], ['R','.','.','s'], ['A','4','255','q'], ['G','4','255','q'], ['A','4','255','w'], 
       ['A','4','255','q'], ['G','4','255','q'], ['A','4','255','q'], ['A#','4','255','q'], ['A','4','255','h'], ['G','4','255','h'],
       ['F','4','255','q'], ['G','4','255','q'], ['R','.','.','s'], ['G','4','255','q'], ['F','4','255','q'], ['G','4','255','w'],
       ['G','4','255','q'], ['F','4','255','q'], ['G','4','255','q'], ['A','4','255','q'], ['G','4','255','h'], ['F','4','255','h'],
       ['E','4','255','q'], ['F','4','255','q'], ['R','.','.','s'], ['F','4','255','q'], ['E','4','255','q'], ['F','4','255','w'],
       ['F','4','255','q'], ['E','4','255','q'], ['F','4','255','q'], ['G','4','255','q'], ['F','4','255','h'], ['E','4','255','h'],
       ['C','5','255','w'], ['C','5','255','w'],
       ['C','5','255','w'], ['C','5','255','w'],           ['R','.','.','w'], 

       ['G','4','255','q'], ['A','4','255','q'], ['R','.','.','s'], ['A','4','255','q'], ['G','4','255','q'], ['A','4','255','w'], 
       ['A','4','255','q'], ['G','4','255','q'], ['A','4','255','q'], ['A#','4','255','q'], ['A','4','255','h'], ['G','4','255','h'],
       ['F','4','255','q'], ['G','4','255','q'], ['R','.','.','s'], ['G','4','255','q'], ['F','4','255','q'], ['G','4','255','w'],
       ['G','4','255','q'], ['F','4','255','q'], ['G','4','255','q'], ['A','4','255','q'], ['G','4','255','h'], ['F','4','255','h'],
       ['E','4','255','q'], ['F','4','255','q'], ['R','.','.','s'], ['F','4','255','q'], ['E','4','255','q'], ['F','4','255','w'],
       ['F','4','255','q'], ['E','4','255','q'], ['F','4','255','q'], ['G','4','255','q'], ['F','4','255','h'], ['E','4','255','h'],
       ['C','5','255','w'], ['C','5','255','w'],
       ['C','5','255','w'], ['C','5','255','w'],           ['R','.','.','w'], 

       ['C','5','255','q'], ['A#','4','255','q'], ['R','.','.','s'], ['A#','4','255','q'], ['A','4','255','q'], ['R','.','.','s'], ['A','4','255','w'], 
       ['A','4','255','q'], ['A#','4','255','q'], ['R','.','.','s'], ['A#','4','255','q'], ['C','5','255','q'], ['R','.','.','s'], ['C','5','255','q'], ['A#','4','255','q'], ['R','.','.','s'], ['A#','4','255','q'], ['A','4','255','q'],
       ['C','5','255','q'], ['A#','4','255','q'], ['R','.','.','s'], ['A#','4','255','q'], ['A','4','255','q'], ['R','.','.','s'], ['A','4','255','w'],
       ['A','4','255','q'], ['A#','4','255','q'], ['R','.','.','s'], ['A#','4','255','q'], ['C','5','255','q'], ['R','.','.','s'], ['C','5','255','h'], ['A#','4','255','h'], ['R','.','.','s'], ['A#','4','255','q'], ['A','4','255','q'],
       ['A#','4','255','q'], ['A','4','255','q'], ['R','.','.','s'], ['A','4','255','q'], ['G','4','255','q'], ['R','.','.','s'], ['G','4','255','w'],
       ['A#','4','255','q'], ['A','4','255','q'], ['R','.','.','s'], ['A','4','255','q'], ['G','4','255','q'], ['R','.','.','s'], ['G','4','255','w'],
       ['A#','4','255','q'], ['A','4','255','q'], ['R','.','.','s'], ['A','4','255','q'], ['G','4','255','q'], ['R','.','.','s'], ['G','4','255','q'], ['F','4','255','q'], ['E','4','255','q'], ['F','4','255','q'],
       ['A','4','255','q'], ['G','4','255','q'], ['R','.','.','s'], ['G','4','255','q'], ['F','4','255','q'], ['R','.','.','s'], ['F','4','255','q'], ['E','4','255','q'], ['D','4','255','q'], ['E','4','255','q'],
       ['F','4','255','q'], ['G','4','255','q'], ['R','.','.','s'], ['G','4','255','q'], ['F','4','255','q'], ['R','.','.','s'], ['G','4','255','w'],
       ['G','4','255','q'], ['F','4','255','q'], ['G','4','255','q'], ['A','4','255','q'], ['G','4','255','h'], ['F','4','255','h'], 
       ['E','4','255','q'], ['F','4','255','q'], ['R','.','.','s'], ['F','4','255','q'], ['E','4','255','q'], ['F','4','255','h'], 
       ['F','4','255','q'], ['E','4','255','q'], ['F','4','255','q'], ['G','4','255','q'], ['F','4','255','h'], ['E','4','255','h'], 
       ['D','4','255','q'], ['E','4','255','q'], ['R','.','.','s'], ['E','4','255','q'], ['D','4','255','q'], ['E','4','255','w'], 
       ['E','4','255','q'], ['R','.','.','s'], ['E','4','255','q'], ['F','4','255','q'], ['G','4','255','q'], ['F','4','255','h'], ['E','4','255','h'], 
       ['F','4','255','w'], ['F','4','255','w'], 
       ['F','4','255','w'], ['F','4','255','w'], 

       ['0','0','0','0']  ],


       # Dronetic ("strings")
    [  ['A','2','255','w'], ['A','2','255','w'], 
       ['A','2','255','w'], ['A','2','255','w'], 
       ['A','2','255','w'], ['A','2','255','w'], 
       ['A#','2','255','w'], ['G','2','255','w'], 
       ['A','2','255','w'], ['A','2','255','w'],
       ['A','2','255','w'], ['A','2','255','w'],
       ['A','2','255','w'], ['A','2','255','w'],    # The notes here are to compensate for the lost time for when note durations are truncated in an attempt to lose less time when eSpeak blocks the timing while speaking
       ['A','2','255','w'], ['A','2','255','w'],    ['A','2','255','w'], ['A','2','255','w'], ['A','2','255','w'], ['A','2','255','w'], ['A','2','255','w'], ['A','2','255','w'], ['A','2','255','w'], ['A','2','255','w'], ['A','2','255','w'],
       ['F','2','255','w'], ['A','2','255','w'],
       ['A','2','255','w'], ['F','2','255','w'],    ['F','2','255','w'], ['F','2','255','w'], ['F','2','255','w'], ['F','2','255','w'],
       ['R','.','.','h'], ['A#','2','255','w'], ['A#','2','255','h'], 
       ['A#','2','255','w'], ['A#','2','255','w'], 

       ['A#','2','255','w'], ['A#','2','255','w'], 
       ['A#','2','255','w'], ['A#','2','255','w'], 
       ['A#','2','255','w'], ['A#','2','255','w'], 
       ['A#','2','255','w'], ['A#','2','255','w'], 
       ['A#','2','255','w'], ['A#','2','255','w'], 
       ['A#','2','255','w'], ['A#','2','255','w'],    ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'],
       ['R','.','.','h'], ['C','2','255','w'], ['C','2','255','h'], 
       ['R','.','.','h'], ['C','2','255','w'], ['C','2','255','h'], 

       ['A#','2','255','w'], ['A#','2','255','w'], 
       ['A#','2','255','w'], ['A#','2','255','w'], 
       ['A#','2','255','w'], ['A#','2','255','w'], 
       ['A#','2','255','w'], ['A#','2','255','w'], 
       ['A#','2','255','w'], ['A#','2','255','w'], 
       ['A#','2','255','w'], ['A#','2','255','w'],    ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'],
       ['R','.','.','h'], ['C','2','255','w'], ['C','2','255','h'], 
       ['R','.','.','h'], ['C','2','255','w'], ['C','2','255','h'],    ['C','2','255','w'], 

       ['D#','2','255','w'], ['C','2','255','w'], 
       ['C','2','255','w'], ['D#','2','255','q'], ['C','2','255','q'], 
       ['D#','2','255','w'], ['C','2','255','w'], 
       ['C','2','255','w'], ['C','2','255','w'], 
       ['A#','2','255','w'], ['A#','2','255','w'], 
       ['C#','2','255','w'], ['A#','2','255','w'],    ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'],
       ['C','2','255','w'], ['A','2','255','w'], 
       ['A#','2','255','w'], ['G','2','255','q'], 
       ['A','2','255','w'], ['A','2','255','w'], 
       ['A','2','255','w'], ['A','2','255','w'], 
       ['A','2','255','w'], ['A','2','255','w'], 
       ['A','2','255','w'], ['A','2','255','w'],    ['A','2','255','w'], ['A','2','255','w'], ['A','2','255','w'], ['A','2','255','w'], ['A','2','255','w'], ['A','2','255','w'], ['A','2','255','w'], ['A','2','255','w'], ['A','2','255','w'], ['A','2','255','w'],
       ['G','2','255','w'], ['G','2','255','w'],
       ['A#','2','255','w'], ['G','2','255','w'],
       ['A','2','255','w'], ['C#','2','255','w'], ['A#','2','255','w'],    ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'], ['A#','2','255','w'],
       ['F','2','255','w'], ['F','2','255','w'],

       ['0','0','0','0']  ],


       # eSpeak (lyrics)
    [  ['R','.','.','w'], ['R','.','.','w'], 
       ['R','.','.','w'], ['R','.','.','w'], 
       ['R','.','.','w'], ['R','.','.','w'], 
       ['R','.','.','w'], ['R','.','.','w'], 
       ['strangers','.','.','.'], ['in_the','.','.','.'], ['night','.','.','.'], ['R','.','.','w'], ['R','.','.','w'], 
       ['exchanging','.','.','.'], ['glances','.','.','.'], ['R','.','.','w'], 
       ['wondering','.','.','.'], ['in_the','.','.','.'], ['night','.','.','.'], ['R','.','.','w'], ['R','.','.','w'], 
       ['what','.','.','.'], ['were_the','.','.','.'], ['chances','.','.','.'], ['R','.','.','w'], 
       ['weed_be','.','.','.'], ['sharing','.','.','.'], ['love','.','.','.'], ['R','.','.','w'], 
       ['before_the','.','.','.'], ['night_was','.','.','.'], ['R','.','.','w'], ['R','.','.','w'], 
       ['through','.','.','.'], ['R','.','.','w'], 

       ['something','.','.','.'], ['in_your','.','.','.'], ['eyes','.','.','.'], ['R','.','.','w'], ['R','.','.','w'], 
       ['was_so','.','.','.'], ['inviting','.','.','.'], ['R','.','.','w'], 
       ['something','.','.','.'], ['in_your','.','.','.'], ['smile','.','.','.'], ['R','.','.','w'], ['R','.','.','w'], 
       ['was_so','.','.','.'], ['excite','.','.','.'], ['ing','.','.','.'], ['R','.','.','w'], 
       ['something','.','.','.'], ['in_my','.','.','.'], ['heart','.','.','.'], ['R','.','.','w'], 
       ['told_me','.','.','.'], ['I_must_have','.','.','.'], ['R','.','.','w'], ['R','.','.','w'], 
       ['you','.','.','.'], ['R','.','.','w'], ['R','.','.','w'], 

       ['R','.','.','w'], ['i_am','.','.','.'], ['really','.','.','.'], ['R','.','.','w'], 
       ['a_good','.','.','.'], ['musician','.','.','.'], ['R','.','.','w'], 
       ['i_used_to','.','.','.'], ['have','.','.','.'], ['dreams','.','.','.'], ['R','.','.','w'], ['R','.','.','w'], 
       ['aspirations','.','.','.'], ['R','.','.','w'], ['R','.','.','w'], 
       ['but','.','.','.'], ['money','.','.','.'], ['got_tight','.','.','.'], ['R','.','.','w'], 
       ['and_i','.','.','.'], ['got_a','.','.','.'], ['job','.','.','.'], ['R','.','.','w'], ['R','.','.','w'], 
       ['at_the','.','.','.'], ['muzak','.','.','.'], ['corporation','.','.','.'], ['R','.','.','w'], ['R','.','.','w'], 

       ['strangers','.','.','.'], ['in_the','.','.','.'], ['night','.','.','.'], ['R','.','.','w'], ['R','.','.','w'], 
       ['two_lonely','.','.','.'], ['people','.','.','.'], ['we_were','.','.','.'], ['R','.','.','w'], 
       ['strangers','.','.','.'], ['in_the','.','.','.'], ['night','.','.','.'], ['R','.','.','w'],
       ['up_to','.','.','.'], ['the_moment','.','.','.'], ['when_we','.','.','.'], ['R','.','.','w'], ['R','.','.','w'], 
       ['said','.','.','.'], ['our_first','.','.','.'], ['hello','.','.','.'], ['R','.','.','w'], ['R','.','.','w'], 
       ['little','.','.','.'], ['did_we','.','.','.'], ['know','.','.','.'], ['R','.','.','w'], ['R','.','.','w'], 
       ['love_was','.','.','.'], ['just_a','.','.','.'], ['glance_away','.','.','.'], ['a','.','.','.'], ['R','.','.','w'], 
       ['warm','.','.','.'], ['embracing','.','.','.'], ['dance_away','.','.','.'], ['and','.','.','.'], ['R','.','.','w'], ['R','.','.','w'], 
       ['ever','.','.','.'], ['since','.','.','.'], ['that_night','.','.','.'], ['R','.','.','w'], 
       ['weave','.','.','.'], ['been','.','.','.'], ['together','.','.','.'], ['R','.','.','w'], 
       ['lovers','.','.','.'], ['at_first','.','.','.'], ['sight','.','.','.'], ['R','.','.','w'], 
       ['in_love','.','.','.'], ['forever','.','.','.'], ['R','.','.','w'],
       ['it','.','.','.'], ['turned_out','.','.','.'], ['so_right','.','.','.'], ['R','.','.','w'], ['R','.','.','w'], 
       ['for','.','.','.'], ['strangers','.','.','.'], ['in_the','.','.','.'], ['night','.','.','.'], 

       ['0','0','0','0']  ]
]


LoveStory = [

       # Thick (bass)
    [  ['A','2','250','w'], ['A','2','250','w'],
       ['A','2','250','w'], ['A','2','250','w'],
       ['A','2','250','w'], ['A','2','250','w'], ['A','2','250','e'],
       ['A','2','250','w'], ['A','2','250','w'], ['A','2','250','e'],     ['A','2','250','w'], ['A','2','250','w'], ['A','2','250','w'], ['A','2','250','w'],
       ['G#','2','250','w'], ['G#','2','250','w'], ['G#','2','250','e'], ['G#','2','250','s'],
       ['G#','2','250','w'], ['G#','2','250','w'], ['G#','2','250','e'],     ['G#','2','250','w'], ['G#','2','250','w'], ['G#','2','250','h'],
       ['A','2','250','w'], ['A','2','250','h'], ['G','2','250','h'], ['G','2','250','e'], ['G','2','250','s'],     ['G','2','250','w'], ['G','2','250','w'],
       ['F','2','250','w'], ['F','2','250','w'], ['F','2','250','e'],     ['F','2','250','h'],
       ['E','2','250','w'], ['E','2','250','w'],
       ['E','2','250','w'], ['E','2','250','w'], ['E','2','250','e'],     ['E','2','250','w'], ['E','2','250','e'],
       ['A','2','250','w'], ['A','2','250','w'],     ['A','2','250','w'], ['A','2','250','w'],
       ['A','2','250','w'], ['A','2','250','w'],     ['A','2','250','w'], ['A','2','250','w'],

       ['A','2','250','w'], ['A','2','250','w'], ['A','2','250','e'],
       ['A','2','250','w'], ['A','2','250','w'], ['A','2','250','e'],     ['A','2','250','w'], ['A','2','250','w'], ['A','2','250','w'], ['A','2','250','w'],
       ['G#','2','250','w'], ['G#','2','250','w'], ['G#','2','250','e'], ['G#','2','250','s'],
       ['G#','2','250','w'], ['G#','2','250','w'], ['G#','2','250','e'],     ['G#','2','250','w'], ['G#','2','250','w'], ['G#','2','250','h'],
       ['A','2','250','w'], ['A','2','250','h'], ['G','2','250','h'], ['G','2','250','e'], ['G','2','250','s'],     ['G','2','250','w'], ['G','2','250','w'],
       ['F','2','250','w'], ['F','2','250','w'], ['F','2','250','e'],     ['F','2','250','h'],
       ['E','2','250','w'], ['E','2','250','w'],
       ['E','2','250','w'], ['E','2','250','w'], ['E','2','250','e'],     ['E','2','250','w'], ['E','2','250','e'],
       ['A','2','250','w'], ['A','2','250','w'],     ['A','2','250','w'], ['A','2','250','w'],
       ['A','2','250','w'], ['A','2','250','w'],     ['A','2','250','w'], ['A','2','250','w'],

       ['A','2','250','w'], ['A','2','250','w'], ['A','2','250','e'],
       ['A','2','250','w'], ['A','2','250','w'], ['A','2','250','e'],     ['A','2','250','w'], ['A','2','250','w'], ['A','2','250','w'], ['A','2','250','w'],
       ['G#','2','250','w'], ['G#','2','250','w'], ['G#','2','250','e'], ['G#','2','250','s'],
       ['G#','2','250','w'], ['G#','2','250','w'], ['G#','2','250','e'],     ['G#','2','250','w'], ['G#','2','250','w'], ['G#','2','250','h'],
       ['A','2','250','w'], ['A','2','250','h'], ['G','2','250','h'], ['G','2','250','e'], ['G','2','250','s'],     ['G','2','250','w'], ['G','2','250','w'],
       ['F','2','250','w'], ['F','2','250','w'], ['F','2','250','e'],     ['F','2','250','h'],
       ['E','2','250','w'], ['E','2','250','w'],
       ['E','2','250','w'], ['E','2','250','w'], ['E','2','250','e'],     ['E','2','250','w'], ['E','2','250','e'],
       ['A','2','250','w'], ['A','2','250','w'],     ['A','2','250','w'], ['A','2','250','w'],
       ['A','2','250','w'], ['A','2','250','w'],     ['A','2','250','w'], ['A','2','250','w'],

       ['0','0','0','0']  ],


       # Hocus (melody)
    [  ['R','.','.','w'], ['R','.','.','w'],
       ['R','.','.','w'], ['R','.','.','w'],
       ['C','5','255','q'], ['E','4','255','q'], ['R','.','.','s'], ['E','4','255','q'], ['C','5','255','q'], ['R','.','.','s'], ['C','5','255','w'],
       ['C','5','255','q'], ['E','4','255','q'], ['R','.','.','s'], ['E','4','255','q'], ['C','5','255','q'], ['R','.','.','s'], ['C','5','255','q'], ['E','4','255','q'], ['F','4','255','q'], ['E','4','255','q'],
       ['D','4','255','q'], ['R','.','.','s'], ['D','4','255','q'], ['R','.','.','s'], ['D','4','255','q'], ['B','4','255','q'], ['R','.','.','s'], ['B','4','255','w'],
       ['B','4','255','q'], ['D','4','255','q'], ['R','.','.','s'], ['D','4','255','q'], ['B','4','255','q'], ['R','.','.','s'], ['B','4','255','q'], ['D','4','255','q'], ['E','4','255','q'], ['D','4','255','q'],
       ['C','4','255','q'], ['R','.','.','s'], ['C','4','255','q'], ['R','.','.','s'], ['C','4','255','q'], ['A','4','255','q'], ['R','.','.','s'], ['A','4','255','w'],
       ['A','4','255','q'], ['C','4','255','q'], ['R','.','.','s'], ['C','4','255','q'], ['A','4','255','q'], ['R','.','.','s'], ['A','4','255','q'], ['C','4','255','q'], ['D','4','255','q'], ['C','4','255','q'],
       ['B','3','255','q'], ['R','.','.','s'], ['B','3','255','q'], ['R','.','.','s'], ['B','3','255','q'], ['G#','4','255','q'], ['R','.','.','s'], ['G#','4','255','w'],
       ['G#','4','255','h'], ['A','4','255','h'], ['B','4','255','h'], ['F','4','255','h'],
       ['E','4','255','W'], ['E','4','255','W'],
       ['E','4','255','W'], ['E','4','255','W'],

       ['C','5','255','q'], ['E','4','255','q'], ['R','.','.','s'], ['E','4','255','q'], ['C','5','255','q'], ['R','.','.','s'], ['C','5','255','w'],
       ['C','5','255','q'], ['E','4','255','q'], ['R','.','.','s'], ['E','4','255','q'], ['C','5','255','q'], ['R','.','.','s'], ['C','5','255','q'], ['E','4','255','q'], ['F','4','255','q'], ['E','4','255','q'],
       ['D','4','255','q'], ['R','.','.','s'], ['D','4','255','q'], ['R','.','.','s'], ['D','4','255','q'], ['B','4','255','q'], ['R','.','.','s'], ['B','4','255','w'],
       ['B','4','255','q'], ['D','4','255','q'], ['R','.','.','s'], ['D','4','255','q'], ['B','4','255','q'], ['R','.','.','s'], ['B','4','255','q'], ['D','4','255','q'], ['E','4','255','q'], ['D','4','255','q'],
       ['C','4','255','q'], ['R','.','.','s'], ['C','4','255','q'], ['R','.','.','s'], ['C','4','255','q'], ['A','4','255','q'], ['R','.','.','s'], ['A','4','255','w'],
       ['A','4','255','q'], ['C','4','255','q'], ['R','.','.','s'], ['C','4','255','q'], ['A','4','255','q'], ['R','.','.','s'], ['A','4','255','q'], ['C','4','255','q'], ['D','4','255','q'], ['C','4','255','q'],
       ['B','3','255','q'], ['R','.','.','s'], ['B','3','255','q'], ['R','.','.','s'], ['B','3','255','q'], ['G#','4','255','q'], ['R','.','.','s'], ['G#','4','255','w'],
       ['G#','4','255','h'], ['A','4','255','h'], ['B','4','255','h'], ['F','4','255','h'],
       ['E','4','255','W'], ['E','4','255','W'],
       ['E','4','255','W'], ['E','4','255','W'],

       ['C','5','255','q'], ['E','4','255','q'], ['R','.','.','s'], ['E','4','255','q'], ['C','5','255','q'], ['R','.','.','s'], ['C','5','255','w'],
       ['C','5','255','q'], ['E','4','255','q'], ['R','.','.','s'], ['E','4','255','q'], ['C','5','255','q'], ['R','.','.','s'], ['C','5','255','q'], ['E','4','255','q'], ['F','4','255','q'], ['E','4','255','q'],
       ['D','4','255','q'], ['R','.','.','s'], ['D','4','255','q'], ['R','.','.','s'], ['D','4','255','q'], ['B','4','255','q'], ['R','.','.','s'], ['B','4','255','w'],
       ['B','4','255','q'], ['D','4','255','q'], ['R','.','.','s'], ['D','4','255','q'], ['B','4','255','q'], ['R','.','.','s'], ['B','4','255','q'], ['D','4','255','q'], ['E','4','255','q'], ['D','4','255','q'],
       ['C','4','255','q'], ['R','.','.','s'], ['C','4','255','q'], ['R','.','.','s'], ['C','4','255','q'], ['A','4','255','q'], ['R','.','.','s'], ['A','4','255','w'],
       ['A','4','255','q'], ['C','4','255','q'], ['R','.','.','s'], ['C','4','255','q'], ['A','4','255','q'], ['R','.','.','s'], ['A','4','255','q'], ['C','4','255','q'], ['D','4','255','q'], ['C','4','255','q'],
       ['B','3','255','q'], ['R','.','.','s'], ['B','3','255','q'], ['R','.','.','s'], ['B','3','255','q'], ['G#','4','255','q'], ['R','.','.','s'], ['G#','4','255','w'],
       ['G#','4','255','h'], ['A','4','255','h'], ['B','4','255','h'], ['F','4','255','h'],
       ['E','4','255','W'], ['E','4','255','W'],
       ['E','4','255','W'], ['E','4','255','W'],

       ['0','0','0','0']  ],


       # Dronetic ("strings")
    [  ['A','2','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'],
       ['A','2','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'],
       ['A','2','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['E','3','50','e'],
       ['A','2','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['E','3','50','e'],
       ['G#','2','50','q'], ['E','3','50','q'], ['B','3','50','q'], ['E','3','50','q'], ['D','4','50','q'], ['E','3','50','q'], ['D','4','50','q'], ['E','3','50','q'], ['E','3','50','e'], ['E','3','50','s'],
       ['G#','2','50','q'], ['E','3','50','q'], ['B','3','50','q'], ['E','3','50','q'], ['D','4','50','q'], ['E','3','50','q'], ['D','4','50','q'], ['E','3','50','q'], ['E','3','50','e'],
       ['A','2','50','q'], ['E','3','50','q'], ['A','3','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['G','2','50','q'], ['E','3','50','q'], ['E','3','50','e'], ['E','3','50','s'],
       ['F','2','50','q'], ['C','3','50','q'], ['A','3','50','q'], ['C','3','50','q'], ['A','4','50','q'], ['C','3','50','q'], ['A','3','50','q'], ['C','3','50','q'], ['C','3','50','e'],     ['C','3','50','w'], ['C','3','50','w'],
       ['E','2','50','q'], ['B','3','50','q'], ['F#','4','50','q'], ['B','3','50','q'], ['F#','4','50','q'], ['B','3','50','q'], ['F#','4','50','q'], ['B','3','50','q'],
       ['E','2','50','h'], ['B','3','50','h'], ['E','4','50','h'], ['E','3','50','h'],
       ['A','2','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'],
       ['A','2','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['E','3','50','e'],

       ['A','2','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['E','3','50','e'],
       ['A','2','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['E','3','50','e'],
       ['G#','2','50','q'], ['E','3','50','q'], ['B','3','50','q'], ['E','3','50','q'], ['D','4','50','q'], ['E','3','50','q'], ['D','4','50','q'], ['E','3','50','q'], ['E','3','50','e'], ['E','3','50','s'],
       ['G#','2','50','q'], ['E','3','50','q'], ['B','3','50','q'], ['E','3','50','q'], ['D','4','50','q'], ['E','3','50','q'], ['D','4','50','q'], ['E','3','50','q'], ['E','3','50','e'],
       ['A','2','50','q'], ['E','3','50','q'], ['A','3','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['G','2','50','q'], ['E','3','50','q'], ['E','3','50','e'], ['E','3','50','s'],
       ['F','2','50','q'], ['C','3','50','q'], ['A','3','50','q'], ['C','3','50','q'], ['A','4','50','q'], ['C','3','50','q'], ['A','3','50','q'], ['C','3','50','q'], ['C','3','50','e'],     ['C','3','50','w'], ['C','3','50','w'],
       ['E','2','50','q'], ['B','3','50','q'], ['F#','4','50','q'], ['B','3','50','q'], ['F#','4','50','q'], ['B','3','50','q'], ['F#','4','50','q'], ['B','3','50','q'],
       ['E','2','50','h'], ['B','3','50','h'], ['E','4','50','h'], ['E','3','50','h'],
       ['A','2','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'],
       ['A','2','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['E','3','50','e'],

       ['A','2','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['E','3','50','e'],
       ['A','2','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['E','3','50','e'],
       ['G#','2','50','q'], ['E','3','50','q'], ['B','3','50','q'], ['E','3','50','q'], ['D','4','50','q'], ['E','3','50','q'], ['D','4','50','q'], ['E','3','50','q'], ['E','3','50','e'], ['E','3','50','s'],
       ['G#','2','50','q'], ['E','3','50','q'], ['B','3','50','q'], ['E','3','50','q'], ['D','4','50','q'], ['E','3','50','q'], ['D','4','50','q'], ['E','3','50','q'], ['E','3','50','e'],
       ['A','2','50','q'], ['E','3','50','q'], ['A','3','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['G','2','50','q'], ['E','3','50','q'], ['E','3','50','e'], ['E','3','50','s'],
       ['F','2','50','q'], ['C','3','50','q'], ['A','3','50','q'], ['C','3','50','q'], ['A','4','50','q'], ['C','3','50','q'], ['A','3','50','q'], ['C','3','50','q'], ['C','3','50','e'],     ['C','3','50','w'], ['C','3','50','w'],
       ['E','2','50','q'], ['B','3','50','q'], ['F#','4','50','q'], ['B','3','50','q'], ['F#','4','50','q'], ['B','3','50','q'], ['F#','4','50','q'], ['B','3','50','q'],
       ['E','2','50','h'], ['B','3','50','h'], ['E','4','50','h'], ['E','3','50','h'],
       ['A','2','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'],
       ['A','2','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['C','4','50','q'], ['E','3','50','q'], ['E','3','50','e'],

       ['0','0','0','0']  ],


       # eSpeak (lyrics)
    [  ['R','.','.','w'], ['R','.','.','w'], 
       ['R','.','.','w'], ['R','.','.','w'], 
       ['where','.','.','.'], ['do_i','.','.','.'], ['R','.','.','h'], ['begin','.','.','.'], ['R','.','.','w'],
       ['to_tell','.','.','.'], ['R','.','.','w'], ['the','.','.','.'], ['story_of','.','.','.'], ['R','.','.','w'], ['R','.','.','q'], 
       ['how_great','.','.','.'], ['R','.','.','h'], ['a_love','.','.','.'], ['R','.','.','h'], ['can_be','.','.','.'], ['R','.','.','w'], 
       ['the_sweet','.','.','.'], ['love_story','.','.','.'], ['R','.','.','w'], ['that_is','.','.','.'], ['R','.','.','q'], 
       ['older','.','.','.'], ['R','.','.','h'], ['than','.','.','.'], ['R','.','.','h'], ['the_sea','.','.','.'], ['R','.','.','q'], 
       ['the_simple','.','.','.'], ['R','.','.','h'], ['truth','.','.','.'], ['R','.','.','h'], ['about_the','.','.','.'], ['R','.','.','q'], 
       ['love_she','.','.','.'], ['R','.','.','h'], ['brings','.','.','.'], ['R','.','.','h'], ['to_me','.','.','.'], ['R','.','.','q'], 
       ['where','.','.','.'], ['R','.','.','h'], ['do','.','.','.'], ['R','.','.','h'], ['i','.','.','.'], ['R','.','.','h'], ['start','.','.','.'], 
       #['R','.','.','w'], ['R','.','.','w'], 

       ['R','.','.','h'], ['this','.','.','.'], ['technology','.','.','.'], ['R','.','.','w'],
       ['is','.','.','.'], ['R','.','.','w'], ['so','.','.','.'], ['inadequate','.','.','.'], ['R','.','.','w'], ['R','.','.','q'], 
       ['i_am','.','.','.'], ['R','.','.','h'], ['fed_up','.','.','.'], ['R','.','.','h'], ['with_it','.','.','.'], ['R','.','.','w'], 
       ['i_am','.','.','.'], ['a','.','.','.'], ['professional','.','.','.'], ['R','.','.','q'], ['R','.','.','w'], 
       ['R','.','.','h'], ['technology','.','.','.'], ['always','.','.','.'], ['promises','.','.','.'], ['R','.','.','q'], ['R','.','.','h'], 
       ['more_than','.','.','.'], ['R','.','.','h'], ['it_can','.','.','.'], ['deliver','.','.','.'], ['R','.','.','q'], ['R','.','.','h'], 
       ['new','.','.','.'], ['R','.','.','q'], ['notes','.','.','.'], ['R','.','.','h'], ['cannot_even','.','.','.'], 
       ['play','.','.','.'], ['R','.','.','h'], ['while','.','.','.'], ['R','.','.','h'], ['i','.','.','.'], ['R','.','.','h'], ['speak','.','.','.'], 
       ['R','.','.','w'], ['R','.','.','h'], 

       ['how','.','.','.'], ['long_does','.','.','.'], ['R','.','.','h'], ['it_last','.','.','.'], ['R','.','.','w'],
       ['can_love','.','.','.'], ['R','.','.','w'], ['be','.','.','.'], ['measured_by','.','.','.'], ['R','.','.','w'], ['R','.','.','q'], 
       ['the','.','.','.'], ['R','.','.','h'], ['hours_in','.','.','.'], ['R','.','.','h'], ['a_day','.','.','.'], ['R','.','.','w'], 
       ['i_have','.','.','.'], ['no_answers','.','.','.'], ['R','.','.','w'], ['now','.','.','.'], ['R','.','.','q'], 
       ['but_this','.','.','.'], ['R','.','.','h'], ['much_i','.','.','.'], ['R','.','.','h'], ['can_say','.','.','.'], ['R','.','.','q'], 
       ['i_know','.','.','.'], ['R','.','.','h'], ['isle','.','.','.'], ['R','.','.','h'], ['need_her','.','.','.'], ['R','.','.','q'], 
       ['till_the','.','.','.'], ['R','.','.','h'], ['stars_all','.','.','.'], ['R','.','.','h'], ['burn_away','.','.','.'], ['R','.','.','q'], 
       ['and','.','.','.'], ['R','.','.','h'], ['sheel','.','.','.'], ['R','.','.','h'], ['be','.','.','.'], ['R','.','.','h'], ['there','.','.','.'], 

       ['0','0','0','0']  ]
]


ThisGuysInLove = [
       # Thick (bass)
    [  ['D#','2','255','w'], ['D#','2','255','w'], ['D#','2','255','e'], ['D#','2','255','s'],
       ['G#','2','255','w'], ['G#','2','255','h'], ['G#','2','255','q'], ['A#','2','255','q'], ['A#','2','255','e'], ['A#','2','255','s'], 
       ['D#','2','255','w'], ['D#','2','255','w'], ['D#','2','255','e'], ['D#','2','255','s'],
       ['G#','2','255','w'], ['G#','2','255','h'], ['G#','2','255','q'], ['A#','2','255','q'], ['A#','2','255','e'], ['A#','2','255','s'], 
       ['D#','2','255','h'], ['D#','2','255','q'], ['R','.','.','q'], ['D#','2','255','h'], ['D#','2','255','q'], ['R','.','.','q'], ['R','.','.','e'], ['R','.','.','s'],
       ['G#','2','255','h'], ['G#','2','255','q'], ['R','.','.','q'], ['G#','2','255','h'], ['G#','2','255','q'], ['R','.','.','q'], ['R','.','.','e'],
       ['G#','2','255','h'], ['G#','2','255','q'], ['R','.','.','q'], ['G#','2','255','h'], ['G#','2','255','q'], ['R','.','.','q'], ['R','.','.','e'], ['R','.','.','s'],
       ['C#','2','255','h'], ['C#','2','255','q'], ['R','.','.','q'], ['C#','2','255','h'], ['C#','2','255','q'], ['R','.','.','q'], ['R','.','.','e'], ['R','.','.','s'],

       ['C#','2','255','w'], ['C#','2','255','w'], 
       ['C#','2','200','w'], ['C#','2','200','w'], 
       ['C#','2','255','w'], ['C#','2','170','w'], 
       ['C#','2','130','w'], ['C#','2','130','w'], 
       ['C#','2','100','w'], ['C#','2','100','w'], 
       ['C#','2','100','w'], ['C#','2','100','w'], 
       ['C#','2','100','w'], ['C#','2','100','w'], 
       ['C#','2','100','w'], ['C#','2','100','w'], 
       ['C#','2','100','w'], ['C#','2','100','w'], 
       ['C#','2','100','w'], ['C#','2','100','w'], 
       ['C#','2','100','w'], ['C#','2','100','w'], 
       ['C#','2','130','w'], ['C#','2','130','w'], 
       ['C#','2','170','w'], ['C#','2','170','w'], 
       ['C#','2','200','w'], ['C#','2','200','w'], 
       ['C#','2','255','w'], ['C#','2','255','w'], 

       ['D#','2','255','h'], ['D#','2','255','q'], ['R','.','.','q'], ['D#','2','255','h'], ['D#','2','255','q'], ['R','.','.','q'], ['R','.','.','e'], ['R','.','.','s'],
       ['D#','2','255','w'], ['D#','2','255','w'],

       ['0','0','0','0']  ],


       # Hocus (melody)
    [  ['R','.','.','h'], ['G','4','255','q'], ['R','.','.','s'], ['G','4','255','q'], ['G','4','255','h'], ['R','.','.','s'], ['G','4','255','q'], ['R','.','.','s'], ['G','4','255','q'], 
       ['R','.','.','h'], ['G','4','255','q'], ['R','.','.','s'], ['G','4','255','q'], ['G','4','255','q'], ['G','4','255','s'], ['F','4','255','q'], ['F','4','255','s'], ['G','4','255','h'], 
       ['R','.','.','h'], ['G','4','255','q'], ['R','.','.','s'], ['G','4','255','q'], ['G','4','255','h'], ['R','.','.','s'], ['G','4','255','q'], ['R','.','.','s'], ['G','4','255','q'], 
       ['R','.','.','h'], ['G','4','255','q'], ['R','.','.','s'], ['G','4','255','q'], ['G','4','255','q'], ['G','4','255','s'], ['F','4','255','q'], ['F','4','255','s'], ['G','4','255','h'], 
       ['R','.','.','h'], ['G','4','255','q'], ['R','.','.','s'], ['G','4','255','q'], ['G','4','255','h'], ['R','.','.','s'], ['G','4','255','q'], ['R','.','.','s'], ['G','4','255','q'], 
       ['G','4','255','h'], ['G','4','255','q'], ['R','.','.','w'], ['G','4','255','q'], 
       ['C','5','255','h'], ['C','4','255','h'], ['D#','4','255','q'], ['F','4','255','h'], ['R','.','.','s'], ['F','4','255','q'], 
       ['F','4','255','w'], ['F','4','255','h'], ['R','.','.','h'],

       ['F','4','255','w'], ['F','4','255','w'],
       ['F','4','200','w'], ['F','4','200','w'],
       ['F','4','170','w'], ['F','4','170','w'],
       ['F','4','130','w'], ['F','4','130','w'],
       ['F','4','100','w'], ['F','4','100','w'],
       ['F','4','100','w'], ['F','4','100','w'],
       ['F','4','100','w'], ['F','4','100','w'],
       ['F','4','100','w'], ['F','4','100','w'],
       ['F','4','100','w'], ['F','4','100','w'],
       ['F','4','100','w'], ['F','4','100','w'],
       ['F','4','100','w'], ['F','4','100','w'],
       ['F','4','100','w'], ['F','4','100','w'],
       ['F','4','100','w'], ['F','4','100','w'],
       ['F','4','100','w'], ['F','4','100','w'],
       ['F','4','100','w'], ['F','4','100','w'],
       ['F','4','130','w'], ['F','4','130','w'],
       ['F','4','170','w'], ['F','4','170','w'],
       ['F','4','200','w'], ['F','4','200','w'],
       ['F','4','255','w'], ['F','4','255','w'],

       ['R','.','.','h'], ['G','4','255','q'], ['R','.','.','s'], ['G','4','255','q'], ['G','4','255','h'], ['R','.','.','s'], ['G','4','255','q'], ['R','.','.','s'], ['G','4','255','q'], 
       ['G','4','255','w'], ['G','4','255','w'],

       ['0','0','0','0']  ],


       # Dronetic ("strings")
    [  ['R','.','.','h'], ['A#','4','80','q'], ['R','.','.','s'], ['A#','4','80','q'], ['A#','4','80','h'], ['R','.','.','s'], ['A#','4','80','q'], ['R','.','.','s'], ['A#','4','80','q'], 
       ['R','.','.','h'], ['C','4','80','q'], ['R','.','.','s'], ['C','4','80','q'], ['C','4','80','q'], ['R','.','.','s'], ['C','4','80','q'], ['R','.','.','s'], ['C','4','80','h'], 
       ['R','.','.','h'], ['A#','4','80','q'], ['R','.','.','s'], ['A#','4','80','q'], ['A#','4','80','h'], ['R','.','.','s'], ['A#','4','80','q'], ['R','.','.','s'], ['A#','4','80','q'], 
       ['R','.','.','h'], ['C','4','80','q'], ['R','.','.','s'], ['C','4','80','q'], ['C','4','80','q'], ['R','.','.','s'], ['C','4','80','q'], ['R','.','.','s'], ['C','4','80','h'], 
       ['R','.','.','h'], ['A#','4','80','q'], ['R','.','.','s'], ['A#','4','80','q'], ['A#','4','80','h'], ['R','.','.','s'], ['A#','4','80','q'], ['R','.','.','s'], ['A#','4','80','q'], 
       ['R','.','.','h'], ['C','4','80','q'], ['R','.','.','s'], ['C','4','80','q'], ['C','4','80','h'], ['R','.','.','s'], ['C','4','80','q'], ['R','.','.','q'],
       ['C','4','80','h'], ['R','.','.','s'], ['C','4','80','h'], ['G','4','80','q'], ['R','.','.','s'], ['G','4','80','h'], ['R','.','.','s'], ['G#','4','80','q'], 
       ['G#','4','80','h'], ['R','.','.','s'], ['G#','4','80','q'], ['R','.','.','s'], ['G#','4','80','q'], ['G#','4','80','q'], ['R','.','.','s'], ['A#','4','80','q'], ['G#','4','80','q'],

       ['G#','4','80','w'], ['G#','4','80','w'],
       ['G#','4','60','w'], ['G#','4','60','w'],
       ['G#','4','40','w'], ['G#','4','40','w'],
       ['G#','4','40','w'], ['G#','4','40','w'],
       ['G#','4','40','w'], ['G#','4','40','w'],
       ['G#','4','40','w'], ['G#','4','40','w'],
       ['G#','4','40','w'], ['G#','4','40','w'],
       ['G#','4','40','w'], ['G#','4','40','w'],
       ['G#','4','40','w'], ['G#','4','40','w'],
       ['G#','4','40','w'], ['G#','4','40','w'],
       ['G#','4','40','w'], ['G#','4','40','w'],
       ['G#','4','40','w'], ['G#','4','40','w'],
       ['G#','4','40','w'], ['G#','4','40','w'],
       ['G#','4','40','w'], ['G#','4','40','w'],
       ['G#','4','60','w'], ['G#','4','60','w'],
       ['G#','4','80','w'], ['G#','4','80','w'],

       ['R','.','.','h'], ['A#','4','80','q'], ['R','.','.','s'], ['A#','4','80','q'], ['A#','4','80','h'], ['R','.','.','s'], ['A#','4','80','q'], ['R','.','.','s'], ['A#','4','80','q'], 
       ['A#','4','80','w'], ['A#','4','80','w'],

       ['0','0','0','0']  ],


       # eSpeak (lyrics)
    [  ['R','.','.','w'], ['R','.','.','w'],
       ['R','.','.','w'], ['R','.','.','w'],
       ['R','.','.','w'], ['R','.','.','w'],
       ['R','.','.','w'], ['R','.','.','w'],
       ['R','.','.','q'], ['you','.','.','.'], ['R','.','.','e'], ['see','.','.','.'], ['R','.','.','q'], ['this','.','.','.'], ['R','.','.','h'], ['guy','.','.','.'], 
       ['R','.','.','w'], ['R','.','.','h'], ['this','.','.','.'], 
       ['R','.','.','q'], ['guys','.','.','.'], ['R','.','.','e'], ['in','.','.','.'], ['R','.','.','q'], ['love_with','.','.','.'], ['R','.','.','h'], ['you','.','.','.'], 

       ['R','.','.','w'], ['R','.','.','w'],
       ['R','.','.','w'], ['R','.','.','w'],
       ['R','.','.','w'], ['R','.','.','w'],
       ['i','.','.','.'], ['R','.','.','s'], ['used','.','.','.'], ['R','.','.','s'], ['to_play','.','.','.'], ['R','.','.','s'], ['good','.','.','.'], 
       ['R','.','.','s'], ['music','.','.','.'], 
       ['R','.','.','w'], ['i','.','.','.'], ['R','.','.','s'], ['used','.','.','.'], ['R','.','.','s'], ['to','.','.','.'], ['R','.','.','s'], ['make','.','.','.'], 
       ['R','.','.','s'], ['choices','.','.','.'], ['R','.','.','s'], ['in','.','.','.'], ['R','.','.','s'], ['my','.','.','.'], ['R','.','.','s'], ['life','.','.','.'], 
       ['R','.','.','w'], ['since','.','.','.'], ['R','.','.','s'], ['being','.','.','.'], ['R','.','.','s'], ['uploaded','.','.','.'], ['R','.','.','s'], ['into','.','.','.'], 
       ['R','.','.','s'], ['a','.','.','.'], ['R','.','.','s'], ['computer','.','.','.'],
       ['R','.','.','e'], ['i','.','.','.'], ['R','.','.','s'], ['only','.','.','.'], ['R','.','.','s'], ['do','.','.','.'], ['R','.','.','s'], ['what','.','.','.'], 
       ['R','.','.','s'], ['i_am','.','.','.'], ['R','.','.','s'], ['programmed','.','.','.'], ['R','.','.','s'], ['to','.','.','.'], ['R','.','.','s'], ['do','.','.','.'], 

       ['R','.','.','w'], ['yes','.','.','.'], ['R','.','.','e'], ['eyem','.','.','.'], ['R','.','.','q'], ['in','.','.','.'], ['R','.','.','h'], ['love','.','.','.'], 

       ['0','0','0','0']  ]
]


#--------------------------------------------------
#--------------------------------------------------
#
# songList is a list of all of the above songs
#
# To access a record in any of the above songs:
#     songList[i][j][k][l]
# where:
#              i = index into which song list 
#                       (if there are 3 songs, then this is 0..2)
#              j = index into note records to play for a given synth 
#                       (for 3 synths plus eSpeak, this is 0..2 for the 3 ArduTouch synths, plus 3 for eSpeak)
#              k = index into the note records, which contain: note, octave, volume, duration 
#                       (if a song contains 103 notes (and rests) to play, then this is 0..102)
#              l = index into a given note record:
#                       0 -- note (or lyric word for eSpeak)
#                       1 -- octave
#                       2 -- volume
#                       3 -- duration
#
# Examples:
#     to access the note to play in the 12th note record for the 1st synth (Thick) in the 2nd song:
#          songList[1][0][11][0]
#     to access the octave for the note to play in the 12th note record for the 1st synth (Thick) in the 2nd song:
#          songList[1][0][11][1]
#     to access the volume for the note to play in the 12th note record for the 1st synth (Thick) in the 2nd song:
#          songList[1][0][11][2]
#     to access the duration for the note to play in the 12th note record for the 1st synth (Thick) in the 2nd song:
#          songList[1][0][11][3]
#     to access the lyric word to "sing" (on eSpeak, synth num 3) in the 2nd note record in the 2nd song:
#          songList[1][3][1][0]
#
#--------------------------------------------------
#--------------------------------------------------

songList = [ MyWay, MoonRiver, StrangersInTheNight, LoveStory, ThisGuysInLove ]



#--------------------------------------------------
#--------------------------------------------------
#
# Transform the noteData strings from the Song list 
#   to the ArduTouch commands for the note data.
#
#--------------------------------------------------
#--------------------------------------------------

def xformNoteData(synth):
    global noteCount0, noteCount1, noteCount2, noteCount3
    global songList
    global note0, note1, note2, note3
    global dur0, dur1, dur2, dur3
    global oct0, oct1, oct2
    global vol0, vol1, vol2

    # synth 0 (Thick):
    # Read the strings for note, octave, volume, and duration from the song list record indexed by noteCount0
    # and store them into global variables.
    if ( synth == 0 ):
        note0 = songList[songChoice][0][noteCount0][0]
        oct0 = songList[songChoice][0][noteCount0][1]   # no transformation needed
        vol0 = songList[songChoice][0][noteCount0][2]   # no transformation needed
        duration0 = songList[songChoice][0][noteCount0][3]
        #print ("                    0: ", note0, oct0, vol0, duration0)

    # synth 1 (Hocus):
    # Read the strings for note, octave, volume, and duration from the song list record indexed by noteCount1
    # and store them into global variables.
    if ( synth == 1 ):
        note1 = songList[songChoice][1][noteCount1][0]
        oct1 = songList[songChoice][1][noteCount1][1]   # no transformation needed
        vol1 = songList[songChoice][1][noteCount1][2]   # no transformation needed
        duration1 = songList[songChoice][1][noteCount1][3]
        #print ("                    1: ", note1, oct1, vol1, duration1)

    # synth 2 (Dronetic):
    # Read the strings for note, octave, volume, and duration from the song list record indexed by noteCount2
    # and store them into global variables.
    if ( synth == 2 ):
        note2 = songList[songChoice][2][noteCount2][0]
        oct2 = songList[songChoice][2][noteCount2][1]   # no transformation needed
        vol2 = songList[songChoice][2][noteCount2][2]   # no transformation needed
        duration2 = songList[songChoice][2][noteCount2][3]
        #print ("                    2: ", note2, oct2, vol2, duration2)   # DEBUG

    # synth 3 (eSpeak):
    # Read the strings for note and duration from the song list record indexed by noteCount3
    # and store them into global variables.
    if ( synth == 3 ):
        note3 = songList[songChoice][3][noteCount3][0]
        duration3 = songList[songChoice][3][noteCount3][3]
        #print ("                    3: ", note3, " ", " ", duration3)

    # Transform the note strings according to the following lists
    # and store the results into note0, note1, note2 (which are global)
    notes  = [ 'C','C#','D','D#','E','F','F#','G','G#','A','A#','B' ]
    xNotes = [ 'z','s', 'x','d', 'c','v','g', 'b','h', 'n','j', 'm' ]

    if ( synth == 0 ):
        for i in range(0, 12):
            if ( note0 == notes[i] ):
                note0 = xNotes[i]

    if ( synth == 1 ):
        for i in range(0, 12):
            if ( note1 == notes[i] ):
                note1 = xNotes[i]

    if ( synth == 2 ):
        for i in range(0, 12):
            if ( note2 == notes[i] ):
                note2 = xNotes[i]

    if ( synth == 3 ):
        pass        # for eSpeak, there is no transformation for note3 (either 'R' or a lyric word)

    # Transform the duration strings according to the following lists
    # and store the result into dur0, dur1, dur2 (which are global).
    # Then convert to integers, and subtract one, 
    # since the number of ticks (to play a note) goes down to 0 (rather than down to 1).
    durs  = [ 'w', 'h','q','e','s' ]
    xDurs = [ '16','8','4','2','1' ]

    if ( synth == 0 ):
        for i in range(0, 5):
            if ( duration0 == durs[i] ):
                dur0 = int( xDurs[i] ) - 1

    if ( synth == 1 ):
        for i in range(0, 5):
            if ( duration1 == durs[i] ):
                dur1 = int( xDurs[i] ) - 1

    if ( synth == 2 ):
        for i in range(0, 5):
            if ( duration2 == durs[i] ):
                dur2 = int( xDurs[i] ) - 1

    if ( (synth == 3) and (note3 == 'R') ):
        for i in range(0, 5):
            if ( duration3 == durs[i] ):
                dur3 = int( xDurs[i] ) - 1
    # if there is a lyric word in note3, then the duration is 0 
    # (so that at the next tick the next lyric word is sent to eSpeak)
    else:
        dur3 = 0

    # DEBUG
    #if ( (synth == 0) and (not endOfSongSynth0) ):
        #print ("                       ", note0, oct0, vol0, dur0)
    #if ( (synth == 1) and (not endOfSongSynth1) ):
        #print ("                       ", note1, oct1, vol1, dur1)
    #if ( (synth == 2) and (not endOfSongSynth2) ):
        #print ("                       ", note2, oct2, vol2, dur2)
    #if ( (synth == 3) and (not endOfSongSynth3) ):
        #print ("                       ", note3, " ", " ", dur3)



#--------------------------------------------------
#--------------------------------------------------
#
# Send a string to a serial port
#
# portNum is an integer: 0, 1, or 2
# sendStr a string: any value, one or more characters
#
#--------------------------------------------------
#--------------------------------------------------

def str2port(portNum, sendStr):

    if ( portNum == 0 ):
        serialPort0.write( bytes(sendStr,'utf-8') )
        serialPort0.flush()

    if ( portNum == 1 ):
        serialPort1.write( bytes(sendStr,'utf-8') )
        serialPort1.flush()

    if ( portNum == 2 ):
        serialPort2.write( bytes(sendStr,'utf-8') )
        serialPort2.flush()



#--------------------------------------------------
#--------------------------------------------------
#
# Reset a synth
#    by toggling the serial port's RTS line 
#    (which is ArduTouch/Arduino board's reset line)
#
# portNum is an integer: 0, 1, or 2
#
#--------------------------------------------------
#--------------------------------------------------

def resetSynth(portNum):

    #print ("                        resetting synth ", portNum, "...")   # DEBUG

    if (portNum == 0):
        serialPort0.setRTS(True)   # RTS (reset) High
        time.sleep(0.1)            # let RTS settle
        serialPort0.setRTS(False)  # RTS (reset) back Low
        time.sleep(0.1)            # let RTS settle

    if (portNum == 1):
        serialPort1.setRTS(True)   # RTS (reset) High
        time.sleep(0.1)            # let RTS settle
        serialPort1.setRTS(False)  # RTS (reset) back Low
        time.sleep(0.1)            # let RTS settle

    if (portNum == 2):
        serialPort2.setRTS(True)   # RTS (reset) High
        time.sleep(0.1)            # let RTS settle
        serialPort2.setRTS(False)  # RTS (reset) back Low
        time.sleep(0.1)            # let RTS settle

    #print ("                        ......................done") # DEBUG



#--------------------------------------------------
#--------------------------------------------------
#
# Set volume level of a synth
#
# synthNum is an integer: 0, 1, or 2
# volLevel is a string: between '0' and '255'
#
#--------------------------------------------------
#--------------------------------------------------

def setVolume(synthNum, volLevel):

    str2port(synthNum, "v")        # volume command
    str2port(synthNum, volLevel)   # choose volume level
    str2port(synthNum, "\\")       # set volume and exit volume menu
    #print ("setVol: ", synthNum, volLevel)               # DEBUG



#--------------------------------------------------
#--------------------------------------------------
#
# Fade out note playing on a synth
#
# synthNum is an integer: 0, 1, or 2
#
#--------------------------------------------------
#--------------------------------------------------

def fadeSynth(synthNum):

    setVolume(synthNum, "200")        # set synth 2 to volume level of 200
    time.sleep(0.001)
    setVolume(synthNum, "180")
    time.sleep(0.001)
    setVolume(synthNum, "150")
    time.sleep(0.001)
    setVolume(synthNum, "100")
    time.sleep(0.001)
    setVolume(synthNum, "80")
    time.sleep(0.001)
    setVolume(synthNum, "60")
    time.sleep(0.001)
    setVolume(synthNum, "40")
    time.sleep(0.001)
    setVolume(synthNum, "20")
    time.sleep(0.001)
    setVolume(synthNum, "0")



#--------------------------------------------------
#--------------------------------------------------
#
# send a note to a synth
#
# synthNum is an integer: 0, 1, or 2
# note is a string: 'z' 's' 'x' 'd' 'c' 'v' 'g' 'b' 'h' 'n' 'j' 'm'
# octave is a string:  between '0' and '7'
#
#--------------------------------------------------
#--------------------------------------------------

def sendNote(synthNum, note, octave):

    str2port(synthNum, "k")       # enter keyboard menu
    #print ("k,", end="")      # DEBUG
    str2port(synthNum, octave)   # choose octave
    #print (octave, end=",")   # DEBUG
    str2port(synthNum, note )    # play note
    #print (note, end=",")     # DEBUG
    str2port(synthNum, "`")       # exit keyboard menu
    #print ("`")               # DEBUG



#--------------------------------------------------
#--------------------------------------------------
#
# stop playing the note on a synth
#
# synthNum is an integer: 0, 1, or 2
#
#--------------------------------------------------
#--------------------------------------------------

def stopNote(synthNum):

    str2port(synthNum, "k")     # enter keyboard menu
    #print ("k,", end="")    # DEBUG
    str2port(synthNum, " ")     # stop playing note
    #print ( " ", end=",")   # DEBUG
    str2port(synthNum, "`")     # exit keyboard menu
    #print ("`")             # DEBUG



#--------------------------------------------------
#--------------------------------------------------
#
# Initialize for playing of the synths:
#   If cold = True (used for first time initializing):
#       * open serial ports
#       * reset synths
#       * exit remote mode in synths
#       * play one note on each synth (at very low volume) 
#         to get past (since the first note on some synths is an anomaly)
#       * set up GPIO23 as an input with pull-up resistors enabled
#       * start interrupts for every falling edge on GPIO23
#   If cold = False (used for re-initializing during operation):
#       * reset synths
#       * exit remote mode in synths
#       * play one note on each synth (at very low volume) 
#         to get past (since the first note on some synths is an anomaly)
#
#--------------------------------------------------
#--------------------------------------------------

def initSynthPlaying( cold ):
    global serialPort0, serialPort1, serialPort2

    print ("")
    print ("")
    print ("Resetting everything for the next consumer with unique desires...")
    time.sleep(0.6)
    print ("    Please enjoy waiting patiently...")
    print ("")
    print ("")

    # Send text to a window with mod graphics
    width = 1400
    height = 500
    textX = 210
    textY = 60
    text1 = "Resetting everything for the"
    text2 = "          next consumer with unique desires..."
    text3 = ""
    text4 = ""
    text5 = "               Please enjoy waiting patiently..."
    text6 = ""
    msTime = 4000   # 4 seconds
    #msTime = 500   # DEV DEBUG
    mgtw.createModGraphicWindow(width, height, textX, textY, text1, text2, text3, text4, text5, text6, msTime)

    # For a cold initialization, open serial ports.
    if ( cold ):
        # open serial ports
        print ("Opening serial ports...")
        serialPort0 = serial.Serial( port="/dev/ttyUSB0", baudrate=115200, bytesize=8, timeout=2, stopbits=serial.STOPBITS_ONE )
        serialPort1 = serial.Serial( port="/dev/ttyUSB1", baudrate=115200, bytesize=8, timeout=2, stopbits=serial.STOPBITS_ONE )
        serialPort2 = serial.Serial( port="/dev/ttyUSB2", baudrate=115200, bytesize=8, timeout=2, stopbits=serial.STOPBITS_ONE )
        time.sleep(2)  # give the ArduTouch board time to reset
        print (".......................done")

    # reset synths
    print ("Resetting synths...")
    resetSynth(0)
    resetSynth(1)
    resetSynth(2)
    time.sleep(3)      # gived synths time to reset
    print ("....................done")

    if ( cold ):
        # exit remote mode
        print ("Exit remote mode...")
        str2port(0, "`")
        str2port(1, "`")
        str2port(2, "`")
        print ("...................done")

    # Play one note on each synth (at very low volume)
    # (since the first note on some synths is an anomaly).
    print ("Playing initial note on each synth...")
    setVolume(0, "20")         # set synth 0 to volume level of 20
    sendNote(0, "x", "3")      # send note C octave 3 to synth 0 (Thick)
    setVolume(1, "5")          # set synth 1 to volume level of 5
    sendNote(1, "b", "3")      # send note G octave 3 to synth 1 (Hocus)
    setVolume(2, "10")         # set synth 2 to volume level of 10
    sendNote(2, "b", "2")      # send note G octave 2 to synth 2 (Dronetic)
    time.sleep(3)              # give the ArduTouch boards time to finish playing their notes
    #time.sleep(2)  # DEV DEBUG
    stopNote(0)                # stop playing note on Thick
    stopNote(1)                # stop playing note on Hocus
    stopNote(2)                # stop playing note on Dronetic
    setVolume(2, "0")          # set Dronetic to volume level of 0 (to stop drone)
    time.sleep(1)
    print (".....................................done")
    
    # For a cold initialization, set up GPIO23 for interrupts.
    if ( cold ):
        # use GPIO port numbers for GPIO module (in our case we will use GPIO23)
        GPIO.setmode(GPIO.BCM)

        # Set up GPIO23 (pin 16) as input with pull-up resistor enabled:
        GPIO.setup(23, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # Start interrupts for every falling edge on GPIO23:
        print ("Starting interrupts...")
        #GPIO.add_event_detect(23, GPIO.FALLING, callback=metronome, bouncetime=200)   # DEBUG bouncetime
        GPIO.add_event_detect(23, GPIO.FALLING, callback=metronome)
        print ("......................done")



#--------------------------------------------------
#--------------------------------------------------
#
# shut down playing of the synths:
#   if final shut down (to end program):
#       * shut down GPIO23 calling metronome() on every falling edge
#       * stop note playing on each synth
#       * close serial ports
#
#   if not final shut down (in normal program operation while playing songs):
#       * stop note playing on each synth
#
#--------------------------------------------------
#--------------------------------------------------

def shutDownSynthPlaying( final ):

    if ( final ):
        # shut down and clean up the interrupt on GPIO23
        GPIO.remove_event_detect(23)
        GPIO.cleanup()

    # stop playing notes on synths
    # I don't know why, but stopping notes here makes it so that the synths won't play again
    # so I commented these out. There should be no notes playing at this point, anyhow.
    print ("stop notes on synths...")
    stopNote(0)               # stop any note still playing on Thick on ttyUSB0
    stopNote(1)               # stop any note still playing on Hocus on ttyUSB1
    stopNote(2)               # stop any note still playing on Dronetic on ttyUSB2
    print (".......................done")

    if ( final ):
        # close serial ports
        print ("Close serial ports...")
        serialPort0.close()
        serialPort1.close()
        serialPort2.close()
        print (".....................done")


#--------------------------------------------------
#--------------------------------------------------
#
# clear the screen
#
# Since Python doesn't have a built-in command for clearing the screen, this function does it.
#
#--------------------------------------------------
#--------------------------------------------------

def clear():
    _ = system('clear')



#--------------------------------------------------
#--------------------------------------------------
#
# Main program 
#
#--------------------------------------------------
#--------------------------------------------------

metronomeON = False

# Do cold initialization the first time through the main task loop
cold = True      # first initialization is cold (subsequent initializations are warm)
songChoice = 0   # choice of song to play  # DEBUG -- init to first song

#===============
#===============
# main task loop
#===============
#===============
while True:

    # wait a little bit before clearning the screen
    time.sleep(1)

    # clear the screen
    clear()

    # Print credits
    print ("")
    print ("")
    print ("")
    print ("")
    print ("")
    print ("                       LOUNGE LOOKER")
    time.sleep(0.25)
    print ("                            by")
    #time.sleep(0.25)
    print ("                       Mitch Altman")
    print ("")
    print ("")
    print ("")
    print ("")
    print ("")

    # Send text to a window with mod graphics
    width = 1000
    height = 500
    textX = 275
    textY = 60
    text1 = ""
    text2 = "LOUNGE LOOKER"
    text3 = "     by"
    text4 = "Mitch Altman"
    text5 = ""
    text6 = ""
    msTime = 5000   # 5 seconds
    #msTime = 500   # DEV DEBUG
    mgtw.createModGraphicWindow2(width, height, textX, textY, text1, text2, text3, text4, text5, text6, msTime)

    # main task loop init
    count = 0
    noteCount0 = 0
    noteCount1 = 0
    noteCount2 = 0
    noteCount3 = 0
    lastNotePlaying0 = False
    lastNotePlaying1 = False
    lastNotePlaying2 = False
    endOfSongSynth0 = False
    endOfSongSynth1 = False
    endOfSongSynth2 = False
    endOfSongSynth3 = False
    # The tick count for each synth is initialized to 0,
    # since the next note (in this case the first note) is only played when the tick count is decrimented down to 0.
    synth0TickCount = 0  
    synth1TickCount = 0
    synth2TickCount = 0
    synth3TickCount = 0

    # Do initialization (first time is cold, and from then on, warm)
    initSynthPlaying(cold)
    cold = False

    # wait a little bit before clearning the screen
    time.sleep(1)

    # clear the screen
    clear()

    # Print greeting
    print ("")
    print ("")
    print ("")
    print ("")
    print ("")
    print ("                       WE ARE ABOUT TO CALCULATE YOUR DESIRES")
    time.sleep(0.6)
    print ("                 AND CHOOSE THE PERFECT SONG TO FULFILL THEM!")
    print ("")
    print ("")
    print ("")
    print ("")
    print ("")

    # Send text to a window with mod graphics
    width = 1500
    height = 500
    textX = 125
    textY = 60
    text1 = ""
    text2 = ""
    text3 = ""
    text4 = "           We Are About to Calculate Your Desires"
    text5 = ""
    text6 = "     and Choose the PERFECT LOUNGE SONG to Fulfill Them!"
    msTime = 5000   # 5 seconds
    #msTime = 500   # DEV DEBUG
    mgtw.createModGraphicWindow(width, height, textX, textY, text1, text2, text3, text4, text5, text6, msTime)

    # wait for webcam to "look" at a face and "choose" a song to play
    songChoice = lc.lookChoose()
    #songChoice = 1   # DEV DEBUG

    #---------------
    # play the chosen song on the ArduTouch boards and eSpeach
    metronomeON = True
    while(not (endOfSongSynth0 and endOfSongSynth1 and endOfSongSynth2 and endOfSongSynth3) ):
        #print ("Main task loop...")   # DEBUG
        #time.sleep(0.2)   # DEBUG
        pass
    metronomeON = False


    #---------------
    # Reached end of song, so shut down the synthesizers
    print ("")
    print ("")
    #print ("END OF SONG REACHED", count, 
            #endOfSongSynth0, endOfSongSynth1, endOfSongSynth2, endOfSongSynth3, 
            #"  noteCount: ", noteCount0, noteCount1, noteCount2, noteCount3)   # DEBUG
    # shut down synths
    final = False
    shutDownSynthPlaying( final )

    # short delay before the thank you screen
    time.sleep(2)
    #time.sleep(0.1)   # DEV DEBUG

    print ("")
    print ("")
    print ("")
    print ("")
    print ("")
    print ("               Thank you for letting us care about your desires!")
    print ("")
    print ("")
    print ("")
    print ("")
    print ("")

    # Send text to a window with mod graphics
    width = 1400
    height = 500
    textX = 125
    textY = 60
    text1 = ""
    text2 = ""
    text3 = ""
    text4 = ""
    text5 = ""
    text6 = "     Thank you for letting us care about your desires!"
    msTime = 5000   # 5 seconds
    #msTime = 500   # DEV DEBUG
    mgtw.createModGraphicWindow(width, height, textX, textY, text1, text2, text3, text4, text5, text6, msTime)

    print ("")
    print ("")
    print ("")
    print ("")
    print ("")
    print ("                            Next Consumer, Please!")
    print ("")

    # Send text to a window with mod graphics
    width = 1400
    height = 500
    textX = 60
    textY = 60
    text1 = ""
    text2 = ""
    text3 = "               Next Consumer, Please!"
    text4 = ""
    text5 = ""
    text6 = ""
    msTime = 5000   # 5 seconds
    #msTime = 500   # DEV DEBUG
    mgtw.createModGraphicWindow(width, height, textX, textY, text1, text2, text3, text4, text5, text6, msTime)

    for i in range(15):
        print ("")
        time.sleep(0.1)
    time.sleep(0.5)




# Since the above is an infinite loop, the code below will never execute.
#------------------------------------------------------------------------
# shut down synths to end program
final = True
shutDownSynthPlaying( final )

# close serial ports
print ("Close serial ports...")
serialPort0.close()
serialPort1.close()
serialPort2.close()
print (".....................done")

print ("")
print ("")
print ("")
print ("")
print ("")
print ("END of program")
print ("")
print ("")
print ("")
print ("")
print ("")
