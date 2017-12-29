import pyaudio
import time
import numpy as np
from threading import Thread

from sound_cap.utils.logger import Logger
from sound_cap.utils.audio_exceptions import MicrophoneDeviceNotFound, DataStreamVisualizationError

np.seterr(all='warn')
LOG = Logger()


def fourier_frequency(data, rate):
    # smoothed_data = data * np.hamming(len(data))
    fft = np.abs(np.fft.fft(data))
    freq = np.fft.fftfreq(len(fft), 1.0 / rate)
    return freq[:int(len(freq) / 2)], fft[:int(len(fft) / 2)]


class AudioStream:
    def __init__(self, refresh_rate=10):
        self.audio_rec = pyaudio.PyAudio()
        self.main_thread = None
        self.chunk_size = 4096
        self.refresh_rate = refresh_rate
        self.devices_info = {}
        self.points_range = None
        self.data = None
        self.fft_data = None
        self.fft_frequency = None
        self.mic_id = None
        self.stream = None

    def validation_test(self, device_id, mics_info):
        LOG.log_msg("Checking device ID: {0}".format(device_id))
        info = self.audio_rec.get_device_info_by_index(device_id)
        if info["maxInputChannels"] <= 0:
            LOG.error_msg("Max input channels <= 0")
            return
        try:
            stream = self.audio_rec.open(format=pyaudio.paInt16, channels=1,
                                         input_device_index=device_id,
                                         frames_per_buffer=self.chunk_size,
                                         rate=int(info["defaultSampleRate"]),
                                         input=True)

            stream.close()
            LOG.log_msg("Device ID: {0} is working properly".format(device_id))
            mics_info[device_id] = {'mic_name': info['name'],
                                    'mic_rate': int(info["defaultSampleRate"])}
        except ValueError:
            LOG.error_msg("Device ID: {0} isnt working".format(device_id))

    # TODO: handle exception in main_app
    def get_available_mics(self):
        LOG.log_msg("Searching for microphones devices")
        mics_info = {}
        for device in range(self.audio_rec.get_device_count()):
            self.validation_test(device, mics_info)
        if len(mics_info) == 0:
            raise MicrophoneDeviceNotFound("No mics found")
        LOG.log_msg("Microphones found: {0}".format(mics_info))
        return mics_info

    def choose_mic(self):
        LOG.log_msg("Choosing microphone")
        time.sleep(0.2)
        if len(self.devices_info) > 1:
            for mic_k, mic_val in self.devices_info.items():
                print("Mic ID: {0}, specs: {1}".format(mic_k, mic_val))
            return int(input("Chose device by ID: "))
        return 0

    def initialization(self):
        LOG.log_msg("Initializing")
        self.devices_info = self.get_available_mics()
        self.mic_id = self.choose_mic()

        if self.mic_id not in self.devices_info.keys():
            raise KeyError("Incorrect device ID")

        self.chunk_size = int(self.devices_info[self.mic_id]['mic_rate'] / self.refresh_rate)
        self.points_range = np.arange(self.chunk_size) / float(self.devices_info[self.mic_id]['mic_rate'])
        LOG.log_msg("Streaming from device: {0} with ID: {1} at rate: {2} Hz"
                    .format(self.devices_info[self.mic_id]['mic_name'],
                            self.mic_id,
                            self.devices_info[self.mic_id]['mic_rate']))

    # TODO: handle closing thread after exception and on app exit
    # TODO: handle closing stream
    def read_data_chunk(self):
        while True:
            try:
                self.data = np.fromstring(self.stream.read(self.chunk_size), dtype=np.int16)
                self.fft_frequency, self.fft_data = fourier_frequency(self.data,
                                                                      self.devices_info[self.mic_id]['mic_rate'])
            except Exception:
                LOG.error_msg("Error while processing data from microphone")
                raise DataStreamVisualizationError("Data processing error")

    def stream_start(self):
        self.initialization()
        self.stream = self.audio_rec.open(format=pyaudio.paInt16,
                                          channels=1,
                                          rate=self.devices_info[self.mic_id]['mic_rate'],
                                          input=True,
                                          frames_per_buffer=self.chunk_size)

        self.main_thread = Thread(target=self.read_data_chunk, args=())
        self.main_thread.daemon = True
        self.main_thread.start()