import os
import math
import numpy as np
from tensorflow.keras.utils import Sequence
from sklearn.model_selection import train_test_split

from sslforslr.dataset.AudioAugmentation import AudioAugmentation
from sslforslr.dataset.SupervisedTrainingSampler import SupervisedTrainingSampler
from sslforslr.dataset.utils import load_audio, extract_mfcc

def sample_frames(audio, frame_length):
    audio_length = audio.shape[1]
    assert audio_length >= 2 * frame_length, \
        "audio_length should >= 2 * frame_length"

    dist = audio_length - 2 * frame_length
    dist = np.random.randint(0, dist + 1)

    lower = frame_length + dist // 2
    upper = audio_length - (frame_length + dist // 2)
    pivot = np.random.randint(lower, upper + 1)

    frame1_from = pivot - dist // 2 - frame_length
    frame1_to = pivot - dist // 2
    frame1 = audio[:, frame1_from:frame1_to]

    frame2_from = pivot + dist // 2
    frame2_to = pivot + dist // 2 + frame_length
    frame2 = audio[:, frame2_from:frame2_to]

    return frame1, frame2

class AudioDatasetGenerator(Sequence):

    def __init__(
        self,
        batch_size,
        frame_length,
        frame_split,
        files,
        labels,
        indices,
        wav_augment=None,
        provide_clean_and_aug=False,
        extract_mfcc=False
    ):
        self.epoch = 0
        self.supervised_sampler = None
        
        self.batch_size = batch_size
        self.frame_length = frame_length
        self.frame_split = frame_split
        self.files = files
        self.labels = labels
        self.indices = indices
        self.wav_augment = wav_augment
        self.provide_clean_and_aug = provide_clean_and_aug
        self.extract_mfcc = extract_mfcc

    def __len__(self):
        return len(self.indices) // self.batch_size

    def preprocess_data(self, data, augment=True):
        assert data.ndim == 2 and data.shape[0] == 1 # (1, T)

        if augment and self.wav_augment: data = self.wav_augment(data)        
        
        if self.extract_mfcc:
            data = extract_mfcc(data) # (1, T) -> (1, T, C)
            data = data.squeeze(axis=0) # (1, T, C) -> (T, C)
        else:
            data = data.T # (1, T) -> (T, 1)
        
        return data

    def __getitem__(self, i):
        start = i * self.batch_size
        end   = i * self.batch_size + self.batch_size

        X1, X2, y = [], [], []
        for index in self.indices[start:end]:
            if self.frame_split:
                data = load_audio(
                    self.files[index],
                    frame_length=None,
                    min_length=2*self.frame_length
                ) # (1, T)
                frame1, frame2 = sample_frames(data, self.frame_length)
                if self.provide_clean_and_aug:
                    frame1_clean = self.preprocess_data(frame1, augment=False)
                    frame1_aug = self.preprocess_data(frame1)
                    X1.append(np.stack((frame1_clean, frame1_aug), axis=-1))
                    frame2_clean = self.preprocess_data(frame2, augment=False)
                    frame2_aug = self.preprocess_data(frame2)
                    X2.append(np.stack((frame2_clean, frame2_aug), axis=-1))
                else:
                    X1.append(self.preprocess_data(frame1))
                    X2.append(self.preprocess_data(frame2))
                y.append(self.labels[index])
            else:
                data1 = load_audio(self.files[index[0]], self.frame_length) # (1, T)
                data1 = self.preprocess_data(data1)
                X1.append(data1)
                data2 = load_audio(self.files[index[1]], self.frame_length) # (1, T)
                data2 = self.preprocess_data(data2)
                X2.append(data2)
                y.append(self.labels[index[0]])

        #if self.frame_split:
        return np.array(X1), np.array(X2), np.array(y)
        #return np.array(X1), np.array(y)

    def enable_supervision(self, nb_labels_per_spk=100):
        self.supervised_sampler = SupervisedTrainingSampler(
                self.labels,
                self.batch_size,
                nb_labels_per_spk
        )
        self.indices = self.supervised_sampler(self.epoch)

    def on_epoch_end(self):
        self.epoch += 1
        if self.supervised_sampler:
            self.indices = self.supervised_sampler(self.epoch)
        else:
            np.random.shuffle(self.indices)

class AudioDatasetLoader:

    def __init__(self, config):
        self.config = config

        # Create augmentation module
        self.wav_augment = None
        if self.config.wav_augment.enable:
            self.wav_augment = AudioAugmentation(
                self.config.wav_augment,
                self.config.base_path
            )
        
        self.load_data()

    def load_data(self):
        # Create lists of audio paths and labels
        self.files = []
        self.labels = []
        self.nb_classes = 0
        labels_id = {}
        for line in open(self.config.train):
            label, file = line.rstrip().split()

            path = os.path.join(self.config.base_path, file)
            self.files.append(path)

            if label not in labels_id:
                labels_id[label] = self.nb_classes
                self.nb_classes += 1
            self.labels.append(labels_id[label])

    def get_input_shape(self):
        if self.config.extract_mfcc:
            return (self.config.frame_length // 160, 40)
        return (self.config.frame_length, 1)

    def load(self, batch_size):
        count = self.config.max_samples if self.config.max_samples else len(self.files)
        
        train_indices = np.arange(count)
        np.random.shuffle(train_indices)
        if self.config.val_ratio:
            train_indices, val_indices = train_test_split(
                train_indices,
                test_size=self.config.val_ratio,
                random_state=0
            )

        train_gen = AudioDatasetGenerator(
            batch_size,
            self.config.frame_length,
            self.config.frame_split,
            self.files,
            self.labels,
            train_indices,
            self.wav_augment,
            self.config.provide_clean_and_aug,
            self.config.extract_mfcc
        )

        val_gen = None
        if self.config.val_ratio:
            val_gen = AudioDatasetGenerator(
                batch_size,
                self.config.frame_length,
                self.config.frame_split,
                self.files,
                self.labels,
                val_indices,
                self.wav_augment,
                self.config.provide_clean_and_aug,
                self.config.extract_mfcc
            )

        return train_gen, val_gen
