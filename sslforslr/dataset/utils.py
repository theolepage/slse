import numpy as np
import torch
import torch.nn.functional as F
import torchaudio
import soundfile as sf

def load_wav(path, frame_length, num_frames=1):
    audio, sr = sf.read(path)

    # Load entire audio data if frame_length is not specified
    if frame_length is None: frame_length = len(audio)

    # Pad signal if it is shorter than frame_length
    if len(audio) < frame_length:
        audio = np.pad(audio, (0, frame_length - len(audio) + 1), 'wrap')

    # Determine frames start indices
    idx = []
    if num_frames == 1:
        idx = [np.random.randint(0, len(audio) - frame_length + 1)]
    else:
        idx = np.linspace(0, len(audio) - frame_length, num=num_frames)

    # Extract frames
    data = [audio[int(i):int(i)+frame_length] for i in idx]
    data = np.stack(data, axis=0).astype(np.float32)

    return data # (num_frames, T)

def pre_emphasis(audio, coef=0.97):
    w = torch.FloatTensor([-coef, 1.0]).unsqueeze(0).unsqueeze(0)
    audio = audio.unsqueeze(1)
    audio = F.pad(audio, (1, 0), 'reflect')
    return F.conv1d(audio, w).squeeze(1)

def extract_mfcc(audio):
    audio = torch.from_numpy(audio) # (N, T)

    audio = pre_emphasis(audio)
    
    mfcc = torchaudio.transforms.MelSpectrogram(
        n_fft=512,
        win_length=400,
        hop_length=160,
        window_fn=torch.hamming_window,
        n_mels=40)(audio) # mfcc: (N, C, T)
    
    mfcc = mfcc.numpy().transpose(0, 2, 1) # (N, T, C)
    
    # torchaudio MelSpectrogram method might return a larger sequence
    limit = audio.shape[1] // 160
    mfcc = mfcc[:, :limit, :]
    
    return mfcc