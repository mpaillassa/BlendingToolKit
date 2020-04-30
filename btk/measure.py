import multiprocessing as mp
from itertools import starmap
from abc import ABC, abstractmethod


# REVIEW: Make into abstract data class? This enforces that children need to overwrite new methods and
#         Measurement_params can't instantiated directly.
class Measurement_params(ABC):
    """Class with functions to perform detection/deblending/measurement."""

    @abstractmethod
    def make_measurement(self, data=None, index=None):
        """Function describing how the measurement algorithm is run.

        Args:
            data (dict): Output generated by btk.draw_blends containing blended
                         images, isolated images, observing conditions and
                         blend catalog, for a given batch.
            index (int): Index number of blend scene in the batch to preform
                         measurement on.

        Returns:
            output of measurement algorithm as a dict.
        """
        return None

    @abstractmethod
    def get_deblended_images(self, data=None, index=None):
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


# REVIEW: avoid shadowing names from outer scope?
# REVIEW: Purpose of this function? also what is blend_output?
def run_batch(measurement_params, blend_output, index):
    deblend_results = measurement_params.get_deblended_images(
        data=blend_output, index=index)
    measured_results = measurement_params.make_measurement(
        data=blend_output, index=index)
    return [deblend_results, measured_results]


# REVIEW: is multiprocessing here only used to draw blends from the generator in batches?
#         the network results might live in a GPU?
def generate(measurement_params, draw_blend_generator, Args,
             multiprocessing=False, cpus=1):
    """Generates output of deblender and measurement algorithm.

    Args:
        measurement_params: Class containing functions to perform deblending
                            and or measurement.
        draw_blend_generator: Generator that outputs dict with blended images,
                              isolated images, observing conditions and blend
                              catalog.
        Args: Class containing input parameters.
        multiprocessing: If true performs multiprocessing of measurement.
        cpus: If multiprocessing is True, then number of parallel processes to
             run [Default :1].
    Returns:
        draw_blend_generator output, deblender output and measurement output.
    """
    while True:
        blend_output = next(draw_blend_generator)
        batch_size = len(blend_output['blend_images'])
        deblend_results = {}
        measured_results = {}
        in_args = [(measurement_params,
                    blend_output, i) for i in range(Args.batch_size)]
        if multiprocessing:
            if Args.verbose:
                print(f"Running mini-batch of size {len(in_args)} with",
                      f"multiprocessing with pool {cpus}")
            with mp.Pool(processes=cpus) as pool:
                batch_results = pool.starmap(run_batch, in_args)
        else:
            if Args.verbose:
                print(f"Running mini-batch of size {len(in_args)} in",
                      f"serial with pool {cpus}")
            batch_results = list(starmap(run_batch, in_args))
        for i in range(batch_size):
            deblend_results.update(
                {i: batch_results[i][0]})
            measured_results.update(
                {i: batch_results[i][1]})
        if Args.verbose:
            print("Measurement performed on batch")
        yield blend_output, deblend_results, measured_results
