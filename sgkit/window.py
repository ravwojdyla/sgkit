from typing import Any, Callable, Tuple

import dask.array as da
import numpy as np
from xarray import Dataset

from sgkit.utils import conditional_merge_datasets

from .typing import ArrayLike, DType

# Window definition (user code)


def window(
    ds: Dataset,
    size: int,
    step: int,
    merge: bool = True,
) -> Dataset:
    """Add fixed-size windowing information to a dataset.

    Windows are defined over the ``variants`` dimension, and are
    used by some downstream functions to calculate statistics for
    each window.

    Parameters
    ----------
    ds
        Genotype call dataset.
    size
        The window size (number of variants).
    step
        The distance (number of variants) between start positions of windows.
    merge
        If True (the default), merge the input dataset and the computed
        output variables into a single dataset, otherwise return only
        the computed output variables.
        See :ref:`dataset_merge` for more details.

    Returns
    -------
    A dataset containing the following variables:

    - :data:`sgkit.variables.window_start_spec` (windows):
      The index values of window start positions.
    - :data:`sgkit.variables.window_stop_spec` (windows):
      The index values of window stop positions.
    """
    n_variants = ds.dims["variants"]

    length = n_variants
    window_starts, window_stops = _get_windows(0, length, size, step)

    new_ds = Dataset(
        {
            "window_start": (
                "windows",
                window_starts,
            ),
            "window_stop": (
                "windows",
                window_stops,
            ),
        }
    )
    return conditional_merge_datasets(ds, new_ds, merge)


def _get_windows(
    start: int, stop: int, size: int, step: int
) -> Tuple[ArrayLike, ArrayLike]:
    # Find the indexes for the start positions of all windows
    # TODO: take contigs into account https://github.com/pystatgen/sgkit/issues/335
    window_starts = np.arange(start, stop, step)
    window_stops = np.clip(window_starts + size, start, stop)
    return window_starts, window_stops


# Computing statistics for windows (internal code)


def has_windows(ds: Dataset) -> bool:
    """Test if a dataset has windowing information."""
    return "window_start" in ds and "window_stop" in ds


def moving_statistic(
    values: ArrayLike,
    statistic: Callable[..., ArrayLike],
    size: int,
    step: int,
    dtype: DType,
    **kwargs: Any,
) -> da.Array:
    """A Dask implementation of scikit-allel's moving_statistic function."""
    length = values.shape[0]
    chunks = values.chunks[0]
    if len(chunks) > 1:
        min_chunksize = np.min(chunks[:-1])  # ignore last chunk
    else:
        min_chunksize = np.min(chunks)
    if min_chunksize < size:
        raise ValueError(
            f"Minimum chunk size ({min_chunksize}) must not be smaller than size ({size})."
        )
    window_starts, window_stops = _get_windows(0, length, size, step)
    return window_statistic(
        values, statistic, window_starts, window_stops, dtype, **kwargs
    )


def window_statistic(
    values: ArrayLike,
    statistic: Callable[..., ArrayLike],
    window_starts: ArrayLike,
    window_stops: ArrayLike,
    dtype: DType,
    **kwargs: Any,
) -> da.Array:

    values = da.asarray(values)

    length = values.shape[0]
    window_lengths = window_stops - window_starts
    depth = np.max(window_lengths)

    # Dask will raise an error if the last chunk size is smaller than the depth
    # Workaround by rechunking to combine the last two chunks in first axis
    # See https://github.com/dask/dask/issues/6597
    if depth > values.chunks[0][-1]:
        chunk0 = values.chunks[0]
        new_chunk0 = tuple(list(chunk0[:-2]) + [chunk0[-2] + chunk0[-1]])
        values = values.rechunk({0: new_chunk0})

    chunks = values.chunks[0]

    rel_window_starts, windows_per_chunk = _get_chunked_windows(
        chunks, length, window_starts, window_stops
    )

    # Add depth for map_overlap
    rel_window_starts = rel_window_starts + depth
    rel_window_stops = rel_window_starts + window_lengths

    chunk_offsets = _sizes_to_start_offsets(windows_per_chunk)

    def blockwise_moving_stat(x: ArrayLike, block_info: Any = None) -> ArrayLike:
        if block_info is None or len(block_info) == 0:
            return np.array([])
        chunk_number = block_info[0]["chunk-location"][0]
        chunk_offset_start = chunk_offsets[chunk_number]
        chunk_offset_stop = chunk_offsets[chunk_number + 1]
        chunk_window_starts = rel_window_starts[chunk_offset_start:chunk_offset_stop]
        chunk_window_stops = rel_window_stops[chunk_offset_start:chunk_offset_stop]
        out = np.array(
            [
                statistic(x[i:j], **kwargs)
                for i, j in zip(chunk_window_starts, chunk_window_stops)
            ]
        )
        return out

    if values.ndim == 1:
        new_chunks = (tuple(windows_per_chunk),)
    else:
        # depth is 0 except in first axis
        depth = {0: depth}
        # new chunks are same except in first axis
        new_chunks = tuple([tuple(windows_per_chunk)] + list(values.chunks[1:]))  # type: ignore
    return values.map_overlap(
        blockwise_moving_stat,
        dtype=dtype,
        chunks=new_chunks,
        depth=depth,
        boundary=0,
        trim=False,
    )


def _sizes_to_start_offsets(sizes: ArrayLike) -> ArrayLike:
    """Convert an array of sizes, to cumulative offsets, starting with 0"""
    return np.cumsum(np.insert(sizes, 0, 0, axis=0))


def _get_chunked_windows(
    chunks: ArrayLike,
    length: int,
    window_starts: ArrayLike,
    window_stops: ArrayLike,
) -> Tuple[ArrayLike, ArrayLike]:
    """Find the window start positions relative to the start of the chunk they are in,
    and the number of windows in each chunk."""

    # Find the indexes for the start positions of all chunks
    chunk_starts = _sizes_to_start_offsets(chunks)

    # Find which chunk each window falls in
    chunk_numbers = np.searchsorted(chunk_starts, window_starts, side="right") - 1

    # Find the start positions for each window relative to each chunk start
    rel_window_starts = window_starts - chunk_starts[chunk_numbers]

    # Find the number of windows in each chunk
    _, windows_per_chunk = np.unique(chunk_numbers, return_counts=True)

    return rel_window_starts, windows_per_chunk
