from train import FeedForward
import torch
import torch.nn as nn
from torch.nn import functional as F


class Head(nn.Module):
    def __init__(self,block_size,head_size): #constructor taking context length and head dim 
        super().__init__()
        #linear layers for key query and value 
        self.key = nn.Linear(head_size, head_size, bias=False) # linear layer for key

        self.query = nn.Linear(head_size, head_size, bias=False)# linear layer for query(what is this token searching for)
        self.value = nn.Linear(head_size, head_size, bias=False) # linear layer for value(what information does this token contain)

        self.register_buffer('tril', torch.tril(torch.ones(block_size, block_size))) #tril matrix

    def forward(self,x):
        B,T,C = x.shape #input shape  B=batch size , T=block size , C= embedding dimension
        k = self.key(x) #initinalizing the key
        q = self.query(x)#initinalizing the Query
        wei = (q @ k.transpose(-2,-1)) * C**-0.5
        wei = wei.masked_fill(self.tril[:T,:T] == 0, float('-inf'))
        wei = F.softmax(wei, dim=-1)
        v = self.value(x)
        out = wei @ v
        return out

class MultiHeadAttention(nn.Module):
    def __init__(self,num_heads,head_size):
        super().__init__()
        self.heads = nn.ModuleList([Head(block_size=8, head_size=head_size) for _ in range(num_heads)])
        self.proj = nn.Linear(head_size * num_heads, head_size)
    def forward(self,x):
        return self.proj(torch.cat([h(x) for h in self.heads], dim=-1))
    
