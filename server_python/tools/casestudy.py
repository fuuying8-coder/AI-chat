import copy
import time
import os
import torch
import numpy as np
import torch.nn as nn
import matplotlib.pyplot as plt
import seaborn as sns

from torch_geometric.data import DataLoader

from data_preprocess5fold import load_data
from layer3 import MGCNA
from sklearn.metrics import precision_recall_curve, roc_auc_score, roc_curve, average_precision_score, f1_score, auc
from sklearn.model_selection import KFold, train_test_split
from torch.utils.data import Dataset, DataLoader
import torch.nn.functional as F


def info_nce_loss(z1, z2, tau=0.5):
    """
    对比学习损失函数 (InfoNCE Loss)
    z1, z2: [N, d] 两个视图的节点表示
    tau: 温度参数，默认为0.5
    """
    z1 = F.normalize(z1, dim=1)
    z2 = F.normalize(z2, dim=1)
    N = z1.size(0)

    sim_matrix = torch.matmul(z1, z2.T) / tau
    labels = torch.arange(N).long().cuda()
    loss = F.cross_entropy(sim_matrix, labels)
    return loss

class Data_class(Dataset):

    def __init__(self, triple):
        self.entity1 = triple[:, 0]
        self.entity2 = triple[:, 1]
        self.label = triple[:, 2]

    def __len__(self):
        return len(self.label)

    def __getitem__(self, index):

        return self.label[index], (self.entity1[index], self.entity2[index])



def train_model(dataset, all_data, args):
    kf = KFold(n_splits=5, shuffle=True, random_state=args.seed)  # 每次交叉验证随机划分


    best_models = []
    # 初始化存储每一折的最优结果
    best_fold_metrics = {
        'auc': [], 'aupr': [], 'f1': [], 'recall': [], 'specificity': [], 'accuracy': [], 'mcc': [],
        'fpr': [], 'tpr': [], 'precision': [], 'recall_curve': []
    }

    for fold, (train_idx, test_idx) in enumerate(kf.split(all_data), 1):
        print(f"\n===== Fold {fold} ======")
        train_data = all_data[train_idx]
        test_data = all_data[test_idx]

        # 数据加载器
        train_loader = DataLoader(Data_class(train_data), batch_size=args.batch, shuffle=True,
                                  num_workers=args.workers, drop_last=True)
        test_loader = DataLoader(Data_class(test_data), batch_size=args.batch, shuffle=False,
                                 num_workers=args.workers, drop_last=False)

        # 初始化模型和优化器
        model = MGCNA(feature=args.dimensions,
                      hidden1 = args.hidden1 ,
                      hidden2 = args.hidden2,
                      decoder1 = args.decoder1)
        optimizer = torch.optim.Adam(model.parameters(),
                                     lr=args.lr,
                                     weight_decay=args.weight_decay)
        m = torch.nn.Sigmoid()
        loss_fn = torch.nn.BCELoss()

        if args.cuda:
            model.to("cuda")

        # 初始化当前折的最优指标
        best_auc = 0.0
        best_model_wts = None
        best_epoch = 0

        current_best = {
            'auc': [], 'aupr': [], 'f1': [], 'recall': [], 'specificity': [], 'accuracy': [], 'mcc': [],
            'fpr': [], 'tpr': [], 'precision': [], 'recall_curve': []
        }

        for epoch in range(args.epochs):
            print(f'-------- Epoch {epoch + 1}/{args.epochs} --------')
            model.train()
            epoch_loss = 0.0
            y_pred_train = []
            y_label_train = []

            for i,(label, inp) in enumerate(train_loader):
                if args.cuda:
                    label = label.cuda()

                optimizer.zero_grad()

                # ====== 1. 对比学习阶段 (获取对比学习的表示) ======
                z_gene_anchor, z_gene_learn, z_md_view1, z_md_view2 = model(dataset, inp, contrastive=True)

                # 计算对比学习损失
                loss_contrast1 = info_nce_loss(z_gene_anchor, z_gene_learn, tau=0.5)  # loss1
                loss_contrast2 = info_nce_loss(z_md_view1, z_md_view2, tau=0.5)  # loss2

                # ====== 2. 下游预测 (miRNA-drug link) ======
                output = model(dataset, inp, contrastive=False)
                log = torch.squeeze(m(output))
                loss_bce = loss_fn(log, label.float())  # bceloss
                optimizer.zero_grad()  # 注意：每次迭代前需清空梯度
                
                # 总损失 = BCE损失 + 对比学习损失
                loss = loss_bce + 0.1 * loss_contrast1 + 0.5 * loss_contrast2
                # loss = loss_bce + 0.1 * loss_contrast1  # 可选：只使用loss1
                
                loss.backward()
                optimizer.step()

                # 统计信息
                epoch_loss += loss.item()
                y_label_train.extend(label.cpu().numpy())
                y_pred_train.extend(log.cpu().detach().numpy())

                # 每100个批次打印进度
                if i % 100 == 0:
                    print(
                        f'Epoch: {epoch + 1}/{args.epochs}, Batch: {i + 1}/{len(train_loader)}, '
                        f'Total Loss: {loss.item():.4f}, BCE Loss: {loss_bce.item():.4f}, '
                        f'Contrast1 Loss: {loss_contrast1.item():.4f}, Contrast2 Loss: {loss_contrast2.item():.4f}')


            # 计算训练集epoch的平均损失和训练集AUC
            avg_loss = epoch_loss / len(train_loader)
            train_auc = roc_auc_score(y_label_train, y_pred_train)

            print(f"Epoch {epoch + 1}/{args.epochs}, Train Loss: {avg_loss:.4f}, Train AUC: {train_auc:.4f}")

            # 释放GPU内存
            if hasattr(torch.cuda, 'empty_cache'):
                torch.cuda.empty_cache()

            # 每轮训练后测试
            metrics = test(model, test_loader, dataset, args)

            # 保存当前折的最优模型和指标
            if metrics['auc'] > best_auc:
                best_auc = metrics['auc']
                best_epoch = epoch + 1
                best_model_wts = copy.deepcopy(model.state_dict())
                current_best = metrics
                print(f"  → New best AUC: {best_auc:.4f} at epoch {best_epoch}")

        # 保存本折最佳模型权重
        if best_model_wts is not None:
            model_path = f'best_model_fold{fold}.pth'
            torch.save(best_model_wts, model_path)
            print(f"\n✓ Fold {fold} best model saved: {model_path} (AUC: {best_auc:.4f})")
            best_models.append(model_path)
        else:
            # 至少保存最后一个epoch的模型
            model_path = f'best_model_fold{fold}.pth'
            torch.save(model.state_dict(), model_path)
            print(f"\n✓ Fold {fold} model saved: {model_path} (AUC: {best_auc:.4f})")
            best_models.append(model_path)

        # for metric_name in best_fold_metrics.keys():
        #     best_fold_metrics[metric_name].append(best_metrics[metric_name])

        # 将这一折的结果添加到存储容器中
        for metric_name, metric_value in current_best.items():
            if metric_name in best_fold_metrics:
                best_fold_metrics[metric_name].append(metric_value)
        # best_fold_metrics.append(current_best)
        print(f"Fold {fold} best AUC: {best_auc:.4f}")

    # 计算平均指标
    print("\n===== Cross-validation summary =====")
    for metric in ['auc', 'aupr', 'f1', 'recall', 'specificity', 'accuracy', 'mcc']:
        if metric in best_fold_metrics:
            mean_val = np.mean(best_fold_metrics[metric])
            std_val = np.std(best_fold_metrics[metric])
            print(f"Mean {metric.upper()}: {mean_val:.4f} ± {std_val:.4f}")

    # 保存全局最佳模型（所有fold中AUC最高的）
    if len(best_fold_metrics['auc']) > 0:
        best_fold_index = np.argmax(best_fold_metrics['auc'])
        best_global_auc = best_fold_metrics['auc'][best_fold_index]
        best_global_model_path = best_models[best_fold_index]
        
        # 复制最佳模型为全局最佳模型
        import shutil
        global_best_path = 'best_model_global.pth'
        shutil.copy(best_global_model_path, global_best_path)
        
        print(f"\n✓ Global best model saved: {global_best_path} (Fold {best_fold_index + 1}, AUC: {best_global_auc:.4f})")

    return best_models, best_fold_metrics


from sklearn.metrics import accuracy_score, matthews_corrcoef, recall_score, confusion_matrix

def test(model, loader, dataset, args):
    m = torch.nn.Sigmoid()
    loss_node = torch.nn.BCELoss()

    model.eval()
    y_pred = []
    y_label = []

    with torch.no_grad():
        for i, (label, inp) in enumerate(loader):
            if args.cuda:
                label = label.cuda()

            output = model(dataset, inp)
            log = torch.squeeze(m(output))
            loss = loss_node(log, label.float())

            label_ids = label.to('cpu').numpy()
            y_label = y_label + label_ids.flatten().tolist()
            y_pred = y_pred + log.flatten().tolist()
            outputs = np.asarray([1 if i else 0 for i in (np.asarray(y_pred) >= 0.5)])


    # AUC
    fpr, tpr, auc_thresholds = roc_curve(y_label, y_pred)
    auc_score = auc(fpr, tpr)

    # AUCPR
    precision, recall, pr_threshods = precision_recall_curve(y_label, y_pred)
    aupr_score = auc(recall, precision)

    # 二值预测（>=0.5为正类）
    y_bin = np.asarray([1 if i >= 0.5 else 0 for i in y_pred])

    accuracy = accuracy_score(y_label, y_bin)
    mcc = matthews_corrcoef(y_label, y_bin)
    sensitivity = recall_score(y_label, y_bin)
    tn, fp, fn, tp = confusion_matrix(y_label, y_bin).ravel()
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    f1 = f1_score(y_label, y_bin)

    print('auroc_val: {:.4f}'.format(auc_score), 'auprc_val: {:.4f}'.format(aupr_score),
          'accuracy: {:.4f}'.format(accuracy), 'mcc: {:.4f}'.format(mcc),
          'sensitivity: {:.4f}'.format(sensitivity), 'specificity: {:.4f}'.format(specificity),
          'f1: {:.4f}'.format(f1))

    return {
        'auc': auc_score, 'aupr': aupr_score, 'f1': f1, 'recall': sensitivity,
        'specificity': specificity, 'accuracy': accuracy, 'mcc': mcc,
        'fpr': fpr, 'tpr': tpr, 'precision': precision, 'recall_curve': recall
    }


def predict_pairs(model, dataset, all_data, args, drug_id=5, top_k=25):
    """
    预测指定药物的所有未标记样本（label == 0）的关联得分，返回得分最高的top_k个miRNA。
    
    Args:
        model: 训练好的模型
        dataset: 数据集字典
        all_data: 所有数据，shape为 [N, 3]，其中第3列为label
        args: 参数对象
        drug_id: 药物ID（下标），默认为5（Docetaxel, DB01248）
        top_k: 返回前k个结果，默认为25
    
    Returns:
        top_pairs: 前top_k个(miRNA_id, drug_id)对
        top_scores: 对应的预测得分
    """
    model.eval()
    m = torch.nn.Sigmoid()

    # 所有未标记数据（label == 0）
    unlabeled_mask = all_data[:, 2] == 0
    unlabeled_data = all_data[unlabeled_mask]

    # 找出指定drug_id的所有未标记对
    drug_mask = unlabeled_data[:, 1] == drug_id
    drug_pairs = unlabeled_data[drug_mask]  # shape (?, 3)

    if len(drug_pairs) == 0:
        print(f"No unlabeled pairs found for drug_id {drug_id}.")
        return [], []

    scores = []
    pairs = []

    with torch.no_grad():
        batch_size = args.batch
        for i in range(0, len(drug_pairs), batch_size):
            batch = drug_pairs[i:i+batch_size]
            inp = (batch[:, 0], batch[:, 1])
            # 预测
            output = model(dataset, inp)
            prob = m(output).cpu().numpy()

            scores.extend(prob.flatten().tolist())
            pairs.extend([(int(a), int(b)) for a, b in zip(batch[:, 0], batch[:, 1])])

    # 取 top_k
    top_indices = np.argsort(scores)[::-1][:top_k]
    top_pairs = [pairs[i] for i in top_indices]
    top_scores = [scores[i] for i in top_indices]

    print(f"\nTop {top_k} predicted miRNAs associated with drug_id {drug_id}:")
    print("-" * 60)
    for idx, (pair, score) in enumerate(zip(top_pairs, top_scores), 1):
        print(f"{idx:2d}. miRNA ID: {pair[0]:4d}, Drug ID: {pair[1]:3d}, Score: {score:.6f}")
    print("-" * 60)
    print(f"Total predicted pairs: {len(top_pairs)}")


    return top_pairs, top_scores


from parms_setting import settings

# parameters setting
args = settings()

args.cuda = not args.no_cuda and torch.cuda.is_available()
np.random.seed(args.seed)
torch.manual_seed(args.seed)
if args.cuda:
    torch.cuda.manual_seed(args.seed)
# # 加载数据和多视图graph数据
# dataset, all_data = load_data(args, test_ratio=0.2)

# # 训练，保存5折模型
# best_models, best_metrics = train_model(dataset, all_data, args)

# 载入第1折最优模型示范（你可以载入任意一折或集成）
model = MGCNA(feature=args.dimensions, hidden1=args.hidden1, hidden2=args.hidden2, decoder1=args.decoder1)
if args.cuda:
    model.to("cuda")

# 找出AUC最高的fold index（如果已经训练过）
# 如果模型文件存在，使用最佳模型；否则使用fold3
# if os.path.exists('best_model_fold1.pth'):
#     # 尝试找到所有fold的模型，选择AUC最高的
#     best_fold_index = np.argmax(best_metrics['auc'])
#     best_model_path = best_models[best_fold_index]
#     print(f"Loading best model from fold {best_fold_index + 1} with AUC: {best_metrics['auc'][best_fold_index]:.4f}")
# else:
#     # 如果模型文件不存在，使用默认的fold3
#     best_model_path = 'best_model_fold3.pth'
#     print(f"Loading model from: {best_model_path}")

best_model_path = 'best_model_fold1.pth'

if os.path.exists(best_model_path):
    model.load_state_dict(torch.load(best_model_path))
    model.eval()
    print(f"Model loaded successfully from: {best_model_path}")
else:
    # 尝试加载全局最佳模型
    if os.path.exists('best_model_global.pth'):
        model.load_state_dict(torch.load('best_model_global.pth'))
        model.eval()
        print(f"Global best model loaded from: best_model_global.pth")
    else:
        print(f"Warning: Model file {best_model_path} not found. Please train the model first.")
        exit(1)

# Docetaxel (下标5) 的前25个关联miRNA
print("\n" + "="*60)
print("Predicting top 25 miRNAs associated with Docetaxel (drug_id=5)")
print("="*60)
top_pairs, top_scores = predict_pairs(model, dataset, all_data, args, drug_id=5, top_k=25)

