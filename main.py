# File: main.py
from collections import namedtuple
import sys
from os import path
from PyQt5.uic import loadUiType
import functions as f
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
import wave
import classes as c
import numpy as np
from PyQt5 import QtCore
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtCore import QUrl
import sounddevice as sd
from scipy.signal import *


FORM_CLASS, _ = loadUiType(path.join(path.dirname(__file__), "design.ui"))


class MainApp(QMainWindow, FORM_CLASS):
    def __init__(self, parent=None):
        super(MainApp, self).__init__(parent)
        QMainWindow.__init__(self)

        self.setupUi(self)
        self.setWindowTitle("Signal Equalizer")
        
        # Objects
        self.hamming = c.WindowType(['N'], 0)
        self.hanning = c.WindowType(['N'], 0)
        self.gaussian = c.WindowType(['Std'], 1)
        self.rectangle = c.WindowType(['constant'], 0)

        r = namedtuple('Range', ['min', 'max'])
        self.default = c.Mode([f'{i*10} to {(i+1)*10} Hz' for i in range(10)],
                              [r(i * 50, (i + 1) * 50) for i in range(10)], [i for i in range(10)], 10)
        self.ecg = c.Mode(['Normal ECG', 'Atrial fibrillation', 'Ventricular Tachycardia', 'Ventricular fibrillation'], [], [i for i in range(4)], 4)
        self.animals = c.Mode(['Wolf', 'Cow', 'Monkey', 'Eagle'], [r(200, 800), r(800, 2000), r(1500, 3800), r(2000, 70000)], [i for i in range(4)] , 4)
        self.musical = c.Mode(['Drums', 'Guitar & Saxophone', 'Piano', 'Triangle'], [r(2000, 6500), r(200,1200), r(1000,5000),r(6500,14000)], [i for i in range(4)], 4)


        # Variables
        self.amplitudes = []
        self.frequency_comp = []
        self.phases = []
        self.output_amplitudes = []
        self.mode = None
        self.index = 0
        self.state = True
        self.audio_data = []
        self.edited_time_domain_signal = []
        self.sample_rate = 44100
        self.playing = False
        self.sliders_list = []
        self.indicators_list = []
        self.window_sliders = []
        self.window_indicators = []
        self.mapping_mode = {
            0: self.default,
            1: self.ecg,
            2: self.animals,
            3: self.musical,
        }
        self.window_map = {
            0: self.hamming,
            1: self.hanning,
            2: self.gaussian,
            3: self.rectangle,
        }
        
        # Timer
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(lambda: self.update_waveform(self.audio_data, self.InputGraph))
        self.timer.timeout.connect(lambda: self.update_waveform(self.edited_time_domain_signal, self.OutputGraph))

        # Audio Players
        self.media_playerIN = QMediaPlayer()
        self.media_playerOUT = QMediaPlayer()

        # Setting the Ui
        self.SliderFrame.setMaximumHeight(200)
        self.change_mode(self.mode_comboBox.currentIndex())
        self.InputGraph.setBackground('w')
        self.OutputGraph.setBackground('w')
        self.freqGraph.setBackground('w')
        self.SliderFrame.setEnabled(False)
        self.window_comboBox.setEnabled(False)


        # Signals
        self.importButton.clicked.connect(lambda: self.upload(self.musicfileName))
        self.mode_comboBox.currentIndexChanged.connect(lambda: self.change_mode(self.mode_comboBox.currentIndex()))
        self.window_comboBox.currentIndexChanged.connect(
            lambda: self.smoothing_window_type(self.window_comboBox.currentIndex()))
        self.playallButton.clicked.connect(lambda: self.play_n_pause(self.playallButton, False))
        self.playButton1.clicked.connect(lambda: self.play_n_pause(self.playButton1, True))
        self.playButton2.clicked.connect(lambda: self.play_output_signal(self.playButton2, self.edited_time_domain_signal, self.sample_rate))
        self.speedSlider.valueChanged.connect(self.update_speed)
        self.resetButton.clicked.connect(self.reset)
        self.showCheckBox.stateChanged.connect(lambda: f.plot_specto(self.audio_data, self.sample_rate, self.spectoframe1, self.showCheckBox))
        self.showCheckBox.stateChanged.connect(lambda: f.plot_specto(self.edited_time_domain_signal, self.sample_rate, self.spectoframe2, self.showCheckBox))
        self.window_comboBox.currentIndexChanged.connect(lambda: self.get_smoothing_window(self.window_comboBox.currentIndex(), self.freqGraph, self.output_amplitudes, self.frequency_comp, 1))
        self.zoomInButton.clicked.connect(lambda: f.zoom(self.InputGraph, self.OutputGraph, 0.8 ))
        self.zoomOutButton.clicked.connect(lambda: f.zoom(self.InputGraph, self.OutputGraph, 1.2))
        
        
    # FUNCTIONS
    
    def enable_widgets(self):
        self.playallButton.setEnabled(True)
        self.resetButton.setEnabled(True)
        self.zoomOutButton.setEnabled(True)
        self.zoomInButton.setEnabled(True)
        self.speedSlider.setEnabled(True)
        self.showCheckBox.setEnabled(True)
        self.SliderFrame.setEnabled(True)
        self.window_comboBox.setEnabled(True)

    def upload(self, label):
        options = QFileDialog.Options()
        options |= QFileDialog.ReadOnly

        filters = "Audio and CSV Files (*.wav *.csv)"
        file_path, _ = QFileDialog.getOpenFileName(self, "QFileDialog.getOpenFileNames()", "", filters, options=options)
        
        if file_path:
            # Store file name
            file_name = file_path.split('/')[-1]
            label.setText(file_name)

            self.reset()
            self.enable_widgets()
            self.reset_sliders()
            
            if file_path.lower().endswith('.wav'):
                if self.media_playerIN.state() == QMediaPlayer.StoppedState:
                    self.media_playerIN.setMedia(QMediaContent(QUrl.fromLocalFile(file_path)))
                    self.AudioPlayerFrame.setEnabled(True)

                # Open the .wav file for reading
                with wave.open(file_path, 'rb') as audio_file:
                    # Get the audio file's parameters
                    num_frames = audio_file.getnframes()

                    # Read audio data as bytes
                    raw_audio_data = audio_file.readframes(num_frames)

                    # Convert raw bytes to numerical values (assuming 16-bit PCM)
                    self.audio_data = np.frombuffer(raw_audio_data, dtype=np.int16)
                    self.edited_time_domain_signal = self.audio_data.copy()

                    sample_width = audio_file.getsampwidth()
                    self.sample_rate = audio_file.getframerate()
                    self.time = np.arange(0, len(self.audio_data)) / self.sample_rate

            elif file_path.lower().endswith('.csv'):
                data = np.loadtxt(file_path, delimiter=',', skiprows=1, usecols=(1,))
                self.audio_data = data[0:1000]
                self.edited_time_domain_signal = self.audio_data.copy()
                self.x = np.loadtxt(file_path, delimiter=',', skiprows=1, usecols=(0,))
                self.sample_rate = 1/(self.x[1]-self.x[0])
                self.time = self.x[0:1000]
            
            
            self.update_signal()
            f.freq_domain_plotting(self.frequency_comp, self.output_amplitudes, self.freqGraph)
            
            
            if self.showCheckBox.isChecked():
                f.plot_specto(self.audio_data, self.sample_rate, self.spectoframe1, self.showCheckBox)
                f.plot_specto(self.edited_time_domain_signal, self.sample_rate, self.spectoframe2, self.showCheckBox)

    def clear_and_plotwaveform(self):
        self.InputGraph.clear()
        self.OutputGraph.clear()
        f.plot_waveform(self.audio_data, self.sample_rate, self.InputGraph)
        f.plot_waveform(self.edited_time_domain_signal, self.sample_rate, self.OutputGraph)
        # To Clear while Plotting Dynamically
        self.state = True

    def reset(self):
        if self.timer.isActive():
            self.play_n_pause(self.playallButton, False)
            self.clear_and_plotwaveform()
        else:
            self.clear_and_plotwaveform()

    def update_waveform(self, data, plot_widget):
        if self.state:
            self.InputGraph.clear()
            self.OutputGraph.clear()

        self.state = False
        x_min = self.index
        x_max = min(len(self.time), self.index + 10)

        plot_item = plot_widget.plot(pen='b')
        plot_item.setData(self.time[x_min:x_max], data[x_min:x_max])
        plot_widget.setXRange(self.time[x_min], self.time[x_max])

        if self.index >= len(self.time):
            self.index = 0
        self.index += 1

    def play_sound(self, button, ):
        if self.timer.isActive():
            self.timer.stop()
            button.setIcon(QIcon("icons/pause.png"))
        else:
            self.timer.start(lambda: f.speed(self.speedSlider.value(),self.speedLabel))
            button.setIcon(QIcon("icons/play.png"))
    
    def update_speed(self):
        time_interval = f.speed(self.speedSlider.value(),self.speedLabel)
        if self.timer.isActive():
            self.timer.stop()
            self.timer.start(time_interval)
        else:
            return
         
    def change_mode(self, index):
        self.mode = self.mapping_mode[index]
        self.sliders_list, indicators_list = f.create_sliders(self.mode.num_sliders, self.mode.labels, self.SliderFrame, 2)
        self.sliders_refresh(self.sliders_list, indicators_list)

    def update_signal(self):
        r = namedtuple('Range', ['min', 'max'])
        signal = self.audio_data
        Ts = 1 / self.sample_rate
        
        if len(signal):
            self.amplitudes, self.frequency_comp, self.phases = f.compute_fourier_transform(signal, Ts)
            # Convert Freq range to Indecies range
            for i in range(4):
                mode = self.mapping_mode[i]
                for i in range(len(mode.frq_range)):
                    min, max = mode.frq_range[i][0], mode.frq_range[i][1]
                    indecies = np.where((self.frequency_comp > min) & (self.frequency_comp < max))[0]
                    mode.ind_range[i] = (r(indecies[0], indecies[-1])) 
                print(mode.ind_range)
            self.output_amplitudes = self.amplitudes.copy()

    def sliders_refresh(self, sliders, indicators):
        if sliders:
            for slider in sliders:
                slider.valueChanged.connect(lambda: self.update_indicators(sliders, indicators))
                slider.valueChanged.connect(lambda value, Slider = slider: self.modifying_amplitudes(self.sliders_list.index(Slider), value,
                                                                              self.amplitudes, self.output_amplitudes,
                                                                              self.window_comboBox.currentIndex(), 1))

    def update_indicators(self, sliders, indicators):
        if sliders:
            for i, slider in enumerate(sliders):
                indicators[i].setText(f"{slider.value()}")

    def smoothing_window_type(self, index):
        window = self.window_map[index]

        self.window_sliders, self.window_indicators = f.create_sliders(window.num_sliders, window.labels, self.WindowFrame, 1)

        # Refresh Sliders
        self.sliders_refresh(self.window_sliders, self.window_indicators)
        for slider in self.window_sliders: slider.valueChanged.connect(lambda: self.customize_smoothing_window_parameters(slider.value(), self.window_comboBox.currentIndex(), self.freqGraph, self.output_amplitudes, self.frequency_comp))

    def modify_output_amplitudes(self, slider_index, gain, input_amplitudes, output_amplitudes,
                                 window_index, parameter, frequency_comp, freqGraph):
        
        start, end = self.mode.ind_range[slider_index][0], self.mode.ind_range[slider_index][1]
        print(start, end)
        print(gain)
        output_amplitudes[start:end] = gain * input_amplitudes[start:end]
        output_amplitudes[start:end] = f.apply_smoothing_window(output_amplitudes, window_index, parameter, freqGraph,start, end, frequency_comp)

        return output_amplitudes

    def modifying_amplitudes(self, slider_index, gain, input_amplitudes, output_amplitudes, window_index,
                             parameter):

        output_amplitudes = self.modify_output_amplitudes(slider_index, gain, input_amplitudes,
                                                     output_amplitudes, window_index, parameter, self.frequency_comp,
                                                     self.freqGraph)

        self.smooth_and_inverse_transform(output_amplitudes)

    def get_smoothing_window(self, window_index, plot_widget, output_amp, freq_comp, parameter):
        self.modifying_amplitudes(0, 1, output_amp, output_amp, window_index, 1)

    def customize_smoothing_window_parameters(self, value, window_index, plot_widget, output_amp, freq_comp):
        new_value = value
        self.modifying_amplitudes(0, 1, output_amp, output_amp, window_index, new_value)

    def smooth_and_inverse_transform(self, output_amplitudes):
        self.edited_time_domain_signal = f.compute_inverse_fourier_transform(output_amplitudes, self.frequency_comp, self.phases)
        self.OutputGraph.clear()
        # if self.state == True:
        f.plot_waveform(self.edited_time_domain_signal, self.sample_rate, self.OutputGraph)
        if self.showCheckBox.isChecked():
            f.plot_specto(self.edited_time_domain_signal, self.sample_rate, self.spectoframe2, self.showCheckBox)

    def play_output_signal(self, button, samples, sample_rate):
        if self.playing:
            sd.stop()
            self.playing = False
        else:
            new_samples = samples.astype(np.float32) / 32767.0  # Convert int16 to float32
            sd.play(new_samples, sample_rate)
            self.playing = True
        f.update_button_icon(button, self.playing)

    def play_n_pause(self, button, sound):
        if self.timer.isActive():
            self.timer.stop()
            if sound: 
                self.media_playerIN.pause()
        else:
            self.timer.start(f.speed(self.speedSlider.value(),self.speedLabel))
            if sound: 
                self.media_playerIN.play()
                
        f.update_button_icon(button, self.timer.isActive())
            
    def reset_sliders(self):
        for slider in self.sliders_list:
            slider.setValue(1)
        self.output_amplitudes = self.amplitudes.copy()


def main():
    app = QApplication(sys.argv)

    with open("style.qss", "r") as f:
        _style = f.read()
        app.setStyleSheet(_style)

    window = MainApp()
    window.show()
    app.exec_()


if __name__ == '__main__':
    main()
