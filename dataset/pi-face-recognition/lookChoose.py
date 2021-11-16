#------
# 
# lookChoose()
#    uses a USB webcam with OpenCV
#    to "look" at the person in the webcam,
#    and "choose" which face in the program's database is a closest match.
#
#    The output is a song number to play on the ArduTouch synths (and eSpeak).
#       If the face has no close match, a song number is chosen randomly.
#
# This Python 3 program was created to run on a Raspberry Pi 4 with 8GB RAM.
# It has a 32GB micro SD card with 100MB/s speed (SanDisk Extreme microSDHC UHS-I A1).
#
# This program requires an external USB webcam.
#    It was tested using a Microsoft LifeCam HD-3000
#
# This is program is hacked from the tutorial:
#     Raspberry Pi Face Recognition
# June 25, 2018, by Adrian Rosebrock 
# https://www.pyimagesearch.com/2018/06/25/raspberry-pi-face-recognition/
#
#
# Version log:
# -----------
# 29-Aug-2021 Mitch:  Initial version.
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
from imutils.video import VideoStream
from imutils.video import FPS
import face_recognition
import argparse
import imutils
import pickle
import os
import time
import cv2



#--------------------------------------------------
#--------------------------------------------------
#
# Choose a song number randomly
#    given the number of songs.
#
# returns an integer value between 0 and numSongs-1
#
#--------------------------------------------------
#--------------------------------------------------

def randChoose(numSongs):

    randByte= os.urandom(1)                     # get a random byte between b'\x00' and b'\xff'
    randInt = int.from_bytes(randByte, "big")   # convert the byte into an integer between 0 and 255
    div = 256 // (numSongs-1)
    randSongNum = randInt / div                 # randSongNum is a random number between 0 and numSongs-1

    return randSongNum



# In order to detect and localize faces in frames we rely on OpenCV’s pre-trained Haar cascade file.
cascade = "haarcascade_frontalface_default.xml"

# Our face encodings (128-d vectors, one for each face) are stored in this pickle file.
encodings = "encodings.pickle"

# NOTE: A higher tolerance number makes matches more likely between webcam frames and pictures in the dataset.
tolerance = 0.73

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
    ["adrian", "ali_macgraw", "barry_manilow", "bert_kaempfert", "billy_joel", "catherine_deneuve", "claude_ciari", "frank_sinatra", "henry_mancini", "herb_alpert", "ian_malcolm", "michel_legrand", "mitch", "rober_kool_bell", "sandra_dee", "walter_wanderley", "Unknown"],
    ["8",      "11",           "0",            "9",              "1",          "7",                 "3",            "6",             "11",            "4",           "5",           "7",              "R",     "2",               "9",          "10"             , "R" ]
#    ["0",       "1",            "2",            "0",              "1",          "2",                 "0",            "1",             "2",             "0",           "1",           "2",              "R",     "0",               "1",          "2"              , "R" ]
]
numElementsInSongNumTab = len(songNumTab[SONG_NAME])


# load the known faces and embeddings along with OpenCV's Haar cascade for face detection
print("[INFO] loading encodings + face detector...")
data = pickle.loads(open(encodings, "rb").read())
detector = cv2.CascadeClassifier(cascade)

# initialize the video stream and allow the camera sensor to warm up
print("[INFO] starting video stream...")
vs = VideoStream(src=0).start()
# vs = VideoStream(usePiCamera=True).start()
time.sleep(2.0)

# count frames    # DEBUG
#frameCount = 0   # DEBUG

# count frames with a face match so we can be sure to display the face recognition frame for at least a few seconds
framesWithMatch = 0

# number of frames to wait till determining a face match 
frameWait = 20

# before we start matching faces there is no name associated with a face yet
name = "uncalculated"
firstFaceName = "uncalculated"

# start the FPS counter
fps = FPS().start()

# loop over frames from the video file stream
while True:
    # grab the frame from the threaded video stream and resize it
    # to 500px (to speedup processing)
    frame = vs.read()
    frame = imutils.resize(frame, width=500)

    # convert the input frame from (1) BGR to grayscale (for face
    # detection) and (2) from BGR to RGB (for face recognition)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # detect faces in the grayscale frame
    rects = detector.detectMultiScale(gray, scaleFactor=1.1, 
        minNeighbors=5, minSize=(30, 30),
        flags=cv2.CASCADE_SCALE_IMAGE)

    # OpenCV returns bounding box coordinates in (x, y, w, h) order
    # but we need them in (top, right, bottom, left) order, so we
    # need to do a bit of reordering
    boxes = [(y, x + w, y + h, x) for (x, y, w, h) in rects]

    # compute the facial embeddings for each face bounding box
    encodings = face_recognition.face_encodings(rgb, boxes)
    names = []

    # loop over the facial embeddings
    for encoding in encodings:
        # attempt to match each face in the input image to our known encodings
                # NOTE: The built-in default tolerance in face_recognition is 0.6 .  
                #       Calling face_recognition.compare_faces() with a differnt value overrides the defaults.
                #       A higher number makes matches more likely between webcam frames and pictures in the dataset.
        matches = face_recognition.compare_faces(data["encodings"], encoding, tolerance)
        name = "Unknown"

        # check to see if we have found a match
        if True in matches:
            # find the indexes of all matched faces then initialize a
            # dictionary to count the total number of times each face
            # was matched
            matchedIdxs = [i for (i, b) in enumerate(matches) if b]
            counts = {}

            # loop over the matched indexes and maintain a count for
            # each recognized face face
            for i in matchedIdxs:
                name = data["names"][i]
                counts[name] = counts.get(name, 0) + 1

            # determine the recognized face with the largest number
            # of votes (note: in the event of an unlikely tie Python
            # will select first entry in the dictionary)
            name = max(counts, key=counts.get)

            # there is a face match in this frame, so increment framesWithMatch
            framesWithMatch += 1

            # add text and countdown
            if ( framesWithMatch < (frameWait-1) ):
                cv2.putText(frame, "Calculating", (10, 30), cv2.FONT_HERSHEY_COMPLEX, 1.25, (0, 255, 255), 3)
                cv2.putText(frame, "      Your Desires...", (10,70), cv2.FONT_HERSHEY_COMPLEX, 1.25, (0, 255, 255), 3)
                cv2.putText(frame, str(20-framesWithMatch), (460,360), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 255), 2)

        # update the list of names
        names.append(name)

    # loop over the recognized faces
    faceCount = 0   # count the faces, and save the name of the name of the first face
    for ((top, right, bottom, left), name) in zip(boxes, names):
        # draw the predicted face name on the image
        cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
        y = top - 15 if top - 15 > 15 else top + 15
        #cv2.putText(frame, name, (left, y), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 0), 2)
        cv2.putText(frame, "consumer", (left, y), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 0), 2)
        if (faceCount == 0):
            firstFaceName = name
        faceCount += 1

    #print (frameCount, framesWithMatch, faceCount, "----", name)        # DEBUG
    #print (frameCount, framesWithMatch, faceCount, "1st:", firstFaceName)   # DEBUG

    if ( (framesWithMatch > frameWait) and (name != "uncalculated") ):
        cv2.putText(frame, "  Desires", (60, 80), cv2.FONT_HERSHEY_COMPLEX, 1.25, (0, 255, 255), 3)
        cv2.putText(frame, "Calculated!", (60, 118), cv2.FONT_HERSHEY_COMPLEX, 1.25, (0, 255, 255), 3)

    # display the image to our screen
    cv2.imshow("Calculating your desires...", frame)
    key = cv2.waitKey(1) & 0xFF

    # if the `q` key was pressed, break from the loop
    if key == ord("q"):
        break

    if (framesWithMatch > frameWait):
        break

    # update the FPS counter (and increment the frame count if DEBUGging)
    fps.update()
    #frameCount += 1   # DEBUG

# keep displaying the saved frame for a little while
time.sleep(6)

# stop the timer and display FPS information
fps.stop()
print("[INFO] elasped time: {:.2f}".format(fps.elapsed()))
print("[INFO] approx. FPS: {:.2f}".format(fps.fps()))

# do a bit of cleanup
cv2.destroyAllWindows()
vs.stop()

# Choose the song to play
#print(firstFaceName)   # DEBUG
# Now that we have a firstFaceName matched with a face, we search for that name in the songNumTab
#     by indexing through the names in songNumTab till we find it: 
#        songNumTab[SONG_NAME][index]  which gives the name of the indexed entry in songNumTab
#    then, using the same index, we look in
#        songNumTab[SONG_NUM][index]   which gives the song number to play.
#    If songNum = "R", then we choose a random song number.

for songIndex in range(numElementsInSongNumTab):
    # Search for the name in the songNumTab.
    readName = songNumTab[SONG_NAME][songIndex]
    if ( readName == firstFaceName ):
        # We found the name, so grab the songNum from songNumTab
        songNum = songNumTab[SONG_NUM][songIndex]
        # If the songNum is "R", then choose a random songNum
        if ( songNum == "R" ):
            # Find number of songs by searching for the max song number in the songNumTab.
            maxSongNum = "0"
            for songIndex in range(numElementsInSongNumTab):
                readNum = songNumTab[SONG_NUM][songIndex]
                if ( readNum != "R" ):
                    if ( int(readNum) > int(maxSongNum) ):
                        maxSongNum = readNum
            #print ("random:  maxSongNum=", maxSongNum)   # DEBUG                    
            songNum = randChoose( int(maxSongNum) )   # this function returns a random song number to play

songNumber = int( songNum )
print ("")
print ("")
print ( "     The song number to play is: ", songNumber )
print ("")
print ("")
