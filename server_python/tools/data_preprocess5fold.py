from scipy.sparse import block_diag
from torch_geometric.data import Data
from torch.utils.data import Dataset, DataLoader
import numpy as np
import torch
import torch as th
import scipy.sparse as sp
import pandas as pd
import os
from pathlib import Path

# 数据目录：与当前脚本同级的 data（即 tools/data），保证任意 cwd 下都能找到
_TOOLS_DIR = Path(__file__).resolve().parent
DATA_DIR = _TOOLS_DIR / 'data'
BASE_DIR = _TOOLS_DIR.parent

class Data_class(Dataset):

    def __init__(self, triple):
        self.entity1 = triple[:, 0]
        self.entity2 = triple[:, 1]
        self.label = triple[:, 2]

    def __len__(self):
        return len(self.label)

    def __getitem__(self, index):

        return self.label[index], (self.entity1[index], self.entity2[index])


def load_data(args, test_ratio=0.2):
    """Read data from path, convert data into loader, return features and adjacency"""
    # read data
    print('Loading {0} seed{1} dataset...'.format(args.pos_sample, args.seed))  #
    positive = np.loadtxt(args.pos_sample, dtype=np.int64)   # pos_pair 8720, 2
    # print("postive:",positive.shape)

    #sample postive
    link_size = int(positive.shape[0])
    np.random.seed(args.seed)
    np.random.shuffle(positive)
    positive = positive[:link_size]

    # sample negative
    negative_all = np.loadtxt(args.neg_sample, dtype=np.int64)  # neg_pair 237448, 2
    # print("negative:", negative_all.shape)
    np.random.shuffle(negative_all)
    negative = np.asarray(negative_all[:positive.shape[0]])  # equal negative samples to positive samples
    print("positive examples: %d, negative examples: %d." % (positive.shape[0], negative.shape[0]))  #


    test_size = int(test_ratio * positive.shape[0]) # test number  1744
    print("test_number:",test_size)

    positive = np.concatenate([positive, np.ones(positive.shape[0], dtype=np.int64).reshape(positive.shape[0], 1)], axis=1) # 8720,3
    negative = np.concatenate([negative, np.zeros(negative.shape[0], dtype=np.int64).reshape(negative.shape[0], 1)], axis=1) # 8720,3
    # negative_all = np.concatenate([negative_all, np.zeros(negative_all.shape[0], dtype=np.int64).reshape(negative_all.shape[0], 1)], axis=1) #90537,3
    print("positive_negative: ",positive.shape, negative.shape)  # (8720, 3) (8720, 3)
    all_data = np.vstack((positive, negative))  # 形状: [2*link_size, 3]



    train_data = np.vstack((positive[: -test_size], negative[: -test_size])) # 13952, 2
    test_data = np.vstack((positive[-test_size:], negative[-test_size:]))    # 3488, 2
    print("data: ",train_data.shape,test_data.shape)

    # build data loader
    params = {'batch_size': args.batch, 'shuffle': True, 'num_workers': args.workers, 'drop_last': True}

    training_set = Data_class(train_data)
    train_loader = DataLoader(training_set, **params)
    print(train_loader)

    test_set = Data_class(test_data)
    test_loader = DataLoader(test_set, **params)
    print(test_loader)


    # build multiple view
    dataset = dict()
    # 节点特征
    "miRNA sequence sim"
    # mm_s_matrix = np.loadtxt(DATA_DIR / 'miRNA_seq_sim2.txt')
    mm_s_matrix = np.load(
        str(DATA_DIR / "miRNA_seq_sim2_gip.npz")
    )["mm_s_matrix"]

    mm_s_edge_index = mm_s_matrix.nonzero() # construct view non_zero index
    mm_s_edge_index = torch.tensor(np.vstack((mm_s_edge_index[0], mm_s_edge_index[1])), dtype=torch.long) # edge index
    dataset['mm_s'] = {'data_matrix': mm_s_matrix, 'edges': mm_s_edge_index}
    "drug fingerprint sim"
    dd_f_matrix = np.loadtxt(DATA_DIR / 'drug_smiles_sim2.txt')
    dd_f_edge_index = dd_f_matrix.nonzero()  # construct view non_zero index
    dd_f_edge_index = torch.tensor(np.vstack((dd_f_edge_index[0], dd_f_edge_index[1])), dtype=torch.long)  # edge index
    dataset['dd_f'] = {'data_matrix': dd_f_matrix, 'edges': dd_f_edge_index}

    "miRNA-drug sim"
    # m_d_matrix = np.loadtxt(DATA_DIR / 'integrated_similarity_matrix_gip.txt')
    m_d_matrix = np.load(
        str(DATA_DIR / "integrated_similarity_matrix_gip.npz")
    )["integrated_matrix"]

    m_d_edge_index = m_d_matrix.nonzero()  # construct view non_zero index
    m_d_edge_index = torch.tensor(np.vstack((m_d_edge_index[0], m_d_edge_index[1])), dtype=torch.long)  # edge index
    dataset['A_d'] = {'data_matrix': m_d_matrix, 'edges': m_d_edge_index}


    # H_gene = np.loadtxt(DATA_DIR / 'H_gene.txt')
    data = np.load(str(DATA_DIR / "H_gene_top500.npz"))
    H_gene = data["H_gene"]
    H_gene = torch.tensor(H_gene, dtype=torch.float32)
    dataset['H_gene'] = H_gene

    x_d = dataset['dd_f']['data_matrix']  # (156,156) #drug finger
    x_m = dataset['mm_s']['data_matrix']  # (1578,1578) #miRNA sequence
    x_m = torch.tensor(x_m, dtype=torch.float32)
    x_d = torch.tensor(x_d, dtype=torch.float32)
    linear_d = torch.nn.Linear(x_d.shape[1], 128) # 156 → 128
    linear_m = torch.nn.Linear(x_m.shape[1], 128)  # 1578 → 128
    x_d = linear_d(x_d)  # shape: (156, 128)
    x_m = linear_m(x_m)  # shape: (1578, 128)
    x = torch.cat([x_m, x_d], dim=0)  # (1734, 128)

    H_md_init1 = build_kNN_hypergraph(x)
    H_md_init2 = hypergraph_diffusion(H_md_init1)

    # 生成 enhanced 特征并保存到 tools 目录，供 layer3.py 加载（路径与 layer3 的 _TOOLS_DIR 一致）
    # enhanced_feats_gene1 = hypergraph_geodesic_simple(x, H_gene)
    # torch.save(enhanced_feats_gene1, _TOOLS_DIR / 'enhanced_feats_gene1.pt')
    h_gene_learn = hypergraph_diffusion(H_gene)
    h_gene_learn = h_gene_learn.clone().detach().to(torch.float32) if isinstance(h_gene_learn, torch.Tensor) else torch.tensor(h_gene_learn, dtype=torch.float32)
    dataset['H_gene_learn'] = h_gene_learn

    # enhanced_feats_gene2 = hypergraph_geodesic_simple(x, h_gene_learn)
    # torch.save(enhanced_feats_gene2, _TOOLS_DIR / 'enhanced_feats_gene2.pt')

    # enhanced_feats_md1 = hypergraph_geodesic_simple(x, H_md_init1)
    # torch.save(enhanced_feats_md1, _TOOLS_DIR / 'enhanced_feats_md1.pt')
    # enhanced_feats_md2 = hypergraph_geodesic_simple(x, H_md_init2)
    # torch.save(enhanced_feats_md2, _TOOLS_DIR / 'enhanced_feats_md2.pt')

    dataset['H_md_view1'] = H_md_init1
    dataset['H_md_view2'] = H_md_init2

    print('Loading finished!')
    return dataset,  all_data



def build_kNN_hypergraph(X: torch.Tensor, k: int = 10, metric: str = 'cosine') -> torch.Tensor:
    """
    基于节点特征构造 kNN 超图
    Args:
        X: [N, d] 节点特征
        k: 每个节点选取的近邻数量（超边大小）
        metric: 'cosine' 或 'euclidean'
    Returns:
        H: [N, E] 超图 incidence matrix，E = N（每个节点一条超边）
    """
    N = X.shape[0]

    # ---------- 1. 计算相似度矩阵 ----------
    if metric == 'cosine':
        X_norm = torch.nn.functional.normalize(X, p=2, dim=1)
        sim = torch.matmul(X_norm, X_norm.t())   # [N, N]
    elif metric == 'euclidean':
        dist = torch.cdist(X, X, p=2)
        sim = -dist  # 越小越相似
    else:
        raise ValueError("metric must be 'cosine' or 'euclidean'")

    # ---------- 2. 选出每个节点的 top-k 近邻 ----------
    knn_idx = torch.topk(sim, k=k+1, dim=1).indices  # 包含自身

    # ---------- 3. 构造 incidence matrix ----------
    # 每个节点 i 作为一条超边，其成员是 i 的 kNN
    H = torch.zeros(N, N, dtype=torch.float32, device=X.device)  # N 条超边
    for i in range(N):
        neighbors = knn_idx[i]
        H[neighbors, i] = 1.0  # 第 i 条超边包含这些邻居

    return H



@torch.no_grad()
def hypergraph_geodesic_simple(node_feats, hyper_adj_matrix, device='cuda', beta=1.0):
    """
    固定特征增强函数（仅预处理阶段使用，不参与梯度计算）
    基于超图邻居的简化测地线扩散特征。
    Args:
        node_feats: 节点特征张量 [N, d]
        hyper_adj_matrix: 超邻接矩阵 [N, M]（N=节点数，M=超边数，0-1张量/数组，A[i][e]=1表示节点i属于超边e）
        device: 'cuda' or 'cpu'
    Returns:
        enhanced_feats: 增强后的节点特征 [N, d]
    """
    node_feats = node_feats.to(device)
    hyper_adj_matrix = torch.tensor(hyper_adj_matrix, dtype=torch.bool, device=device)  # 转为bool型便于判断节点是否属于超边
    N = node_feats.size(0)
    M = hyper_adj_matrix.size(1)  # 超边数M

    # === Step 0. 构造超邻居结构 ===
    hyper_edge_nodes = []  # hyper_edge_nodes[e] = 超边e包含的所有节点索引（列表）
    for e in range(M):
        # 找到超边e对应的所有节点（超邻接矩阵第e列值为1的行索引）
        nodes_in_edge = torch.nonzero(hyper_adj_matrix[:, e], as_tuple=True)[0].tolist()
        hyper_edge_nodes.append(nodes_in_edge)

    # 0.2 再推导“每个节点的超邻居集合”（对应论文2.1节邻域N(i)的超图扩展）
    hyper_neighbors = [[] for _ in range(N)]  # hyper_neighbors[i] = 节点i的超邻居列表
    for i in range(N):
        # 步骤1：找到节点i所属的所有超边（超邻接矩阵第i行值为1的列索引）
        edges_contain_i = torch.nonzero(hyper_adj_matrix[i, :], as_tuple=True)[0].tolist()
        # 步骤2：收集这些超边中的所有节点，作为候选超邻居
        candidate_neighbors = set()
        for e in edges_contain_i:
            candidate_neighbors.update(hyper_edge_nodes[e])
        # 步骤3：剔除节点i自身（超邻居不包含自己），得到最终超邻居列表
        hyper_neighbors[i] = [j for j in candidate_neighbors if j != i]

    # === Step 1. 初始化度与势函数ρ(x) ===
    deg = hyper_adj_matrix.sum(dim=1).float()  # 节点超度
    # rho = 1.0 / (deg + 1e-6)
    # 若想让高度节点传播慢，则改为 rho = deg + 1e-6
    # rho = (deg + 1e-6) # 4fold 0.5
    rho = (deg / deg.mean()) ** beta



    # Step 2. 初始化距离并开始迭代
    dist = torch.zeros(N, device=device)
    max_iter = 100  # 工程上的迭代上限，避免无限循环（论文要求“迭代至收敛”）
    conv_threshold = 1e-3  # 收敛阈值（对应论文“稳态解”的判断标准）
    for _ in range(max_iter):
        dist_new = torch.zeros_like(dist)
        for i in range(N):
            nbors = hyper_neighbors[i]
            if len(nbors) > 0:
                # 论文Eq.(9)：f(i) = min_{j∈N(i)} {f(j)+1}（超图中N(i)为超邻居列表）
                nbor_idx = torch.tensor(nbors, dtype=torch.long, device=device)
                nbor_dists = dist[nbor_idx]
                # 更新公式：f(i) = min_{j∈N(i)}(f(j) + ρ(i))
                dist_new[i] = nbor_dists.min() + rho[i]  # 最小距离 + 1
            else:
                # 论文115节实验设定：无邻域节点时距离设为极大值（1e6），表示无可达路径
                dist_new[i] = 1e6  # 无超邻居时距离设为极大值

        # 收敛判断
        if torch.abs(dist_new - dist).max() < conv_threshold:
            dist = dist_new
            break
        dist = dist_new

    # Step 3. 特征增强（拼接测地线距离特征）
    dist_feat = dist.unsqueeze(1)  # [N, 1]
    enhanced_feats = torch.concat((node_feats, dist_feat), dim=1) #0.9636
    # enhanced_feats = dist_feat * 0.1 + node_feats * 0.9  #0.9637

    return enhanced_feats


def hypergraph_diffusion(H, k_diff=2, alpha=0.5, k_neighbors=10):
    """
    Perform hypergraph structure diffusion (S -> S_diff)
    and rebuild shifted hypergraph H' using kNN.

    Parameters:
        H: (N, G) hypergraph incidence matrix
        k_diff: diffusion steps
        alpha: residual coefficient
        k_neighbors: number of neighbors for reconstructing H'

    Returns:
        S_diff: (N, N) diffused structure matrix
        H_prime: (N, N) reconstructed shifted hypergraph incidence matrix
    """

    # ----- 1. Degree matrices -----
    Dv = H.sum(dim=1)                             # (N,)
    Dv_inv_sqrt = torch.diag(1.0 / torch.sqrt(Dv + 1e-8))

    De = H.sum(dim=0)                             # (G,)
    De_inv = torch.diag(1.0 / (De + 1e-8))

    # hyperedge weights
    W = torch.eye(H.size(1), device=H.device)     # (G, G)

    # ----- 2. Node–node association matrix S = H W De^{-1} H^T -----
    S = H @ De_inv @ H.t()                        # (N, N)

    # ----- 3. Symmetric normalized propagation matrix Θ -----
    Theta = Dv_inv_sqrt @ S @ Dv_inv_sqrt         # (N, N)

    # ----- 4. k-step symmetric residual diffusion -----
    S_diff = S.clone()
    for _ in range(k_diff):
        S_diff = alpha * S + (1 - alpha) * (Theta @ S_diff @ Theta)

    # ----- 5. Reconstruct shifted hypergraph H' using kNN -----
    N = S_diff.size(0)
    H_prime = torch.zeros((N, N), device=S_diff.device)

    # for each node, pick top-k neighbors
    topk_idx = torch.topk(S_diff, k=k_neighbors, dim=1).indices

    for i in range(N):
        H_prime[i, topk_idx[i]] = 1
        H_prime[i, i] = 1  # include self-loop if needed

    return H_prime
