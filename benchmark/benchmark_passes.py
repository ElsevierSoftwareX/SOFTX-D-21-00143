import time

import numpy as np
import torch
from matplotlib import pyplot as plt
from torch import nn
from torch.nn import CrossEntropyLoss
from torch.nn.utils import prune
from torchvision.models.resnet import resnet101
from tqdm import tqdm
import simplify

import wandb
from simplify import propagate, remove_zeroed
from simplify.utils import get_pinned_out

if __name__ == '__main__':
    network = resnet101
    model = network(True)
    simplify.fuse(model, simplify.utils.get_bn_folding(model))
    device = torch.device("cuda")
    batch_size = 128
    fake_input = torch.randint(0, 256, (batch_size, 3, 224, 224))
    fake_input = fake_input.float() / 255.
    fake_target = torch.randint(0, 1000, (batch_size,)).long()
    
    fake_input, fake_target = fake_input.to(device), fake_target.to(device)
    
    criterion = CrossEntropyLoss()
    
    iterations = 500
    
    total_neurons = 0
    remaining_neurons = 0
    for name, module in model.named_modules():
        if isinstance(module, nn.Conv2d):
            total_neurons += module.weight.shape[0]
            remaining_neurons += module.weight.shape[0]
    
    x = []
    pruned_y_forward = []
    pruned_y_forward_std = []
    pruned_y_backward = []
    pruned_y_backward_std = []
    
    simplified_y_forward = []
    simplified_y_forward_std = []
    simplified_y_backward = []
    simplified_y_backward_std = []
    
    amount = 0.
    
    wandb.init(group="benchmark_passes")
    for i in tqdm(range(iterations), desc="Benchmark"):
        if amount > 1.:
            break
        model = network(True)
        simplify.fuse(model, simplify.utils.get_bn_folding(model))

        # First loop is the full model
        if i > 0:
            remaining_neurons = 0
            for name, module in model.named_modules():
                if isinstance(module, nn.Conv2d):
                    prune.ln_structured(module, 'weight', amount=amount, n=2, dim=0)
                    ch_sum = module.weight.sum(dim=(1, 2, 3))
                    remaining_neurons += ch_sum[ch_sum != 0].shape[0]
                    prune.remove(module, 'weight')
        
        x.append(100 - (remaining_neurons / total_neurons) * 100)
        
        # PRUNED
        forward_time = []
        backward_time = []
        model.to(device)
        for j in tqdm(range(10), desc="Pruned test"):
            if device == torch.device("cuda"):
                starter, ender = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
                starter.record()
            else:
                start = time.perf_counter()
            
            output = model(fake_input)  # FORWARD PASS
            
            if device == torch.device("cuda"):
                ender.record()
                torch.cuda.synchronize()
            else:
                end = time.perf_counter()
            
            forward_time.append(starter.elapsed_time(ender) if device == torch.device("cuda") else end - start)
            
            loss = criterion(output, fake_target)
            
            if device == torch.device("cuda"):
                starter, ender = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
                starter.record()
            else:
                start = time.perf_counter()
            
            loss.backward()  # BACKWARD PASS
            
            if device == torch.device("cuda"):
                ender.record()
                torch.cuda.synchronize()
            else:
                end = time.perf_counter()
            
            backward_time.append(starter.elapsed_time(ender) if device == torch.device("cuda") else end - start)
        
        forward_time = forward_time[1:]
        backward_time = backward_time[1:]
        
        pruned_y_forward.append(np.mean(forward_time))
        pruned_y_forward_std.append(np.std(forward_time))
        pruned_y_backward.append(np.mean(backward_time))
        pruned_y_backward_std.append(np.std(backward_time))
        
        wandb.log({
            'pruned.forward':      np.mean(forward_time),
            'pruned.forward_std':  np.std(forward_time),
            'pruned.backward':     np.mean(backward_time),
            'pruned.backward_std': np.std(backward_time)
        }, commit=False)
        
        # SIMPLIFIED
        pinned_out = get_pinned_out(model)
        propagate.propagate_bias(model, torch.zeros(1, 3, 224, 224).to(device), pinned_out)
        remove_zeroed(model, torch.zeros(1, 3, 224, 224).to(device), pinned_out)
        
        forward_time = []
        backward_time = []
        model.to(device)
        for j in tqdm(range(10), desc="Simplified test"):
            if device == torch.device("cuda"):
                starter, ender = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
                starter.record()
            else:
                start = time.perf_counter()
            
            output2 = model(fake_input)  # FORWARD PASS
            
            if device == torch.device("cuda"):
                ender.record()
                torch.cuda.synchronize()
            else:
                end = time.perf_counter()
            
            forward_time.append(starter.elapsed_time(ender) if device == torch.device("cuda") else end - start)
            
            loss2 = criterion(output2, fake_target)
            
            if device == torch.device("cuda"):
                starter, ender = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
                starter.record()
            else:
                start = time.perf_counter()
            
            loss2.backward()  # BACKWARD PASS
            
            if device == torch.device("cuda"):
                ender.record()
                torch.cuda.synchronize()
            else:
                end = time.perf_counter()
            
            backward_time.append(starter.elapsed_time(ender) if device == torch.device("cuda") else end - start)
        
        forward_time = forward_time[1:]
        backward_time = backward_time[1:]
        
        simplified_y_forward.append(np.mean(forward_time))
        simplified_y_forward_std.append(np.std(forward_time))
        simplified_y_backward.append(np.mean(backward_time))
        simplified_y_backward_std.append(np.std(backward_time))
        
        print(torch.equal(output.argmax(dim=1), output2.argmax(dim=1)))
        assert torch.equal(output.argmax(dim=1), output2.argmax(dim=1))
        
        wandb.log({
            'simplified.forward':      np.mean(forward_time),
            'simplified.forward_std':  np.std(forward_time),
            'simplified.backward':     np.mean(backward_time),
            'simplified.backward_std': np.std(backward_time),
            'remaining_neurons':       100. - x[-1]
        })
        
        amount += 0.05
        del model
        torch.cuda.empty_cache()
    
    # plt.errorbar(x, pruned_y_forward, pruned_y_forward_std, label="pruned")
    # plt.errorbar(x, simplified_y_forward, simplified_y_forward_std, label="simplified")
    # plt.title("Forward")
    # plt.xlabel("Pruning (%)")
    # plt.ylabel("Time (s)")
    # plt.legend()
    # plt.savefig("Forward.png", dpi=300)
    # plt.clf()
    #
    # plt.errorbar(x, pruned_y_backward, pruned_y_backward_std, label="pruned")
    # plt.errorbar(x, simplified_y_backward, simplified_y_backward_std, label="simplified")
    # plt.title("Backward")
    # plt.xlabel("Pruning (%)")
    # plt.ylabel("Time (s)")
    # plt.legend()
    # plt.savefig("Backward.png", dpi=300)
    # plt.clf()