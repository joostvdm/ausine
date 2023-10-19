# ausine.py

# Building an Audio Unit in Python with ctypes.

# Created in Pythonista on iPad 2 running iOS 9.

# Based on Simple Sine Wave Player from the book Learning Core Audio
# by Chris Adamson and Kevin Avila.

# Python approach adapted from audiounittest.py by jsbain.
# gist.github.com/jsbain/0db690ed392ce35ec05fdb45bb2b3306

# ~ Joost van der Molen, October 2023


import numpy as np
from sys import exit, stderr
from time import sleep

from ctypes import (
	byref, c_double, c_float, c_int32, c_uint32, c_void_p,
	cast, cdll, memmove, pointer, py_object, sizeof,
	CFUNCTYPE, POINTER, Structure)

c = cdll.LoadLibrary(None)


class raw_c_void_p(c_void_p):
	pass

sampleRate = 44100.0
sineFrequency = 880.0

noErr = 0

AudioUnitRenderActionFlags = c_uint32
Float64 = c_double
OSStatus = c_int32
OSType = c_uint32


def StringToOSType(s):
	x = int.from_bytes(bytes(s, 'ascii'), byteorder='big')
	return(OSType(x))


# --- Core Audio constants

kAudioFormatLinearPCM = StringToOSType('lpcm')

kAudioUnitType_Output = StringToOSType('auou')
kAudioUnitSubType_RemoteIO = StringToOSType('rioc')
kAudioUnitManufacturer_Apple = StringToOSType('appl')

kAudioUnitProperty_StreamFormat = 8
kAudioUnitProperty_SetRenderCallback = 23

kAudioUnitScope_Global = 0
kAudioUnitScope_Input = 1
kAudioUnitScope_Output = 2


# --- Core Audio structs

class AudioBuffer(Structure):
	_fields_ = [
		('mNumberChannels', c_uint32),
		('mDataByteSize', c_uint32),
		('mData', c_void_p)]


class AudioBufferList(Structure):
	_fields_ = [
		('mNumberBuffers', c_uint32),
		('mBuffers', AudioBuffer*1)]
# "struct hack" for variable-length array


class AudioComponentDescription(Structure):
	_fields_ = [
		('componentType', OSType),
		('componentSubType', OSType),
		('componentManufacturer', OSType),
		('componentFlags', c_uint32),
		('componentFlagsMask', c_uint32)]


class AudioStreamBasicDescription(Structure):
	_fields_ = [
		('mSampleRate', Float64),
		('mFormatID', c_uint32),
		('mFormatFlags', c_uint32),
		('mBytesPerPacket', c_uint32),
		('mFramesPerPacket', c_uint32),
		('mBytesPerFrame', c_uint32),
		('mChannelsPerFrame', c_uint32),
		('mBitsPerChannel', c_uint32),
		('mReserved', c_uint32)]


# --- Core Audio functions

AudioComponentFindNext = c.AudioComponentFindNext
AudioComponentFindNext.argtypes = [
	c_void_p, POINTER(AudioComponentDescription)]
AudioComponentFindNext.restype = c_void_p

AudioComponentInstanceNew = c.AudioComponentInstanceNew
c.AudioComponentInstanceNew.argtypes = [c_void_p, c_void_p]
c.AudioComponentInstanceNew.restype = OSStatus

AudioUnitSetProperty = c.AudioUnitSetProperty
AudioUnitSetProperty.argtypes = [
	c_void_p, c_uint32, c_uint32, c_uint32, c_void_p, c_uint32]
AudioUnitSetProperty.restype = OSStatus

AudioUnitInitialize = c.AudioUnitInitialize
AudioUnitInitialize.argtypes = [c_void_p]
AudioUnitInitialize.restype = OSStatus

AudioOutputUnitStart = c.AudioOutputUnitStart
AudioOutputUnitStart.argtypes = [c_void_p]
AudioOutputUnitStart.restype = OSStatus

c.AudioOutputUnitStop.argtypes = [c_void_p]

c.AudioUnitUninitialize.argtypes = [c_void_p]

c.AudioComponentInstanceDispose.argtypes = [c_void_p]


# --- Callback function prototype
arg = [
	c_void_p,
	POINTER(AudioUnitRenderActionFlags),
	c_void_p,  # POINTER(AudioTimeStamp),
	c_uint32,
	c_uint32,
	POINTER(AudioBufferList)]
res = OSStatus
AURenderCallback = CFUNCTYPE(res, *(arg))


# --- Callback struct
class AURenderCallbackStruct(Structure):
	_fields_ = [
		('inputProc', AURenderCallback),
		('inputProcRefCon', c_void_p)]


# --- User data struct
class MySineWavePlayer(Structure):
	_fields_ = [
		('outputUnit', raw_c_void_p),
		('startingFrameCount', c_double)]


# --- Callback function
def SineWaveRenderProc(
	inRefCon: c_void_p,
	ioActionFlags: POINTER(AudioUnitRenderActionFlags),
	inTimeStamp: c_void_p,  # POINTER(AudioTimeStamp),
	inBusNumber: c_uint32,
	inNumberFrames: c_uint32,
	ioData: POINTER(AudioBufferList)
	) -> OSStatus:

		# Generate tone to demonstrate functionality
		player = cast(inRefCon, POINTER(py_object)).contents.value
		cycleLength = sampleRate / sineFrequency
		j = player.startingFrameCount
		jarr = np.zeros(inNumberFrames, dtype=np.float32)
		for frame in range(inNumberFrames):
			jarr[frame] = j
			j = j + 1.0
			if (j > cycleLength):
				j = j - cycleLength
		amplitude = 0.25
		sine = amplitude * np.sin(2.0 * np.pi * (jarr / cycleLength))
		memmove(
			ioData[0].mBuffers[0].mData,
			sine.ctypes.data,
			inNumberFrames * sizeof(c_float))
		player.startingFrameCount = j
		return noErr


# --- Error check function
def CheckError(error: OSStatus, operation):
	if (error == noErr):
		return
	print('Error: %s (%d)' % (operation, error), file=stderr)
	exit(1)


# --- Setup function
def CreateAndConnectOutputUnit(player: MySineWavePlayer):

	# Describe audio unit
	outputcd = AudioComponentDescription(0)
	outputcd.componentType = kAudioUnitType_Output
	outputcd.componentSubType = kAudioUnitSubType_RemoteIO
	outputcd.componentManufacturer = kAudioUnitManufacturer_Apple

	# Get audio unit
	comp = c.AudioComponentFindNext(None, byref(outputcd))
	if comp is None:
		print("Can't get output unit")
		exit(-1)

	# Instantiate audio unit
	err = c.AudioComponentInstanceNew(comp, byref(player.outputUnit))
	CheckError(err, "Couldn't open component for outputUnit")

	# Describe audio format
	bytesPerSample = 4  # 32 bit
	streamFormat = AudioStreamBasicDescription(0)
	streamFormat.mSampleRate = sampleRate
	streamFormat.mFormatID = kAudioFormatLinearPCM
	streamFormat.mFormatFlags = 41
	streamFormat.mBytesPerPacket = bytesPerSample
	streamFormat.mFramesPerPacket = 1
	streamFormat.mBytesPerFrame = 1 * bytesPerSample
	streamFormat.mChannelsPerFrame = 1  # Mono
	streamFormat.mBitsPerChannel = 8 * bytesPerSample

	# Set audio format
	err = c.AudioUnitSetProperty(
		player.outputUnit,
		kAudioUnitProperty_StreamFormat,
		kAudioUnitScope_Input,
		0,
		byref(streamFormat),
		sizeof(streamFormat))
	CheckError(err, "AudioUnitSetProperty StreamFormat failed")

	# Prepare callback function
	input = AURenderCallbackStruct()
	input.inputProc = AURenderCallback(SineWaveRenderProc)
	player_ptr = cast(pointer(py_object(player)), c_void_p)
	input.inputProcRefCon = player_ptr

	# Connect callback function to audio unit
	err = c.AudioUnitSetProperty(
		player.outputUnit,
		kAudioUnitProperty_SetRenderCallback,
		kAudioUnitScope_Input,
		0,
		byref(input),
		sizeof(input))
	CheckError(err, "AudioUnitSetProperty SetRenderCallback failed")

	# Initialize audio unit
	err = c.AudioUnitInitialize(player.outputUnit)
	CheckError(err, "Couldn't initialize output unit")

	# Return callback struct so that Python does not discard it
	return input


# --- Main
if (__name__ == '__main__'):

	player = MySineWavePlayer(0)

	# Set up audio unit and callback
	_ = CreateAndConnectOutputUnit(player)

	# Play sound for 5 seconds
	try:
		err = c.AudioOutputUnitStart(player.outputUnit)
		CheckError(err, "Couldn't start output unit")
		sleep(5)

	# Clean up
	finally:
		c.AudioOutputUnitStop(player.outputUnit)
		c.AudioUnitUninitialize(player.outputUnit)
		c.AudioComponentInstanceDispose(player.outputUnit)

