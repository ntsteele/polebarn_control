#!/usr/bin/env python3
import subprocess, wave, numpy as np, tempfile, os

# ALSA device for the XR18 USB audio interface (adjust if `aplay -l` shows differently)
XR18_DEVICE = "plughw:CARD=X18XR18,DEV=0"

def _as_int16(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32).flatten()
    x = np.clip(x, -1.0, 1.0)
    return (x * 32767.0).astype(np.int16)

def _write_wav_multichannel(path: str, frames_chn: np.ndarray, samplerate=48000):
    """
    frames_chn: shape (num_frames, num_channels), float32 in [-1,1]
    Writes interleaved 16-bit PCM WAV.
    """
    frames_chn = np.asarray(frames_chn, dtype=np.float32)
    assert frames_chn.ndim == 2, "frames_chn must be (frames, channels)"
    interleaved = _as_int16(frames_chn.reshape(-1))
    with wave.open(path, "wb") as wf:
        wf.setnchannels(frames_chn.shape[1])
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(samplerate)
        wf.writeframes(interleaved.tobytes())

def build_wav_usb_17_18(left: np.ndarray, right: np.ndarray, samplerate=48000) -> str:
    """
    Create a temp 18-channel WAV with content only in channels 17/18.
    Returns temp file path (caller is responsible for cleanup).
    """
    left  = np.asarray(left, dtype=np.float32).flatten()
    right = np.asarray(right, dtype=np.float32).flatten()
    assert left.shape == right.shape, "Left/Right must have same length"
    n = left.shape[0]
    ch = 18
    frames = np.zeros((n, ch), dtype=np.float32)
    frames[:, 16] = left   # USB ch 17
    frames[:, 17] = right  # USB ch 18

    f = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp = f.name; f.close()
    _write_wav_multichannel(tmp, frames, samplerate)
    return tmp

def play_wav_async(path: str):
    """
    Start aplay asynchronously (non-blocking). Returns subprocess.Popen handle.
    Caller should wait on .wait() and then delete the temp file.
    """
    return subprocess.Popen(["aplay", "-D", XR18_DEVICE, path])

def cleanup_tmp(path: str):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass

# Synchronous convenience (kept for reference)
def play_usb_pair_17_18(left: np.ndarray, right: np.ndarray, samplerate=48000):
    tmp = None
    try:
        tmp = build_wav_usb_17_18(left, right, samplerate)
        proc = play_wav_async(tmp)
        proc.wait()
    finally:
        cleanup_tmp(tmp)
