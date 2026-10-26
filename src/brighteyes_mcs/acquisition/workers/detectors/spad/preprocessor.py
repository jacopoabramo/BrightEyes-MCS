"""FIFO preprocessing worker that forwards raw queue payloads as typed numpy arrays."""

from brighteyes_mcs.logging_setup import logged_worker
import multiprocessing as mp
import queue
import numpy as np
from brighteyes_mcs.logging_setup import logger, set_debug

# from ...is_parent_alive import CheckParentAlive
import os
import time
import psutil


class DataPreProcess(mp.Process):
    def __init__(
        self,
        queue_in,
        dict_of_shared_loc,
        last_preprocessed_len,
        dict_of_queue_array_out,
        dict_of_dtype_queue_array_out,
        debug=False,
        use_rust_fifo=True,
    ):
        super().__init__()
        self.daemon = True
        """
        :param queue_in: this is the queue from the fpgahandleprocess each elements contains ("FIFONAME", data)
        :param dict_of_shared_loc: {'FIFONAME':shared_loc_fifo,...}
        :param dict_of_queue_array_out: {'FIFONAME':shared_queue_array_out,...}
        :param dict_of_dtype_queue_array_out: {'FIFONAME':dtype_shared_queue_array_out,...}
        """
        # def __init__(self, queue_in, buffer, loc, dict_of_queue_array_out):
        set_debug(debug)
        logger.debug("DataPreProcess INIT")
        self.queue_in = queue_in
        self.dict_of_shared_loc = dict_of_shared_loc
        self.last_preprocessed_len = last_preprocessed_len
        # self.shm_data = buffer

        self.index = 0
        # print("I",id(self.databuffer))
        self.stop_event = mp.Event()
        self.stop_event.clear()

        self.stop_event_done = mp.Event()
        self.stop_event_done.clear()

        self.dict_of_queue_array_out = dict_of_queue_array_out
        self.dict_of_dtype_queue_array_out = dict_of_dtype_queue_array_out

    @logged_worker
    def run(self) -> None:
        logger.debug("%s %s", "DataPreProcess RUN - PID:", os.getpid())
        while not self.stop_event.is_set():
            try:
                # TODO: receive from the sharedbox FIFO stream.
                fifo_name, words = self.queue_in.get(timeout=0.1)
            except queue.Empty:
                continue
            data_as_array = np.asarray(words, dtype=np.uint64).astype(
                self.dict_of_dtype_queue_array_out[fifo_name]
            )
            self.dict_of_queue_array_out[fifo_name].put(data_as_array)
            self.dict_of_shared_loc[fifo_name].value += len(data_as_array)
            self.last_preprocessed_len[fifo_name].value = len(data_as_array)

        self.stop_event.clear()
        self.stop_event_done.set()
        logger.debug("%s %s", "DataPreProcess self.stop_event.clear() PID: ", os.getpid())

    def stop(self):
        # databuffer = self.shm_data.get_numpy_handle()
        logger.debug("DataPreProcess STOP")
        self.stop_event.set()
        logger.debug("waiting for self.stop_event_done")
        self.stop_event_done.wait(5000)
        logger.debug("waiting for self.stop_event_done DONE")
        self.terminate()

    def terminate(self) -> None:
        logger.debug("DataPreProcess.terminate()")
        time.sleep(0.1)
        super().terminate()


class SpadDataPreProcess(DataPreProcess):
    """SPAD-named FIFO preprocessing worker."""
