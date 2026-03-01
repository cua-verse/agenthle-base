import sys
import json
import math
import os

# Core OCC imports
from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_REVERSED
from OCC.Core.TopoDS import topods
from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
from OCC.Core.GeomAbs import GeomAbs_Cylinder
from OCC.Core.GProp import GProp_GProps
from OCC.Core.BRepGProp import brepgprop
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib
from OCC.Core.gp import gp_Pnt, gp_Vec
from OCC.Core.BRepLProp import BRepLProp_SLProps


class AdvancedStepAnalyzer:
    def __init__(self, step_path):
        self.step_path = step_path
        self.shape = None
        print(f"Loading STEP file: {step_path}")
        self._load_step_simple()
        print("STEP file loaded successfully.")

    def _load_step_simple(self):
        reader = STEPControl_Reader()
        status = reader.ReadFile(self.step_path)
        if status == IFSelect_RetDone:
            reader.TransferRoot()
            self.shape = reader.Shape()
        else:
            raise ValueError(f"Failed to read STEP file: {self.step_path}")

    def _is_coaxial(self, loc1, dir1, loc2, dir2, tol_loc=0.1, tol_ang=0.02):
        v1 = gp_Vec(dir1[0], dir1[1], dir1[2])
        v2 = gp_Vec(dir2[0], dir2[1], dir2[2])
        if not (v1.IsParallel(v2, tol_ang) or v1.IsParallel(v2.Reversed(), tol_ang)):
            return False
        p1 = gp_Pnt(loc1[0], loc1[1], loc1[2])
        p2 = gp_Pnt(loc2[0], loc2[1], loc2[2])
        vec_p1p2 = gp_Vec(p1, p2)
        cross_prod = vec_p1p2.Crossed(v1)
        return cross_prod.Magnitude() < tol_loc

    def _classify_cylinder_geometric(self, face, surf_adaptor):
        u_min, u_max = surf_adaptor.FirstUParameter(), surf_adaptor.LastUParameter()
        v_min, v_max = surf_adaptor.FirstVParameter(), surf_adaptor.LastVParameter()
        u_mid, v_mid = (u_min + u_max) / 2.0, (v_min + v_max) / 2.0

        sl_props = BRepLProp_SLProps(surf_adaptor, u_mid, v_mid, 1, 1e-6)
        if not sl_props.IsNormalDefined():
            return "unknown"

        p_surf = sl_props.Value()
        n_geom = sl_props.Normal()

        if face.Orientation() == TopAbs_REVERSED:
            n_face = n_geom.Reversed()
        else:
            n_face = n_geom

        cyl = surf_adaptor.Cylinder()
        axis = cyl.Axis()

        vec_loc_to_surf = gp_Vec(axis.Location(), p_surf)
        vec_axis_dir = gp_Vec(axis.Direction().X(), axis.Direction().Y(), axis.Direction().Z())

        projection = vec_loc_to_surf.Dot(vec_axis_dir)
        vec_parallel = vec_axis_dir.Multiplied(projection)
        vec_radial = vec_loc_to_surf.Subtracted(vec_parallel)

        vec_n_face = gp_Vec(n_face.X(), n_face.Y(), n_face.Z())
        dot_prod = vec_n_face.Dot(vec_radial)

        if dot_prod > 0:
            return "pin"
        else:
            return "hole"

    def analyze_features(self):
        print("Analyzing features with Angle Filtering...")
        raw_cylinders = []
        topo_exp = TopExp_Explorer(self.shape, TopAbs_FACE)

        while topo_exp.More():
            face = topods.Face(topo_exp.Current())
            surf_adaptor = BRepAdaptor_Surface(face, True)

            if surf_adaptor.GetType() == GeomAbs_Cylinder:
                cyl = surf_adaptor.Cylinder()
                radius = cyl.Radius()
                axis = cyl.Axis()
                loc = [axis.Location().X(), axis.Location().Y(), axis.Location().Z()]
                direc = [axis.Direction().X(), axis.Direction().Y(), axis.Direction().Z()]

                # 计算这个面的弧度角 (Arc Angle)
                # STEP 中通常是弧度制，2*PI 是整圆
                u_start = surf_adaptor.FirstUParameter()
                u_end = surf_adaptor.LastUParameter()
                angle = abs(u_end - u_start)

                f_type = self._classify_cylinder_geometric(face, surf_adaptor)

                raw_cylinders.append(
                    {
                        "radius": radius,
                        "location": loc,
                        "direction": direc,
                        "type": f_type,
                        "angle": angle,  # 记录角度
                    }
                )
            topo_exp.Next()

        # --- 智能去重与聚合 ---
        merged_features = []
        for raw in raw_cylinders:
            matched = False
            for exist in merged_features:
                if (
                    raw["type"] == exist["type"]
                    and math.isclose(raw["radius"], exist["radius"], abs_tol=0.01)
                    and self._is_coaxial(
                        raw["location"], raw["direction"], exist["location"], exist["direction"]
                    )
                ):
                    # 如果匹配，累加角度
                    exist["total_angle"] += raw["angle"]
                    matched = True
                    break

            if not matched:
                # 新特征，初始化总角度
                raw["total_angle"] = raw["angle"]
                merged_features.append(raw)

        final_features = {"holes": [], "pins": [], "fillets": []}

        for feat in merged_features:
            diameter = feat["radius"] * 2.0
            data = {
                "diameter": round(diameter, 4),
                "location": [round(x, 4) for x in feat["location"]],
                "axis": [round(x, 4) for x in feat["direction"]],
                "angle_deg": round(math.degrees(feat["total_angle"]), 1),
            }

            # --- 最终分类逻辑 ---
            # 1. 只有 concave (hole类型) 的才可能是真正的孔
            # 2. 且总角度必须接近 360度 (考虑误差 > 300度)
            # 3. 如果角度小，说明它是内圆角 (Fillet)

            if feat["type"] == "hole":
                if feat["total_angle"] > 5.0:  # 5.0 rad ≈ 286 deg
                    final_features["holes"].append(data)
                else:
                    final_features["fillets"].append(data)  # 内圆角归为 Fillet
            else:
                # 凸的都是 Pin (外圆角暂时也放这里，或者按半径过滤)
                if feat["radius"] <= 2.1:
                    final_features["fillets"].append(data)  # 外圆角
                else:
                    final_features["pins"].append(data)

        return final_features

    def analyze_global_properties(self):
        props = GProp_GProps()
        brepgprop.VolumeProperties(self.shape, props)
        volume = props.Mass()

        bbox = Bnd_Box()
        brepbndlib.Add(self.shape, bbox)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()

        return {
            "volume": round(volume, 4),
            "bbox_dims": [round(xmax - xmin, 4), round(ymax - ymin, 4), round(zmax - zmin, 4)],
            "bbox_min": [round(xmin, 4), round(ymin, 4), round(zmin, 4)],
            "bbox_max": [round(xmax, 4), round(ymax, 4), round(zmax, 4)],
        }

    def generate_report(self):
        feats = self.analyze_features()
        globals = self.analyze_global_properties()

        hole_hist = {}
        for h in feats["holes"]:
            d_str = f"{h['diameter']:.2f}"
            hole_hist[d_str] = hole_hist.get(d_str, 0) + 1

        return {
            "meta": {"filename": os.path.basename(self.step_path)},
            "geometry": globals,
            "features": {
                "hole_count_unique": len(feats["holes"]),
                "pin_count_unique": len(feats["pins"]),
                "fillet_count_unique": len(feats["fillets"]),
                "hole_histogram": hole_hist,
                "holes_details": feats["holes"],
            },
        }


if __name__ == "__main__":
    gt_file = "/Users/bytedance/Downloads/32300A-000001.STEP"
    try:
        analyzer = AdvancedStepAnalyzer(gt_file)
        report = analyzer.generate_report()

        # Generate output JSON filename in the same directory as input file
        output_dir = os.path.dirname(gt_file)
        base_name = os.path.splitext(os.path.basename(gt_file))[0]
        output_filename = os.path.join(output_dir, f"{base_name}.json")

        # Save to JSON file
        with open(output_filename, "w") as f:
            json.dump(report, f, indent=2)

        print(f"Report saved to: {output_filename}")
    except Exception as e:
        print(f"Error: {e}")
