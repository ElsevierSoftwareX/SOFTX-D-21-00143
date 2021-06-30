from numpy import isin
from torchvision.models.alexnet import alexnet
from simplify.layers import ConvExpand
import torch
from torch import nn
from torch.nn.utils import prune
from torchvision.models import resnet18

import numpy as np
import time
import utils
from simplify import propagate_bias, remove_zeroed, fuse

if __name__ == '__main__':
    utils.set_seed(3)
    model = resnet18(True)
    print(model)
    for module in model.modules():
        if isinstance(module, nn.ReLU):
            module.inplace = True

    optimizer = torch.optim.SGD(model.parameters(), lr=0.1)

    bn_folding = utils.get_bn_folding(model)
    model = fuse(model, bn_folding)
    model.eval()
    pinned_out = utils.get_pinned_out(model)
    
    im = torch.randint(0, 256, (10, 3, 224, 224))
    x = im / 255.
    
    zeros = torch.zeros(1, *im.shape[1:])
    
    for name, module in model.named_modules():
        if isinstance(module, nn.Conv2d):
            prune.random_structured(module, name="weight", amount=0.5, dim=0)
            prune.remove(module, 'weight')
    

    times_pruned = []
    for i in range(10):
        start = time.perf_counter()
        y = model(x)
        y.sum().backward()
        optimizer.step()
        optimizer.zero_grad()
        length = time.perf_counter() - start
        times_pruned.append(length)

    for e in range(2):
        s = "Simplification #{}".format(e)
        print("#"*len(s))
        print(s)
        print("#"*len(s))
        
        #for module in model.modules():
        #    if isinstance(module, ConvExpand):
        #        module.expand()

        #optimizer = torch.optim.SGD(model.parameters(), lr=0.1)
        y = model(x)
        y.sum().backward()
        optimizer.step()
        optimizer.zero_grad()

        #for module in model.modules():
        #    if isinstance(module, ConvExpand):
        #        module.reduce()
        #optimizer.zero_grad()


        model.eval()
        y_src = model(x)
        
        propagate_bias(model, zeros, pinned_out)
        model.eval()
        y_prop = model(x)
        
        print("Bias propagation")
        print("Max abs diff: ", (y_src - y_prop).abs().max().item())
        print("MSE diff: ", nn.MSELoss()(y_src, y_prop).item())
        print(f'Correct predictions: {torch.eq(y_src.argmax(dim=1), y_prop.argmax(dim=1)).sum()}/{y_prop.shape[0]}')
        
        print("")
        
        remove_zeroed(model, zeros, pinned_out)
        model.eval()
        y_prop = model(x)
        
        print("Channel removal")
        print("Max abs diff: ", (y_src - y_prop).abs().max().item())
        print("MSE diff: ", nn.MSELoss()(y_src, y_prop).item())
        print(f'Correct predictions: {torch.eq(y_src.argmax(dim=1), y_prop.argmax(dim=1)).sum()}/{y_prop.shape[0]}')
        
        print(model)
        print("")

    times_simplified = []
    for i in range(10):
        start = time.perf_counter()
        y = model(x)
        y.sum().backward()
        optimizer.step()
        optimizer.zero_grad()
        length = time.perf_counter() - start
        times_simplified.append(length)
    
    print('Pruned time:', np.mean(times_pruned))
    print('Simplified time:', np.mean(times_simplified))
        
