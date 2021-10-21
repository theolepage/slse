import numpy as np
import torch
import torchaudio
import soundfile as sf

def load_wav(path, frame_length):
    data, sr = sf.read(path)
    data = data.reshape((len(data), 1))

    if len(data) < frame_length:
        data = np.pad(data, (0, frame_length - len(data) + 1), 'wrap')

    offset = np.random.randint(0, len(data) - frame_length + 1)
    data = data[offset:offset+frame_length]

    return data

def extract_mfcc(audio):
    audio = torch.from_numpy(audio.astype(np.float32).T) # (T, 1) -> (1, T)
    mfcc = torchaudio.transforms.MelSpectrogram(
        n_fft=512,
        win_length=400,
        hop_length=160,
        window_fn=torch.hamming_window,
        n_mels=40)(audio)

    return mfcc.numpy().transpose(1, 2, 0) # (H, W, C) = (40, W, 1)