import sys
import torch
import networkx as nx
import networkx.algorithms.components.connected as nxacc
import networkx.algorithms.dag as nxadag
import numpy as np
import torch.nn as nn
import gc


def pearson_corr(x, y):
    xx = x - torch.mean(x)
    yy = y - torch.mean(y)

    return torch.sum(xx * yy) / (torch.norm(xx, 2) * torch.norm(yy, 2))


def load_ontology(file_name, gene2id_mapping):
    dG = nx.DiGraph()
    term_direct_gene_map = {}
    term_size_map = {}

    file_handle = open(file_name)

    gene_set = set()

    for line in file_handle:

        line = line.rstrip().split()

        if line[2] == 'default':
            dG.add_edge(line[0], line[1])
        else:
            if line[1] not in gene2id_mapping:
                continue

            if line[0] not in term_direct_gene_map:
                term_direct_gene_map[line[0]] = set()

            # Collect the "child" of genes at position 0
            term_direct_gene_map[line[0]].add(gene2id_mapping[line[1]])

            gene_set.add(line[1])

    file_handle.close()

    print('There are', len(gene_set), 'genes')

    for term in dG.nodes():

        term_gene_set = set()

        if term in term_direct_gene_map:
            term_gene_set = term_direct_gene_map[term]

        deslist = nxadag.descendants(dG, term)

        for child in deslist:
            if child in term_direct_gene_map:
                term_gene_set = term_gene_set | term_direct_gene_map[child]

        # jisoo
        if len(term_gene_set) == 0:
            print('There is empty terms, please delete term:', term)
            sys.exit(1)
        else:
            term_size_map[term] = len(term_gene_set)

    leaves = [n for n in dG.nodes if dG.in_degree(n) == 0]
    # leaves = [n for n,d in dG.in_degree() if d==0]

    uG = dG.to_undirected()
    connected_subG_list = list(nxacc.connected_components(uG))

    print('There are', len(leaves), 'roots:', leaves[0])
    print('There are', len(dG.nodes()), 'terms')
    print('There are', len(connected_subG_list), 'connected componenets')

    if len(leaves) > 1:
        print(
            'There are more than 1 root of ontology. Please use only one root.')
        sys.exit(1)
    if len(connected_subG_list) > 1:
        print('There are more than connected components. Please connect them.')
        sys.exit(1)

    return dG, leaves[0], term_size_map, term_direct_gene_map


def load_train_data(file_name, cell2id):
    feature = []
    label = []

    with open(file_name, 'r') as fi:
        for line in fi:
            tokens = line.strip().split(',')

            feature.append(cell2id[tokens[0]])
            label.append([float(tokens[2])])

    return feature, label


def prepare_predict_data(test_file, cell2id_mapping_file):
    # load mapping files
    cell2id_mapping = load_mapping(cell2id_mapping_file)
    # drug2id_mapping = load_mapping(drug2id_mapping_file)

    test_feature, test_label = load_train_data(test_file, cell2id_mapping)

    print('Total number of cell lines = %d' % len(cell2id_mapping))

    return (torch.Tensor(test_feature),
            torch.Tensor(test_label)), cell2id_mapping


def load_mapping(mapping_file):
    mapping = {}

    file_handle = open(mapping_file)

    for line in file_handle:
        line = line.rstrip().split()
        mapping[line[1]] = int(line[0])

    file_handle.close()

    return mapping


def prepare_train_data(train_file, test_file, cell2id_mapping_file):
    # load mapping files
    cell2id_mapping = load_mapping(cell2id_mapping_file)

    train_feature, train_label = load_train_data(train_file, cell2id_mapping)
    test_feature, test_label = load_train_data(test_file, cell2id_mapping)

    print('Total number of cell lines = %d' % len(cell2id_mapping))

    return (torch.Tensor(train_feature), torch.FloatTensor(train_label),
            torch.Tensor(test_feature),
            torch.FloatTensor(test_label)), cell2id_mapping


def build_input_vector(input_data, cell_features):
    
    #print("input_data:", input_data.size())
    #print("cell_features:", len(cell_features))
    genedim = len(cell_features[0])
    # drugdim = len(drug_features[0,:])
    feature = np.zeros((input_data.size()[0], genedim))

    for i in range(input_data.size()[0]):
        feature[i] = cell_features[int(input_data[i])]

    feature = torch.from_numpy(feature).float()
    return feature

def accuracy(output, label):
    total = output.shape[0]
    preds = torch.argmax(output, dim=1).T
    
    acc = torch.eq(preds, label).sum().item()/total
    
    return acc

def precision(output, labels):
    nums = torch.zeros(92)
    denoms = torch.zeros(92)
    preds = torch.argmax(output, dim=1).T
    
    for i in range(labels.shape[0]):
        pred = preds[i]
        label = labels[i]
        denoms[pred] += 1
        if pred == label:
            nums[pred] += 1
            
    for j in range(92):
        if denoms[j] == 0:
            denoms[j] = 1
            
    return torch.div(nums, denoms)

def recall(output, labels):
    nums = torch.zeros(92)
    denoms = torch.zeros(92)
    preds = torch.argmax(output, dim=1).T
    
    for i in range(labels.shape[0]):
        pred = preds[i]
        label = labels[i]
        denoms[label] += 1
        if pred == label:
            nums[pred] += 1
            
    for j in range(92):
        if denoms[j] == 0:
            denoms[j] = 1
            
    return torch.div(nums, denoms)

"""class DiceLoss(nn.Module):

    def __init__(self, weight=None, size_average=True):
        super(DiceLoss, self).__init__()

    def forward(self, inputs, targets, eps=1e-6):

        num_classes = inputs.shape[1]

        true_1_hot = torch.eye(num_classes)[targets.squeeze(1)]
        true_1_hot = true_1_hot.permute(0, 3, 1, 2).float()
        probas = F.softmax(inputs, dim=1)
        true_1_hot = true_1_hot.type(inputs.type())
        dims = (0,) + tuple(range(2, targets.ndimension()))
        intersection = torch.sum(probas * true_1_hot, dims)
        cardinality = torch.sum(probas + true_1_hot, dims)
        dice_loss = ((2. * intersection + eps) / (cardinality + eps)).mean()
        
        return (1 - dice_loss)"""

def get_weights(train_labels, test_labels):
    
    print("train_lables.shape:", train_labels.shape)
    print("test_lables.shape:", test_labels.shape)
    
    l1 = torch.flatten(train_labels).long()
    l2 = torch.flatten(test_labels).long()
    l = torch.cat([l1,l2])
    total = l.shape[0]
    
    weights = torch.zeros(92)
    
    #Count occurrences of each label
    for i in range(total):
        weights[l[i]] += 1
        
    #Inverse frequency of each label
    weights = torch.div(total, weights)
    
    #Square root
    weights = torch.sqrt(weights)
    
    #Normalize
    weights = torch.div(weights, torch.sum(weights).item())
    
    del l
    gc.collect()
    torch.cuda.empty_cache()
    
    print("Output:", weights.shape)
    
    return weights
