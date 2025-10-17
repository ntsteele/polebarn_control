import time, yaml, numpy as np, sounddevice as sd
CFG = yaml.safe_load(open("/home/pi/polebarn_control/config.yaml"))
SR=48000; BS=4096; HZ=np.fft.rfftfreq(BS,1/SR)
BANDS=[31.5,40,50,63,80,100,125,160,200,250,315,400,500,630,800,1000,1250,1600,2000,2500,3150,4000,5000,6300,8000,10000,12500]
IDX=[np.argmin(np.abs(HZ-f)) for f in BANDS]
def analyze(dev="default", seconds=12):
    frames=int(seconds*SR/BS); acc=np.zeros(len(HZ))
    with sd.InputStream(device=dev, channels=1, samplerate=SR, blocksize=BS, dtype='float32') as s:
        for _ in range(frames):
            x,_=s.read(BS); X=np.abs(np.fft.rfft(x[:,0]*np.hanning(BS)))+1e-12
            acc+=20*np.log10(X)
    acc/=max(frames,1); vals=[float(acc[i]) for i in IDX]; med=np.median(vals)
    peaks=[(f, v-med) for f,v in zip(BANDS,vals) if v-med>6.0]
    peaks=sorted(peaks, key=lambda t:-t[1])[:5]
    print("Suggested notches (freq ~ gain_dB @ Q≈4):")
    for f,delta in peaks:
        g=-min(delta-3, 9)  # leave 3 dB margin, cap -9 dB
        print(f"  {int(round(f)):>5} Hz   {g:>5.1f} dB")
    if not peaks: print("No strong peaks found.")
if __name__=="__main__":
    analyze(CFG.get("autovolume",{}).get("device","default"), seconds=12)
