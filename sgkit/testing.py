from typing import Optional

import numpy as np

from .api import create_genotype_call_dataset


def simulate_genotype_call_dataset(
    n_variant: int,
    n_sample: int,
    n_ploidy: int = 2,
    n_allele: int = 2,
    n_contig: int = 1,
    seed: Optional[int] = None,
):
    """Simulate genotype calls and variant/sample data

    Parameters
    ----------
    n_variant : int
        Number of variants to simulate
    n_sample : int
        Number of samples to simulate
    n_ploidy : int
        Number of chromosome copies in each sample
    n_contig : int, optional
        Number of contigs to partition variants with,
        controlling values in `variant/contig`. Values
        will all be 0 by default with `n_contig` == 1.
    seed : int, optional
        Seed for random number generation

    Returns
    -------
    Dataset
        Dataset from `sgkit.create_genotype_call_dataset`
    """
    rs = np.random.RandomState(seed=seed)
    call_genotype = rs.randint(
        0, n_allele, size=(n_variant, n_sample, n_ploidy), dtype=np.int8
    )
    contig_size = np.ceil(n_variant / n_contig).astype(int)
    contig = np.arange(n_variant) // contig_size
    contig_names = np.unique(contig)
    position = np.concatenate([np.arange(contig_size) for i in range(n_contig)])
    position = position[:n_variant]
    alleles = rs.choice(["A", "C", "G", "T"], size=(n_variant, n_allele)).astype("S")
    sample_id = np.array([f"S{i}" for i in range(n_sample)])
    return create_genotype_call_dataset(
        variant_contig_names=list(contig_names),
        variant_contig=contig,
        variant_position=position,
        variant_alleles=alleles,
        sample_id=sample_id,
        call_genotype=call_genotype,
    )
