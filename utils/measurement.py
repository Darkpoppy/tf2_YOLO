# Copyright 2021 Samson. All Rights Reserved.
# =============================================================================

"""Measurements for Yolo.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from .tools import decode
from .tools import cal_iou
from .tools import nms, soft_nms


def create_score_mat(y_trues, *y_preds,
                     class_names=[],
                     conf_threshold=0.5,
                     nms_mode=0,
                     nms_threshold=0.5,
                     nms_sigma=0.5,
                     iou_threshold=0.5,
                     precision_mode=1,
                     version=3):
    """Create score matrix table
    containing precision, recall, F1-score, gts and dets.

    Args:
        y_trues: A tensor or array-like of shape:
            (batch, grid_heights, grid_widths, info_num),
            ground truth label.
        *y_preds: A tensor or array-like of shape:
            (batch, grid_heights, grid_widths, info_num),
            prediction from model.
            Multiple prediction can be given at once.
        class_names: A list of string,
            containing all label names.
        conf_threshold: A float,
            threshold for quantizing output.
        nms_mode: An integer,
            0: Not use NMS.
            1: Use NMS.
            2: Use Soft-NMS.
        nms_threshold: A float,
            threshold for eliminating duplicate boxes.
        nms_sigma: A float,
            sigma for Soft-NMS.
        iou_threshold: A float,
            threshold for true positive determination.
        precision_mode: An integer,
            mode 0: precision = (TPP)/(PP)
            mode 1: precision = (TP)/(PP-(TPP-TP))
            (TPP: true predictive positive;
             TP : true positive;
             PP : predictive positive)
        version: An integer,
            specifying the decode method, yolov1、v2 or v3.  

    Return:
        A Pandas.Dataframe
        with `precision`, `recall`, `F1-score`,
        `gts`(number of all objects) and
        `dets`(number of all detections).
    """
    class_num = len(class_names)

    denom_array = np.zeros((class_num, 2))
    TP_array = np.zeros((class_num, 2))
    det_counts = np.zeros((class_num,), dtype="int")

    for i in range(len(y_trues)):
        y_true = y_trues[i]
        y_pred = [y_preds[j][i] for j in range(len(y_preds))]
        
        xywhcp_true = decode(y_true,
                             class_num=class_num,
                             version=version)
        xywhcp_pred = decode(*y_pred,
                             class_num=class_num,
                             threshold=conf_threshold,
                             version=version)
        if nms_mode > 0 and len(xywhcp_pred) > 0:
            if nms_mode == 1:
                xywhcp_pred = nms(xywhcp_pred, nms_threshold)
            elif nms_mode == 2:
                xywhcp_pred = soft_nms(
                    xywhcp_pred, nms_threshold,
                    conf_threshold, nms_sigma)

        xywhc_true = xywhcp_true[..., :5]
        xywhc_pred = xywhcp_pred[..., :5]
        p_true = xywhcp_true[..., 5:]
        p_pred = xywhcp_pred[..., 5:]
        
        if len(p_true) > 0:
            class_true = p_true.argmax(axis=-1)
        else:
            class_true = p_true
        if len(p_pred) > 0:
            class_pred = p_pred.argmax(axis=-1)
        else:
            class_pred = p_pred

        for class_i in range(class_num):
            xywhc_true_class = xywhc_true[class_true==class_i]
            xywhc_pred_class = xywhc_pred[class_pred==class_i]

            num_PP = len(xywhc_pred_class)
            num_P = len(xywhc_true_class)
            denom_array[class_i] += (num_PP, num_P)
            det_counts[class_i] += num_PP

            if len(xywhc_true_class) > 0 and len(xywhc_pred_class) > 0:
                xywhc_true_class = np.reshape(
                    xywhc_true_class, (-1, 1, 5))
                xywhc_pred_class = np.reshape(
                    xywhc_pred_class, (1, -1, 5))

                iou_scores = cal_iou(xywhc_true_class, xywhc_pred_class)

                best_ious_true = np.max(iou_scores, axis=1)
                best_ious_pred = np.max(iou_scores, axis=0) 

                num_TPP = sum(best_ious_pred >= iou_threshold)
                num_TP = sum(best_ious_true >= iou_threshold)
                
                if precision_mode == 1:
                    denom_array[class_i, 0] -= num_TPP - num_TP
                    num_TPP = num_TP
                TP_array[class_i] += (num_TPP, num_TP)
    score_table = np.true_divide(TP_array, denom_array)
    score_table = pd.DataFrame(score_table)
    score_table.columns = ["precision", "recall"]

    precision = score_table["precision"]
    recall = score_table["recall"]
    F1_score = (2*precision*recall)/(precision + recall)
    score_table["F1-score"] = F1_score
    score_table["gts"] = denom_array[:, 1].astype("int")
    score_table["dets"] = det_counts

    score_table.index = class_names

    return score_table


class PR_func(object):
    """Create precision-reacll function.

    Args:
        y_trues: A tensor or array-like of shape:
            (batch, grid_heights, grid_widths, info_num),
            ground truth label.
        *y_preds: A tensor or array-like of shape:
            (batch, grid_heights, grid_widths, info_num),
            prediction from model.
            Multiple prediction can be given at once.
        class_names: A list of string,
            containing all label names.
        conf_threshold: A float,
            threshold for quantizing output.
        nms_mode: An integer,
            0: Not use NMS.
            1: Use NMS.
            2: Use Soft-NMS.
        nms_threshold: A float,
            threshold for eliminating duplicate boxes.
        nms_sigma: A float,
            sigma for Soft-NMS.
        iou_threshold: A float,
            threshold for true positive determination.
        max_per_img: An integer,
            limit the number of objects
            that an image can detect at most.
        version: An integer,
            specifying the decode method, yolov1、v2 or v3.  

    Return:
        `PR_func` instance, call this instance
        with a recall value and it'll return
        a precision value.
    """
    def __init__(self,
                 y_trues, *y_preds,
                 class_names=[],
                 conf_threshold=0.05,
                 nms_mode=1,
                 nms_threshold=0.5,
                 nms_sigma=0.5,
                 iou_threshold=0.5,
                 max_per_img=100,
                 version=3):
        class_num = len(class_names)
        self.class_num = class_num
        self.class_names = class_names

        gts = [0 for _ in range(class_num)]
        detections = [np.empty((0, 3), dtype="float32")
            for _ in range(class_num)]

        for i_img in range(len(y_trues)):
            y_true = y_trues[i_img]
            y_pred = [y_preds[j][i_img] for j in range(len(y_preds))]
            
            xywhcp_true = decode(y_true,
                                 class_num=class_num,
                                 version=version)
            xywhcp_pred = decode(*y_pred,
                                 class_num=class_num,
                                 threshold=conf_threshold,
                                 version=version)
            if nms_mode > 0 and len(xywhcp_pred) > 0:
                if nms_mode == 1:
                    xywhcp_pred = nms(xywhcp_pred, nms_threshold)
                elif nms_mode == 2:
                    xywhcp_pred = soft_nms(
                        xywhcp_pred, nms_threshold,
                        conf_threshold, nms_sigma)

            xywhc_true = xywhcp_true[..., :5]
            xywhc_pred = xywhcp_pred[..., :5]
            p_true = xywhcp_true[..., 5:]
            p_pred = xywhcp_pred[..., 5:]
            
            if len(p_true) > 0:
                class_true = p_true.argmax(axis=-1)
            else:
                class_true = p_true
            if len(p_pred) > 0:
                class_pred = p_pred.argmax(axis=-1)
            else:
                class_pred = p_pred

            for class_i in range(class_num):
                xywhc_true_class = xywhc_true[class_true==class_i]
                xywhc_pred_class = xywhc_pred[class_pred==class_i]

                num_gts = gts[class_i]
                num_P = len(xywhc_true_class)
                gts[class_i] = num_gts + num_P

                if num_P > 0 and len(xywhc_pred_class) > 0:
                    xywhc_true_class = np.reshape(
                        xywhc_true_class, (-1, 1, 5))
                    xywhc_pred_class = np.reshape(
                        xywhc_pred_class, (1, -1, 5))

                    iou_scores = cal_iou(xywhc_true_class, xywhc_pred_class)
                    best_ious_pred = np.max(iou_scores, axis=0)

                    iou_mask = (best_ious_pred >= iou_threshold)
                    iou_mask = iou_mask.astype("float32")

                    box_id_pred = np.argmax(iou_scores, axis=0) + num_gts

                    conf_pred = xywhc_pred_class[0, :, 4]
                    detection = np.stack(
                        (conf_pred, box_id_pred, iou_mask), axis=1)
                    
                    if (max_per_img is not None 
                        and len(detection) > max_per_img):    
                        sort_index = np.argsort(detection[:, 0])[::-1]
                        detection = detection[sort_index]
                        detection = detection[-max_per_img:]

                    detections[class_i] = np.vstack(
                        (detections[class_i], detection))

        precisions = [[] for _ in range(class_num)]
        recalls = [[] for _ in range(class_num)]

        for class_i in range(class_num):
            num_gts = gts[class_i]
            detection = detections[class_i]
            sort_index = np.argsort(detection[:, 0])[::-1]
            detection = detection[sort_index]
            for det_i in range(len(detection)):
                det = detection[:det_i + 1]

                obj_mask = det[:, 2].astype("bool")
                num_TP = len(set(det[:, 1][obj_mask]))
                num_dets = len(det)
                num_TPP = obj_mask.sum()
                num_FP = num_dets - num_TPP

                precisions[class_i].append(num_TP/(num_TP + num_FP))
                recalls[class_i].append(num_TP/num_gts)
            precisions[class_i].append(0)
            recalls[class_i].append(num_TP/num_gts)
        precisions = [np.array(pc) for pc in precisions]
        recalls = [np.array(rc) for rc in recalls]
        
        self.precisions = precisions
        self.recalls = recalls
        
    def __call__(self, recall, class_idx=0):
        if class_idx >= self.class_num:
            raise IndexError("Class index out of range")
        precisions = self.precisions[class_idx]
        recalls = self.recalls[class_idx]
        pc_idx = (recalls > recall).sum()
        if pc_idx == 0:
            precision = 0
        else:
            precision = precisions[-pc_idx:].max()
        return precision

    def plot_pr_curve(self, class_idx=0,
                      smooth=False,
                      figsize=None):
        """Plot PR curve

        Args:
            class_idx: An integer, index of class.
            smooth: A boolean,
                if True, use interpolated precision.
            figsize: (float, float), optional, default: None
            width, height in inches. If not provided, defaults to [6.4, 4.8].
        """
        if class_idx >= self.class_num:
            raise IndexError("Class index out of range")
        precisions = self.precisions[class_idx].copy()
        recalls = self.recalls[class_idx]

        if smooth:
            max_pc = 0
            for i in range(len(precisions)-1, -1, -1):
                if precisions[i] > max_pc:
                    max_pc = precisions[i]
                else:
                    precisions[i] = max_pc
        
        fig = plt.figure(figsize=figsize)
        plt.plot(recalls, precisions)
        plt.title("PR curve")
        plt.xlabel("recall")
        plt.ylabel("precision")
        plt.xlim(-0.05, 1.05)
        plt.ylim(-0.05, 1.05)
        plt.show()

    def get_map(self, mode="voc2012"):
        """Get a mAP table

        Args:
            mode: A string, one of "voc2007", "voc2012"(default),
                "area", "smootharea".
                "voc2007": calculate the average precision of
                    recalls at [0, 0.1, ..., 1](11 points).
                "voc2012": calculate the average precision of
                    recalls at [0, 0.14, 0.29, 0.43, 0.57, 0.71, 1].
                "area": calculate the area under precision-recall curve.
                "smootharea": calculate the area 
                    under interpolated precision-recall curve.

        Return:
            A Pandas.Dataframe
        """
        aps = [0 for _ in range(self.class_num)]
        
        if mode == "area" or mode == "smootharea":
            for class_i in range(self.class_num):
                if mode == "smootharea":
                    precisions = self.precisions[class_i].copy()
                    max_pc = 0
                    for i in range(len(precisions)-1, -1, -1):
                        if precisions[i] > max_pc:
                            max_pc = precisions[i]
                        else:
                            precisions[i] = max_pc
                else:
                    precisions = self.precisions[class_i]
                recalls = self.recalls[class_i]

                for pr_i in range(0, len(precisions)-1):
                    delta = recalls[pr_i + 1] - recalls[pr_i]
                    value = ((precisions[pr_i + 1] - precisions[pr_i])/2
                             + precisions[pr_i])
                    aps[class_i] += delta*value
        else:
            if mode == "voc2012":
                recall_list = [0, 0.14, 0.29, 0.43, 0.57, 0.71, 1]
            elif mode == "voc2007":
                recall_list = [i/10 for i in range(0, 11)]

            for class_i in range(self.class_num):
                for rc in recall_list:
                    aps[class_i] += self(rc, class_i)
            aps = [ap/len(recall_list) for ap in aps]
        aps.append(sum(aps)/len(aps))

        ap_table = pd.DataFrame(aps)
        ap_table.columns = ["ap"]
        ap_table.index = list(self.class_names) + ["mAP"]

        return ap_table