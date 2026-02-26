import math
from pathlib import Path

import numpy as np
import torch
import torch as th
import torch.nn as nn
import torch.nn.functional as F
from torch.nn import Parameter

from parms_setting import settings
from torch_geometric.utils import degree, dense_to_sparse

# 与 layer3.py 同目录，避免 ./xxx.pt 因 cwd 不同找不到文件
_TOOLS_DIR = Path(__file__).resolve().parent
from torch_geometric.nn import GCNConv
from torch_geometric.nn.conv import MessagePassing
from torch_geometric.utils import add_self_loops


def get_args():
    return settings()

if __name__ == "__main__":
    args = settings()
import torch
import torch.nn as nn
import torch.nn.functional as F

import torch
import torch.nn as nn
import torch.nn.functional as F

class HypergraphConv(nn.Module):
    def __init__(self, in_channels, out_channels, use_bias=True):
        super(HypergraphConv, self).__init__()
        self.linear = nn.Linear(in_channels, out_channels, bias=use_bias)

    def forward(self, x, H):
        """
        x: [N_nodes, in_channels] 节点特征
        H: [N_nodes, N_edges]     超图 incidence 矩阵（可以是稠密或稀疏）
        """
        # 节点度 Dv (N_nodes,)
        Dv = torch.sum(H, dim=1)  # 每个节点连接的超边数
        Dv_inv_sqrt = torch.pow(Dv + 1e-8, -0.5)  # 防止除零
        Dv_inv_sqrt = torch.diag(Dv_inv_sqrt)

        # 超边度 De (N_edges,)
        De = torch.sum(H, dim=0)  # 每个超边包含的节点数
        De_inv = torch.pow(De + 1e-8, -1.0)
        De_inv = torch.diag(De_inv)

        # H * De^-1 * H^T
        # step1: H @ De^-1
        H_ = torch.matmul(H, De_inv)         # [N_nodes, N_edges]
        # step2: (H @ De^-1) @ H^T
        HT = H.t()                           # [N_edges, N_nodes]
        HHT = torch.matmul(H_, HT)           # [N_nodes, N_nodes]

        # step3: Dv^-1/2 * HHT * Dv^-1/2
        DVHHT = torch.matmul(Dv_inv_sqrt, torch.matmul(HHT, Dv_inv_sqrt))

        # Linear transform + propagation
        x_proj = self.linear(x)              # [N_nodes, out_channels]
        out = torch.matmul(DVHHT, x_proj)    # [N_nodes, out_channels]
        return F.relu(out)



class MGCNA(nn.Module):
    def __init__(self, feature, hidden1, hidden2, decoder1):
        """
        :param args: Arguments object.
        """
        super(MGCNA, self).__init__()

        hidden1 = 128

        self.lin1 = nn.Linear(1578, hidden1)
        self.lin2 = nn.Linear(156, hidden1)
        self.lin3 = nn.Linear(640, 128)
        self.lin4 = nn.Linear(512, 128)

        # HGCN on gene hypergraph
        self.hgcn = HypergraphConv(in_channels=129, out_channels=128)


        #####
        self.embedding_dim = 256
        self.hidden_dim = 128
        self.v_dropout = 0.3
        num_fc_layers = 2
        self.gmlp = GMLP(
            self.embedding_dim,
            self.hidden_dim,
            self.v_dropout,
            output_dim=self.embedding_dim,
            num_fc_layers=num_fc_layers,
        )
        self.gcn = GCN(
            in_channels=512,
            hidden_channels=512
        )

        # decoder
        self.decoder1 = nn.Linear(hidden1 * 4, decoder1)
        self.decoder2 = nn.Linear(decoder1, 1)


    def forward(self, data, idx, contrastive=False):

        ##### work2
        # 1. Gene 超图 (Algorithm 1: Structure Optimization) ----------
        H_gene = data['H_gene']  # [N, G]
        enhanced_feats_gene1 = torch.load(_TOOLS_DIR / 'enhanced_feats_gene1.pt', map_location='cpu')
        z_gene_anchor = self.hgcn(enhanced_feats_gene1, H_gene)  # [N, hidden]

        h_gene_learn = data['H_gene_learn']
        enhanced_feats_gene2 = torch.load(_TOOLS_DIR / 'enhanced_feats_gene2.pt', map_location='cpu')
        z_gene_learn = self.hgcn(enhanced_feats_gene2, h_gene_learn)

        # 2. miRNA–drug 特征结构 (Algorithm 2: Structure Exploration) ----------
        enhanced_feats_md1 = torch.load(_TOOLS_DIR / 'enhanced_feats_md1.pt', map_location='cpu')
        z_md_view1 = self.hgcn(enhanced_feats_md1, data['H_md_view1'])
        enhanced_feats_md2 = torch.load(_TOOLS_DIR / 'enhanced_feats_md2.pt', map_location='cpu')
        z_md_view2 = self.hgcn(enhanced_feats_md2, data['H_md_view2'])

        if contrastive:
            # 用于对比学习阶段
            return z_gene_anchor, z_gene_learn, z_md_view1, z_md_view2


        H_g = torch.cat((z_gene_anchor, z_gene_learn), dim=1) #(1734, 256)
        H_md = torch.cat((z_md_view1, z_md_view2), dim=1)

        #####模态间对齐（Inter）与跨模态表示融合
        H_g = self.gmlp(H_g) #(1734,256)
        H_md = self.gmlp(H_md)
        all_feat = torch.cat((H_g, H_md), dim=1) #(1735,512)
        edge_index = data['A_d']['edges']  # bipartite edges
        z = self.gcn(all_feat, edge_index)
        z = self.lin4(z)

        entity1 = z[idx[0]]
        entity2 = z[1578+idx[1]]


        # multi-relationship modelling decoder
        add = entity1 + entity2
        product = entity1 * entity2
        concatenate = torch.cat((entity1, entity2), dim=1)

        feature = torch.cat((add, product, concatenate), dim=1) #(64,1024)

        log1 = F.relu(self.decoder1(feature))
        log = self.decoder2(log1)


        return log



class GMLP(nn.Module):
    def __init__(self, input_dim, hid_dim, dropout, output_dim=64, num_fc_layers=3, act_fn='gelu'):
        super(GMLP, self).__init__()
        self.fc_layers = nn.ModuleList()
        for i in range(num_fc_layers):
            in_features = input_dim if i == 0 else hid_dim
            out_features = hid_dim if i < num_fc_layers - 1 else output_dim
            self.fc_layers.append(nn.Linear(in_features, out_features))

        # Dictionary of activation functions
        activation_functions = {
            'relu': F.relu,
            'leaky_relu': F.leaky_relu,
            'gelu': F.gelu,
            'tanh': torch.tanh,
            'sigmoid': torch.sigmoid,
            'elu': F.elu,
            'selu': F.selu,
            'softplus': F.softplus
        }

        # Set the activation function
        if act_fn in activation_functions:
            self.act_fn = activation_functions[act_fn]
        else:
            raise ValueError(f"Unsupported activation function: {act_fn}")

        self.dropout = nn.Dropout(dropout)
        self.layernorm = nn.LayerNorm(hid_dim, eps=1e-6)

        self._init_weights()

    def _init_weights(self):
        for fc in self.fc_layers:
            nn.init.xavier_uniform_(fc.weight)
            nn.init.normal_(fc.bias, std=1e-6)

    def forward(self, x):
        for i, fc in enumerate(self.fc_layers):
            x = fc(x)
            if i < len(self.fc_layers) - 1:
                x = self.act_fn(x)
                x = self.layernorm(x)
                x = self.dropout(x)
        return x

class GCN(torch.nn.Module):
    def __init__(self, in_channels, hidden_channels, num_layers=3, aggr='add'):
        super(GCN, self).__init__()
        self.num_layer = num_layers
        self.convs = nn.ModuleList()
        self.convs.append(Base_gcn(in_channels, hidden_channels, aggr=aggr))

        for _ in range(num_layers - 1):
            self.convs.append(Base_gcn(hidden_channels, hidden_channels, aggr=aggr))

    def forward(self, x, edge_index):
        h = x
        for i, conv in enumerate(self.convs):
            h_new = conv(h, edge_index)
            h_new = F.relu(h_new)
            # 多层残差融合
            h = h + h_new
        return h

from torch_geometric.utils import remove_self_loops, degree
class Base_gcn(MessagePassing):
    def __init__( self, in_channels, out_channels, aggr="add"):
        super(Base_gcn, self).__init__(aggr=aggr)
        self.aggr = aggr
        self.lin = nn.Linear(in_channels, out_channels)

    def forward(self, x, edge_index, size=None):
        edge_index, _ = remove_self_loops(edge_index)
        x = self.lin(x)
        return self.propagate(edge_index, x=x)

    def message(self, x_j, edge_index, size):
        row, col = edge_index
        deg = degree(row, size[0], dtype=x_j.dtype)
        deg_inv_sqrt = deg.pow(-0.5)
        norm = deg_inv_sqrt[row] * deg_inv_sqrt[col]
        return norm.view(-1, 1) * x_j

    def update(self, aggr_out):
        return aggr_out

    def __repr(self):
        return "{}({},{})".format(
            self.__class__.__name__, self.in_channels, self.out_channels
        )
