import numpy as np
import backtrader as bt
from scipy.signal import hilbert

__all__ = ['HilbertTransform']


class HilbertTransform(bt.Indicator):
    """
    Hilbert Transform Indicator
    This indicator calculates the Hilbert Transform of the input data series.
    The imaginary part of the analytic signal is returned as the output.
    """
    lines = ('hilbert',)
    params = (
        ('period', 60),  # Period for minimum data length
    )

    def __init__(self):
        """
        Initialization of the indicator.
        Sets the minimum period required for the calculation.
        """
        self.addminperiod(self.p.period)
        self.min_size = self.p.period * 5

    def next(self, status):
        """
        Calculates the indicator value for the current bar.
        Note: This method is computationally expensive as it recalculates the transform
        for the entire available series on each new bar.
        The `once` method is recommended for performance.
        """
        series = np.asarray(self.data.get_array(), dtype=np.float64)
        
        # Calculate Hilbert Transform
        analytic_signal = hilbert(series)
        
        # Store the imaginary part of the last element
        self.lines.hilbert[0] = np.imag(analytic_signal)[-1]

    def once(self, start, end):
        if end-start==1:
            return

        """
        Vectorized calculation of the indicator.
        This is the recommended method for performance.
        """
        # Get the entire data series as a numpy array
        series = np.asarray(self.data.get_array_preloaded(), dtype=np.float64)
        
        # Calculate Hilbert Transform for the entire series
        analytic_signal = hilbert(series)
        
        # Get the imaginary part
        imag_part = np.imag(analytic_signal)
        
        # Set the line buffer with the calculated values
        self.lines.hilbert.ndbuffer(imag_part)
