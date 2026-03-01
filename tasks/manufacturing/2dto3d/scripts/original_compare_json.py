import json
import math
import sys
import os
import numpy as np
from scipy.spatial.distance import cdist


class CADComparator:
    def __init__(self, gt_json_path, stu_json_path):
        self.gt_json_path = gt_json_path
        self.stu_json_path = stu_json_path
        self.gt_data = self._load_json(gt_json_path)
        self.stu_data = self._load_json(stu_json_path)

        # --- 评分权重配置 ---
        self.weights = {
            "global": 0.20,  # 20% 基础几何 (体积/原点)
            "quantity": 0.30,  # 30% 特征数量 (直方图)
            "precision": 0.50,  # 50% 特征精度 (位置/轴线)
        }

        # --- 容差配置 ---
        self.tolerances = {
            "volume_error": 0.05,  # 体积误差 > 5% 零分
            "pos_error_max": 2.0,  # 位置偏差 > 2mm 匹配失败
            "pos_error_perfect": 0.1,  # 位置偏差 < 0.1mm 满分
            "axis_angle_max": 15.0,  # 轴线偏差 > 15度 匹配失败
        }

    def _load_json(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")
        with open(path, "r") as f:
            return json.load(f)

    def _vec_dist(self, v1, v2):
        return np.linalg.norm(np.array(v1) - np.array(v2))

    def _vec_angle(self, v1, v2):
        """计算两个向量的夹角 (度)"""
        v1 = np.array(v1)
        v2 = np.array(v2)
        norm_v1 = np.linalg.norm(v1)
        norm_v2 = np.linalg.norm(v2)
        if norm_v1 == 0 or norm_v2 == 0:
            return 90.0

        cos_theta = np.dot(v1, v2) / (norm_v1 * norm_v2)
        cos_theta = np.clip(cos_theta, -1.0, 1.0)

        # 轴线是无向的，180度也是0度误差
        angle = np.degrees(np.arccos(cos_theta))
        if angle > 90:
            angle = 180 - angle
        return angle

    def evaluate_global(self):
        """维度一：全局几何合规性 (20分)"""
        gt_geom = self.gt_data["geometry"]
        stu_geom = self.stu_data["geometry"]

        # 1. 体积评分 (10分)
        vol_gt = gt_geom["volume"]
        vol_stu = stu_geom["volume"]
        vol_diff = abs(vol_stu - vol_gt) / vol_gt

        if vol_diff <= 0.01:
            vol_score = 10.0
        elif vol_diff >= self.tolerances["volume_error"]:
            vol_score = 0.0
        else:
            # 线性插值
            vol_score = 10.0 * (1 - (vol_diff - 0.01) / (self.tolerances["volume_error"] - 0.01))

        # 2. 包围盒/原点评分 (10分)
        # 检查 Min 点是否对齐 (0,0,0)
        bbox_min_gt = np.array(gt_geom["bbox_min"])
        bbox_min_stu = np.array(stu_geom["bbox_min"])
        origin_dist = np.linalg.norm(bbox_min_gt - bbox_min_stu)

        if origin_dist <= 0.1:
            origin_score = 10.0
        elif origin_dist >= 2.0:
            origin_score = 0.0
        else:
            origin_score = 10.0 * (1 - origin_dist / 2.0)

        return {
            "score": round(vol_score + origin_score, 2),
            "max_score": 20.0,
            "details": {
                "volume_error_ratio": round(vol_diff, 4),
                "origin_deviation": round(origin_dist, 4),
            },
        }

    def evaluate_quantity(self):
        """维度二：特征数量完整性 (30分)"""
        gt_hist = self.gt_data["features"]["hole_histogram"]
        stu_hist = self.stu_data["features"]["hole_histogram"]

        total_items = sum(gt_hist.values())
        if total_items == 0:
            return {"score": 30.0, "details": "No holes in GT"}

        # 归一化每个特征的价值
        score_per_item = 30.0 / total_items
        current_score = 30.0

        missing_log = []
        extra_log = []

        # 检查漏画 (Missing)
        for dia, count in gt_hist.items():
            stu_count = stu_hist.get(dia, 0)
            diff = gt_hist[dia] - stu_count
            if diff > 0:
                current_score -= diff * score_per_item
                missing_log.append(f"Missing {diff} holes of Dia {dia}mm")

        # 检查多画 (Extra) - 适当扣分
        for dia, count in stu_hist.items():
            gt_count = gt_hist.get(dia, 0)
            diff = count - gt_count
            if diff > 0:
                current_score -= diff * score_per_item * 0.5  # 多画扣分权重减半
                extra_log.append(f"Extra {diff} holes of Dia {dia}mm")

        return {
            "score": round(max(0, current_score), 2),
            "max_score": 30.0,
            "details": {"missing": missing_log, "extra": extra_log},
        }

    def evaluate_precision(self):
        """维度三：特征位置与精度 (50分)"""
        gt_holes = self.gt_data["features"]["holes_details"]
        stu_holes = self.stu_data["features"]["holes_details"]

        if not gt_holes:
            return {"score": 50.0, "details": "No holes to check"}
        if not stu_holes:
            return {"score": 0.0, "details": "No holes found in student file"}

        # 预分配
        matched_gt_indices = set()
        matched_pairs = []
        total_pos_error = 0.0
        total_axis_error = 0.0

        # 单个孔的满分分值
        score_per_hole = 50.0 / len(gt_holes)
        total_score = 0.0

        # --- 贪婪匹配算法 ---
        # 1. 构建距离矩阵 (GT x Student)
        gt_locs = np.array([h["location"] for h in gt_holes])
        stu_locs = np.array([h["location"] for h in stu_holes])
        dist_matrix = cdist(gt_locs, stu_locs, metric="euclidean")

        # 2. 遍历每个 GT 孔寻找最佳匹配
        for i, gt_h in enumerate(gt_holes):
            best_match_idx = -1
            best_dist = float("inf")

            # 在距离矩阵中找最近的，且未被使用的
            # 过滤条件1: 直径必须接近 (容差 0.1mm)
            candidates = []
            for j, stu_h in enumerate(stu_holes):
                if abs(gt_h["diameter"] - stu_h["diameter"]) < 0.2:  # 直径容差放宽一点点
                    candidates.append(j)

            if not candidates:
                continue  # 没有直径匹配的，跳过 -> 漏画

            # 在候选者中找位置最近的
            for j in candidates:
                dist = dist_matrix[i, j]
                if dist < best_dist:
                    best_dist = dist
                    best_match_idx = j

            # 判定匹配是否有效
            if best_match_idx != -1 and best_dist < self.tolerances["pos_error_max"]:
                # 检查轴线角度
                stu_h = stu_holes[best_match_idx]
                axis_angle = self._vec_angle(gt_h["axis"], stu_h["axis"])

                if axis_angle < self.tolerances["axis_angle_max"]:
                    # --- 匹配成功，开始算分 ---
                    # 1. 位置分 (权重 70%)
                    if best_dist <= self.tolerances["pos_error_perfect"]:
                        pos_score = 1.0
                    else:
                        pos_score = max(0, 1.0 - (best_dist - 0.1) / (2.0 - 0.1))

                    # 2. 角度分 (权重 30%)
                    ang_score = max(0, 1.0 - axis_angle / 15.0)

                    hole_score = score_per_hole * (0.7 * pos_score + 0.3 * ang_score)
                    total_score += hole_score

                    matched_pairs.append(
                        {
                            "gt_idx": i,
                            "stu_idx": best_match_idx,
                            "pos_error": round(best_dist, 4),
                            "axis_error": round(axis_angle, 2),
                        }
                    )
                    total_pos_error += best_dist
                    total_axis_error += axis_angle

        num_matched = len(matched_pairs)
        avg_pos_error = total_pos_error / num_matched if num_matched > 0 else 0

        return {
            "score": round(total_score, 2),
            "max_score": 50.0,
            "details": {
                "total_gt_features": len(gt_holes),
                "matched_features": num_matched,
                "avg_position_error": round(avg_pos_error, 4),
                "avg_axis_error": round(total_axis_error / num_matched if num_matched else 0, 2),
                "matches": matched_pairs,
            },
        }

    def generate_report(self):
        global_res = self.evaluate_global()
        quant_res = self.evaluate_quantity()
        prec_res = self.evaluate_precision()

        final_score = global_res["score"] + quant_res["score"] + prec_res["score"]

        # 评语生成逻辑
        feedback = []
        if final_score >= 90:
            feedback.append("Excellent work! High precision.")
        if global_res["details"]["origin_deviation"] > 0.5:
            feedback.append("Warning: Coordinate origin is misaligned.")
        if len(quant_res["details"]["missing"]) > 0:
            feedback.append(
                f"Missing features detected: {', '.join(quant_res['details']['missing'])}"
            )

        return {
            "meta": {"ground_truth_path": self.gt_json_path, "output_path": self.stu_json_path},
            "summary": {
                "total_score": round(final_score, 1),
                "status": "PASS" if final_score >= 60 else "FAIL",
                "feedback": " ".join(feedback),
            },
            "breakdown": {
                "1_global_geometry": global_res,
                "2_feature_quantity": quant_res,
                "3_feature_precision": prec_res,
            },
        }


if __name__ == "__main__":
    # 使用示例
    # 假设你已经运行了提取器生成了两个 JSON
    gt_file = "/Users/bytedance/Downloads/32300A-000001.json"
    # 这里用 GT 自己对比自己，用来测试满分逻辑
    stu_file = "/Users/bytedance/Downloads/32300A-000001.json"

    try:
        comparator = CADComparator(gt_file, stu_file)
        report = comparator.generate_report()

        # Generate output filename by combining both base filenames
        gt_base = os.path.splitext(os.path.basename(gt_file))[0]
        stu_base = os.path.splitext(os.path.basename(stu_file))[0]
        output_filename = os.path.join(os.path.dirname(gt_file), f"{gt_base}{stu_base}.json")

        # Save report to JSON file
        with open(output_filename, "w") as f:
            json.dump(report, f, indent=2)

        print(f"Report saved to: {output_filename}")
    except Exception as e:
        print(f"Error: {e}")
