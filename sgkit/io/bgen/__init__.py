try:
    from .bgen_reader import bgen_to_zarr, read_bgen, rechunk_bgen
except ImportError as e:
    msg = (
        "sgkit bgen requirements are not installed.\n\n"
        "Please install them via pip :\n\n"
        "  pip install 'git+https://github.com/pystatgen/sgkit#egg=sgkit[bgen]'"
    )
    raise ImportError(str(e) + "\n\n" + msg) from e
