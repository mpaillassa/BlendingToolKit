from abc import ABC

import numpy as np
import sep
from skimage.feature import peak_local_max

from btk.multiprocess import multiprocess


class MeasurementParams(ABC):
    """Class with functions to perform detection/deblending/measurement."""

    def make_measurement(self, data, index):
        """Function describing how the measurement algorithm is run.

        Args:
            data (dict): Output generated by btk.draw_blends containing blended
                         images, isolated images, observing conditions and
                         blend catalog, for a given batch.
            index (int): Index number of blend scene in the batch to preform
                         measurement on.

        Returns:
            output of measurement algorithm (fluxes, shapes, size, etc.) as
            an astropy catalog.
        """
        return None

    def get_deblended_images(self, data, index):
        """Function describing how the deblending algorithm is run.

        Args:
            data (dict): Output generated by btk.draw_blends containing blended
                         images, isolated images, observing conditions and
                         blend catalog, for a given batch.
            index (int): Index number of blend scene in the batch to preform
                         measurement on.

        Returns:
            output of deblending algorithm as a dict.
        """
        return None


class BasicMeasureParams(MeasurementParams):
    """Class to perform detection by identifying peaks with skimage"""

    @staticmethod
    def get_centers(image):
        """Return centers detected when object detection is performed on the
        input image with skimage.feature.peak_local_max.

        Args:
            image (np.ndarray): Image (single band) of galaxy to perform measurement

        Returns:
                centers: x and y coordinates of detected  centroids
        """
        # set detection threshold to 5 times std of image
        threshold = 5 * np.std(image)
        coordinates = peak_local_max(image, min_distance=2, threshold_abs=threshold)
        return np.stack((coordinates[:, 1], coordinates[:, 0]), axis=1)

    def get_deblended_images(self, data, index):
        """Returns scarlet modeled blend and centers for the given blend"""
        image = np.mean(data["blend_images"][index], axis=2)
        peaks = self.get_centers(image)
        return {"deblend_image": None, "peaks": peaks}


class SepParams(MeasurementParams):
    """Class to perform detection and deblending with SEP"""

    def __init__(self):
        self.catalog = None
        self.segmentation = None

    def get_centers(self, image):
        """Return centers detected when object detection and photometry
        is done on input image with SEP.
        It also initializes the self.catalog and self.segmentation attributes
        of the class object.
        Args:
            image: Image (single band) of galaxy to perform measurement on.
        Returns:
            centers: x and y coordinates of detected  centroids
        """
        bkg = sep.Background(image)
        self.catalog, self.segmentation = sep.extract(
            image, 1.5, err=bkg.globalrms, segmentation_map=True
        )
        centers = np.stack((self.catalog["x"], self.catalog["y"]), axis=1)
        return centers

    def get_deblended_images(self, data, index):
        """Performs SEP detection on the band-coadd image and returns the
        detected peaks.
        Args:
            data (dict): Output generated by btk.draw_blends containing blended
                images, isolated images, observing conditions and blend
                catalog, for a given batch.
            index (int): Index number of blend scene in the batch to preform
                measurement on.
        Returns:
            dict with the centers of sources detected by SEP detection
            algorithm.
        """
        image = np.mean(data["blend_images"][index], axis=2)
        peaks = self.get_centers(image)
        return {"deblend_image": None, "peaks": peaks}


class MeasureGenerator:
    def __init__(
        self,
        measurement_params,
        draw_blend_generator,
        multiprocessing=False,
        cpus=1,
        verbose=False,
    ):
        """Generates output of deblender and measurement algorithm.

        Args:
            measurement_params: Instance from class
                                `btk.measure.Measurement_params`.
            draw_blend_generator: Generator that outputs dict with blended images,
                                  isolated images, observing conditions and blend
                                  catalog.
            multiprocessing: If true performs multiprocessing of measurement.
            cpus: If multiprocessing is True, then number of parallel processes to
                 run [Default :1].
        """
        self.measurement_params = measurement_params
        self.draw_blend_generator = draw_blend_generator
        self.multiprocessing = multiprocessing
        self.cpus = cpus

        self.batch_size = self.draw_blend_generator.batch_size

        self.verbose = verbose

    def __iter__(self):
        return self

    def run_batch(self, blend_output, index):
        deblend_results = self.measurement_params.get_deblended_images(
            data=blend_output, index=index
        )
        measured_results = self.measurement_params.make_measurement(data=blend_output, index=index)
        return [deblend_results, measured_results]

    def __next__(self):
        """
        Returns:
            draw_blend_generator output, deblender output and measurement output.
        """

        blend_output = next(self.draw_blend_generator)
        deblend_results = {}
        measured_results = {}
        input_args = [(blend_output, i) for i in range(self.batch_size)]
        batch_results = multiprocess(
            self.run_batch,
            input_args,
            self.cpus,
            self.multiprocessing,
            self.verbose,
        )
        for i in range(self.batch_size):
            deblend_results.update({i: batch_results[i][0]})
            measured_results.update({i: batch_results[i][1]})
        if self.verbose:
            print("Measurement performed on batch")
        return blend_output, deblend_results, measured_results
