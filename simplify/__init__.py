from typing import List

import torch
import torch.nn as nn

from . import layers
from .fuse import fuse
from .propagate import propagate_bias
from .remove import remove_zeroed

__version__ = "1.0.1"


def simplify(model: nn.Module, x: torch.Tensor, pinned_out: List = None, bn_folding: List = None) -> nn.Module:
    # TODO: if pinned_out is defined via graph we cannot pass it here
    if bn_folding is None:
        bn_folding = []
    if pinned_out is None:
        pinned_out = []
    
    fuse(model, bn_folding)
    propagate_bias(model, x, pinned_out)
    remove_zeroed(model, x, pinned_out)
    
    return model
