import numpy as np
import time
import torch
import pickle
from scipy import spatial
import os
from utils import progress_bar
from pathlib import Path
from collections import OrderedDict
from torch.utils.data import Dataset
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import torchvision
import torchvision.transforms as transforms
from PIL import Image
import sys, getopt
from torchvision import models as t_models
class B_Block(nn.Module):
    def __init__(self, inlayer, outlayer, filter_size = 3, first_stride = 1, padding = 1, downsample_net = None):
        super(B_Block, self).__init__()
        self.conv1 = nn.Conv2d(inlayer, outlayer, filter_size, first_stride, padding)
        self.conv1_bn = nn.BatchNorm2d(outlayer)
        self.conv2 = nn.Conv2d(outlayer, outlayer, filter_size, 1, padding)
        self.conv2_bn = nn.BatchNorm2d(outlayer)
        self.downsample_net = downsample_net

    def forward(self,x):
        out = self.conv1(x)
        if self.downsample_net:
            x = self.downsample_net(x)

        out = self.conv1_bn(out)
        out = F.relu(out)
        out = self.conv2(out)
        out = self.conv2_bn(out)
        out = x + out

        return out


class ResNet(nn.Module):
    def __init__(self):
        super(ResNet, self).__init__()
        self.inputplane = 32
        self.conv1 = nn.Conv2d(3, 32, 3, 1, 1)
        self.conv1_bn = nn.BatchNorm2d(32)
        self.conv1_dropout = nn.Dropout(0.2)
        self.bb1 = self.block_layer(32, 2, 1)
        self.bb2 = self.block_layer(64, 4, 2)
        self.bb3 = self.block_layer(128, 4, 2)
        self.bb4 = self.block_layer(256, 2, 2)
        self.max_pol = nn.MaxPool2d(4, 1)
        self.fc = nn.Linear(256, 128)
        self.fc1 = nn.Linear(128, 100)
        self.fc2 = nn.Linear(256, 100)



    def block_layer(self, out_layers, num_layer, stride):
        downsample_net = None
        if stride != 1:
            downsample_net = nn.Sequential(nn.Conv2d(self.inputplane, out_layers, kernel_size=3, stride=stride, padding = 1, bias=False), nn.BatchNorm2d(out_layers),)
        block = []
        block.append(B_Block(self.inputplane, out_layers, 3, stride, 1, downsample_net))
        self.inputplane = out_layers
        for i in range(1, num_layer):
            block.append(B_Block(self.inputplane, out_layers))
        return nn.Sequential(*block)


    def forward(self,x):
        x = self.conv1(x)
        x = self.conv1_bn(x)
        x = F.relu(x)
        x = self.conv1_dropout(x)
        x = self.bb1(x)
        x = self.bb2(x)
        x = self.bb3(x)
        x = self.bb4(x)
        x = self.max_pol(x)
        x = x.view(x.size(0), -1)
        #x = self.fc(x)
        #x = self.fc1(F.relu(x))
        #x = self.fc(x)
        x = self.fc2(x)
        return x
def choicelist(number, end):
    ret = list(range(number)) + list(range(number + 1, end))
    return ret

class TripleDataset(Dataset):
    def __init__(self, triplelist, root_dir,train, transform=None):
        self.triplelist = pickle.load(open(triplelist,'rb'))
        self.root_dir = root_dir
        self.transform = transform
        self.train = train

    def __len__(self):
        return len(self.triplelist)

    def __getitem__(self, idx):
        if self.train :
            label = self.triplelist[idx][0].split('_')[0]
            subdir = label
            query_image_path = self.root_dir + '/'+ subdir + '/images/' + self.triplelist[idx][0]
            positive_image_path = self.root_dir + '/'+ subdir + '/images/' + self.triplelist[idx][1]
            negative_label = self.triplelist[idx][2].split('_')[0]
            subdir = negative_label
            negative_image_path = self.root_dir + '/'+ subdir + '/images/' + self.triplelist[idx][2]
            positive_image = Image.open(positive_image_path).convert('RGB')
            query_image = Image.open(query_image_path).convert('RGB')
            negative_image = Image.open(negative_image_path).convert('RGB')
            sample = {'positive_image': positive_image, 'query_image': query_image, 'negative_image' : negative_image}
            if self.transform:
                for i,v in sample.items():
                    sample[i] = self.transform(v)
            return sample, self.triplelist[idx]
        else:
            query_image_path = root_dir + self.triplelist[idx]
            query_image = Image.open(query_image_path).convert('RGB')
            if self.transform:
                sample = self.transform(query_image)
            return sample, self.triplelist[idx]

def TestGenerator():
    root = "data/tiny-imagenet-200/val/images"
    image_list = os.listdir(root)
    print(image_list[0:10])
    print(len(image_list))
    with open('data/tiny-imagenet-200/val/val_annotations.txt', 'r') as f:
        class_lable = []
        lines =  f.readlines()
        for line in lines:
            tmp = line.rstrip().split()
            class_lable.append(tmp[1])
        print(class_lable[0:10])
        with open('testlist_label.pkl', 'wb') as f:
            pickle.dump(class_lable, f)

    with open('testlist.pkl', 'wb') as f:
        pickle.dump(image_list, f)


def TripleGenerator():
    num_ep = 40
    for i in range(num_ep):
        root = "data/tiny-imagenet-200/train"
        label_list = os.listdir(root)
        number_label = len(label_list)
        triple_list = []
        for ind, label in enumerate(label_list):
            path = root + '/' + label + '/'+ 'images'
            image_list = os.listdir(path)
            number_image = len(image_list)
            for image_inx, image in enumerate(image_list):
                query_image = image
                positive_image = image_list[np.random.choice(number_image)]
                negative_index = np.random.choice(choicelist(ind, number_label))
                negative_path = root + '/' + label_list[negative_index] + '/'+ 'images'
                negative_image_list = os.listdir(negative_path)
                number_negative_image = len(negative_image_list)
                negative_image = negative_image_list[np.random.choice(number_negative_image)]
                triple_list.append((query_image,positive_image,negative_image))
        print(triple_list[0])
        print(len(triple_list))
        with open('triplelist' + str(i) + '.pkl', 'wb') as f:
            pickle.dump(triple_list, f)

class LimitedSizeDict(OrderedDict):
  def __init__(self, *args, **kwds):
    self.size_limit = kwds.pop("size_limit", None)
    OrderedDict.__init__(self, *args, **kwds)
    self._check_size_limit()

  def __setitem__(self, key, value):
    OrderedDict.__setitem__(self, key, value)
    self._check_size_limit()

  def _check_size_limit(self):
    if self.size_limit is not None:
      while len(self) > self.size_limit:
        self.popitem(last=False)
#Hyper parameters
embedding_size =4096
def main(pretrain,argv):
    batch_size = 0
    try:
        opts,args = getopt.getopt(argv, "hb", ["batch_size="])
    except getopt.GetoptError:
        print('test.py -batchsize')
        sys.exit(2)
    for opt. arg in opts:
        if opt in ('-b', "--batch_size"):
            batch_size = arg
    print(batch_size)
    transform = transforms.Compose(
        [transforms.RandomHorizontalFlip(),
         transforms.RandomCrop(32,4),
         transforms.RandomRotation(20),
         transforms.ToTensor(),
         transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))])

    if pretrain == True:
        net = t_models.resnet18(pretrained = True)
        num_inp = net.fc.in_features
        net.fc = nn.Linear(num_inp, embedding_size)
        transform = transforms.Compose(
        [transforms.Resize((224,224)),
         transforms.RandomHorizontalFlip(),
         transforms.RandomCrop(224, 4),
         transforms.RandomRotation(20),
         transforms.ToTensor(),
         transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))])
    else:
        net = ResNet()
    model_file = Path("model.pt")
    if model_file.is_file():
        net.load_state_dict(torch.load("model.pt"))

    #freeze parameters
    child_counter = 0
    for child in net.children():
        if child_counter not in  [7,8,9]:
            for param in child.parameters():
                param.requires_grad = False
            print("child",child_counter,"was frozen")
        elif child_counter == 7:
            children_of_child_counter = 0
            for children_of_child in child.children():
                if children_of_child_counter == 0:
                    for param in children_of_child.parameters():
                        param.requires_grad = False
                    print('child ', children_of_child_counter, 'of child', child_counter, ' was frozen')
                children_of_child_counter += 1
        child_counter += 1

    criterion = nn.TripletMarginLoss()
    optimizer = optim.Adam(net.parameters(), lr = 0.001)
    if torch.cuda.is_available():
        print('cuda')
        device = torch.device('cuda:0')
    else:
        print('cpu')
        device = torch.device('cpu')
    print(device)
    net.to(device)
    time1 = time.time()
    for epoch in range(40):  # loop over the dataset multiple times
        net.train()
        pickle_file = 'triplelist' + str(epoch) + '.pkl'

        trainset = TripleDataset(triplelist = pickle_file,root_dir = 'tiny-imagenet-200/train', train = 1, transform = transform)
        trainloader = torch.utils.data.DataLoader(trainset, batch_size = batch_size,
                                                  shuffle=True, num_workers=10)
        #mage_dict = LimitedSizeDict(size_limit= 5000)

        time2 = time.time()
        running_loss = 0.0
        train_embedding = None
        train_image_name = None
        train_embedding = []
        train_image_name = []
        if (epoch > 6):
            for group in optimizer.param_groups:
                for p in group['params']:
                    state = optimizer.state[p]
                    if ('step' in state and state['step'] >= 1024):
                        state['step'] = 1000
        bar_counter = 0
        for i, data in enumerate(trainloader, 0):
            # get the inputs
            #print(len(image_dict))
            bar_counter = i
            data_i , label = data
            positive_image = data_i['positive_image']
            query_image = data_i['query_image']
            negative_image =data_i['negative_image']
            positive_image = positive_image.to(device)
            negative_image = negative_image.to(device)
            query_image = query_image.to(device)
            # zero the parameter gradients
            optimizer.zero_grad()

            # forward + backward + optimize
            query_output = None
            positive_output = None
            negative_output = None
            query_output = net(query_image)
            positive_output = net(positive_image)
            negative_output =  net(negative_image)
            if (epoch + 1) >= 2 and (epoch + 1)% 2 == 0 :
                for each_label in label:
                    train_image_name.append(each_label[0])
                train_embedding.append(query_output)
            loss = criterion(query_output, positive_output, negative_output)
            loss.backward()
            optimizer.step()

            # print statistics
            running_loss += loss.item()
            if i % 1000 == 999:  # print every 2000 mini-batches
                print('[%d, %5d] loss: %.3f' %
                      (epoch + 1, i + 1, running_loss / 999))
                running_loss = 0.0
                #progress_bar(i/10 ,10000)
                print('100 batch time: ', time.time() - time2)
        torch.save(net.state_dict(), "model.pt")
        if (epoch + 1) >= 1 and (epoch + 1) % 1 == 0:
            np.asanyarray(train_embedding)
            with open('embedding.pkl', 'wb') as f:
                np.save(f, train_embedding)
            with open('train_image_name.pkl', 'wb') as f:
                pickle.dump(train_image_name, f)
            test(net, device,'embedding.pkl', 'train_image_name.pkl')



    print('Total time: ', time.time() -time1)


    print('Finished Training')
    print('Start Testing')
    ####testing###########
    #test(net, device, train_embedding, train_image_name)

def test(net,device, embedding_array,train_image_name):
    embedding_array = np.load(embedding_array)
    embedding_array = embedding_array.flatten()
    print(embedding_array.shape)
    train_image_name = pickle.load(open(train_image_name, 'rb'))
    print(len(train_image_name))
    time3 = time.time()
    net.eval()
    testset = TripleDataset(triple_list = pickle_file, root_dir = 'tiny-imagenet-200/val/images', train = 0,
                             transform = transform)
    testloader = torch.utils.data.DataLoader(testset, batch_size= 32,shuffle=True, num_workers=8)
    labels_list = []
    labels_list = pickle.load(open("testlist_label.pkl", 'rb'))
    #tree_array = np.vstack((outputs, embedding_array))
    tree = spatial.KDTree(embedding_array)
    total_acc = 0
    train_image_name_counter = 0
    for i, data in enumerate(testloader, 0):
        # get the inputs
        accuracy = 0
        inputs, labels = data
        print(inputs.shape)
        print(labels.shape)
        inputs, labels = inputs.to(device), labels.to(device)
        # zero the parameter gradients
       # optimizer.zero_grad()
        # forward + backward + optimize
        outputs = net(inputs)
        dis, index = tree.query(outputs, k =30 )

        true_label = label_list[i]
        counter = 0
        for ind, group in enumerate(index):
            for gourp_ind, image in enumerate(group):
                train_image_name_counter += 1
                train_label = train_image_name[image].split('_')[0]
                if train_label == true_label:
                    counter +=1
        print(train_image_name_counter)
        accuracy = counter/30
        total_acc += accuracy

    print("average acc of testing: ", total_acc/100)
    print('One time: ', time.time()- time3)

main(True,sys.argv[1:])
