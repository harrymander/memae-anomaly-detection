import math

import torch
from torch import nn
from torch.nn import functional as F
from torch.nn.parameter import Parameter


class MemoryUnit(nn.Module):
    def __init__(self, mem_dim, fea_dim, shrink_thres=0.0025):
        super().__init__()
        self.mem_dim = mem_dim
        self.fea_dim = fea_dim
        self.weight = Parameter(
            torch.Tensor(self.mem_dim, self.fea_dim)
        )  # M x C
        self.bias = None
        self.shrink_thres = shrink_thres
        # self.hard_sparse_shrink_opt = nn.Hardshrink(lambd=shrink_thres)

        self.reset_parameters()

    def reset_parameters(self):
        stdv = 1.0 / math.sqrt(self.weight.size(1))
        self.weight.data.uniform_(-stdv, stdv)
        if self.bias is not None:
            self.bias.data.uniform_(-stdv, stdv)

    def forward(self, input):
        att_weight = F.linear(
            input, self.weight
        )  # Fea x Mem^T, (TxC) x (CxM) = TxM
        att_weight = F.softmax(att_weight, dim=1)  # TxM
        # ReLU based shrinkage, hard shrinkage for positive value
        if self.shrink_thres > 0:
            att_weight = hard_shrink_relu(att_weight, lambd=self.shrink_thres)
            # att_weight = F.softshrink(att_weight, lambd=self.shrink_thres)
            # normalize???
            att_weight = F.normalize(att_weight, p=1, dim=1)
            # att_weight = F.softmax(att_weight, dim=1)
            # att_weight = self.hard_sparse_shrink_opt(att_weight)
        mem_trans = self.weight.permute(1, 0)  # Mem^T, MxC
        output = F.linear(
            att_weight, mem_trans
        )  # AttWeight x Mem^T^T = AW x Mem, (TxM) x (MxC) = TxC
        return {"output": output, "att": att_weight}  # output, att_weight

    def extra_repr(self):
        return f"mem_dim={self.mem_dim}, fea_dim={self.fea_dim is not None}"


# NxCxHxW -> (NxHxW)xC -> addressing Mem, (NxHxW)xC -> NxCxHxW
class MemModule(nn.Module):
    def __init__(self, mem_dim, fea_dim, shrink_thres=0.0025, device="cuda"):
        super().__init__()
        self.mem_dim = mem_dim
        self.fea_dim = fea_dim
        self.shrink_thres = shrink_thres
        self.memory = MemoryUnit(self.mem_dim, self.fea_dim, self.shrink_thres)

    def forward(self, input):
        s = input.data.shape
        ndim = len(s)

        if ndim == 3:
            x = input.permute(0, 2, 1)
        elif ndim == 4:
            x = input.permute(0, 2, 3, 1)
        elif ndim == 5:
            x = input.permute(0, 2, 3, 4, 1)
        else:
            x = []
            print("wrong feature map size")
        x = x.contiguous()
        x = x.view(-1, s[1])

        y_and = self.memory(x)

        y = y_and["output"]
        att = y_and["att"]

        if ndim == 3:
            y = y.view(s[0], s[2], s[1])
            y = y.permute(0, 2, 1)
            att = att.view(s[0], s[2], self.mem_dim)
            att = att.permute(0, 2, 1)
        elif ndim == 4:
            y = y.view(s[0], s[2], s[3], s[1])
            y = y.permute(0, 3, 1, 2)
            att = att.view(s[0], s[2], s[3], self.mem_dim)
            att = att.permute(0, 3, 1, 2)
        elif ndim == 5:
            y = y.view(s[0], s[2], s[3], s[4], s[1])
            y = y.permute(0, 4, 1, 2, 3)
            att = att.view(s[0], s[2], s[3], s[4], self.mem_dim)
            att = att.permute(0, 4, 1, 2, 3)
        else:
            y = x
            att = att
            print("wrong feature map size")
        return {"output": y, "att": att}


# relu based hard shrinkage function, only works for positive values
def hard_shrink_relu(input, lambd=0, epsilon=1e-12):
    output = (F.relu(input - lambd) * input) / (
        torch.abs(input - lambd) + epsilon
    )
    return output
