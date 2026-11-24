with open ('input.txt','r',encoding='utf-8') as f:
    text=f.read()
print(f"Length of data is : {len(text)} chars")
print(text[:1000])
#here all the unique characters that uccurs in this text
chars=sorted(list(set(text)))
vocab_size=len(chars)
print('vocabulary:' + ''.join(chars))
print(f'vocabulary size: {vocab_size}')

#tokenize the input text
#create mapping from the characters to integers

stio={ch:i for i,ch in enumerate(chars)}
itos={i:ch for i,ch in enumerate(chars)}
encode=lambda s: [stio[c] for c in s] # encode take string and return list of integers
decode=lambda l: "".join([itos[i] for i in l]) # decode take list of integers and return string
print(encode("hello my name is abubakar"))
print (decode(encode("hello my name is abubakar")))

#lets now encode the  entire dataset and store it into the torch.Tensor

import torch
data=torch.tensor(encode(text),dtype=torch.long)
print (data.shape)
print (data[:1000])

#lets now split up the data into train test split
n=int(0.9*len(data))#first 90% will be training data and the last 10% will be validation data
train_data=data[:n]
val_data=data[n:]

block_size=8
print(train_data[:block_size+1]) # for the first example we take first 9 chars the first 8 are inputs and the 9th is the output

x=train_data[:block_size]
y=train_data[1:block_size+1]
for t in range (block_size):
    context=x[:t+1]
    target=y[t]
    print(f'when input is {context} the target is: {target}')

torch.manual_seed(1337)
batch_size=4 #how many independent sequences we process in parallel 
block_size=8 #maximum context length for predictions

def get_batch(split):
    data=train_data if split=='train' else val_data
    ix=torch.randint(len(data) - block_size,(batch_size,))
    x=torch.stack([data[i:i+block_size] for i in ix])
    y=torch.stack([data[i+1:i+block_size+1]for i in ix])
    return x,y
xb,yb=get_batch('train')
print('inputs:')
print(xb.shape)
print(xb)
print('targets:')
print(yb.shape)
print(yb)

print('\n--------\n')

for b in range(batch_size):
    for t in range(block_size):
        context=xb[b, :t+1]
        target=yb[b, t]
        print (f'when input is {context} \nThe target is: {target}')


import torch.nn as nn
from torch.nn import functional as F
torch.manual_seed(1337)

class BigramLanguageModel(nn.Module):
    def __init__(self,vocab_size):
        super().__init__()
        #each token directly reads the off the the logits for the next token from alookup table 
        self.token_embedding_table=nn.Embedding(vocab_size,vocab_size)
    def forward (self,idx,targets=None):
        logits=self.token_embedding_table(idx)# (B,T,C)
        if targets is None:
            loss=None
        else:
            B,T,C=logits.shape
            logits=logits.view(B*T,C)
            targets=targets.view(B*T)
            loss=F.cross_entropy(logits,targets)    
        return logits,loss


    def generation(self,idx,max_new_tokens):
        #idx is (B,T) array on indices in current context
        for _ in range(max_new_tokens):
            #get predictions
            logits,loss=self(idx)
            #focus on the last time step 
            logits=logits[:, -1, :] # becomes (B,C)
            #get the probabilities
            probs=F.softmax(logits,dim=-1) # (B,C)
            #sample from the distribution
            idx_next=torch.multinomial(probs,num_samples=1) #(B,1)
            #append sampled token to the idx
            idx = torch.cat((idx,idx_next),dim=1) # (B,T+1)
        return idx

   
m=BigramLanguageModel(vocab_size)
logits,loss=m(xb,yb)
print(loss)
idx=torch.zeros((1,1),dtype=torch.long)
print("Genartetion : ")
print(decode(m.generation(idx,max_new_tokens=100)[0].tolist()))

#create pytorch object
optimizer=torch.optim.AdamW(m.parameters(),lr=1e-3) 

batch_size=32
for steps in range (1000):
    #sample a batch of data
    xb,yb=get_batch('train')
    #evaluate the loss
    logits,loss=m(xb,yb)
    optimizer.zero_grad(set_to_none=True)
    loss.backward()
    optimizer.step()
    print(f'step {steps}: loss {loss.item()}')