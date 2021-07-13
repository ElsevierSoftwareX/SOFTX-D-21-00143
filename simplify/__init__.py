from typing import List

import torch
import torch.nn as nn

from . import layers
from . import utils
from .fuse import fuse
from .propagate import propagate_bias
from .remove import remove_zeroed

__version__ = "1.0.1"


def simplify(model: nn.Module, x: torch.Tensor, fuse_bn: bool = True, bn_folding: List = None,
             training: bool = False) -> nn.Module:
    if fuse_bn or training:
        if bn_folding is None:
            bn_folding = utils.get_bn_folding(model)
        if fuse_bn:
            fuse(model, bn_folding)
    
    pinned_out = utils.get_pinned_out(model)
    
    if training:
        new_pinned_out = []
        for pinned in pinned_out:
            new_pinned_out.append(pinned)
            for conv_bn in bn_folding:
                if pinned in conv_bn:
                    new_pinned_out.append(conv_bn[1])
                    break
                    
        pinned_out = new_pinned_out
        
    propagate_bias(model, x, pinned_out)
    remove_zeroed(model, x, pinned_out, training=training)
    
    return model
