import os
import re
import glob
import argparse
import numpy as np
import pandas as pd
import pdb
import matplotlib
import pickle as pkl
font = {'weight' : 'normal',
        'size'   : 14}
matplotlib.rc('font', **font)
import matplotlib.pyplot as plt

from evaluation.closed_loop_metrics import ScenarioResult, ClosedLoopTrajectory, load_scenario_result


def _parse_scenario_dir_name(scenario_dir):
    base = os.path.basename(scenario_dir.rstrip("/"))
    if "_ego_init_" not in base:
        return None
    scenario_name, tail = base.split("_ego_init_", 1)
    init_str, policy = tail.split("_", 1)
    return scenario_name, int(init_str), policy

def get_metric_dataframe(results_dir):
    scenario_dirs = sorted(glob.glob(results_dir + "*scenario_lk*"))

    if len(scenario_dirs) == 0:
        raise ValueError(f"Could not detect scenario results in directory: {results_dir}")

    # Assumption: format is *scenario_<scene_num>_ego_init_<init_num>_policy
    dataframe = []
    for scenario_dir in scenario_dirs:
        # pdb.set_trace()
        scene_num =  1#scenario_dir.split("scenario_")[-1].split("_")[0] 
        init_num  = int( scenario_dir.split("ego_init_")[-1].split("_")[0])
        policy    = re.split("ego_init_[0-9]*_", scenario_dir)[-1]

        pkl_path = os.path.join(scenario_dir, "scenario_result.pkl")

        
        if not os.path.exists(pkl_path):
            raise RuntimeError(f"Unable to find a scenario_result.pkl in directory: {scenario_dir}")

        notv_pkl_path = os.path.join(re.split(f"{policy}", scenario_dir)[0] + "notv", "scenario_result.pkl")
        if not os.path.exists(notv_pkl_path):
            raise RuntimeError(f"Unable to find a notv scenario_result.pkl in location: {notv_pkl_path}")

        # Load scenario dict for this policy and the notv case (for Hausdorff distance).
        sr      = load_scenario_result(pkl_path)
        notv_sr = load_scenario_result(notv_pkl_path)

        metrics_dict = sr.compute_metrics()
        metrics_dict["hausdorff_dist_notv"] = sr.compute_ego_hausdorff_dist(notv_sr)
        dmins = metrics_dict.pop("dmins_per_TV")
        if dmins:
            metrics_dict["dmin_TV"] = np.amin(dmins) # take the closest distance to any TV in the scene
        else:
            metrics_dict["dmin_TV"] = np.nan # no moving TVs in the scene
        metrics_dict["scenario"] = scene_num
        metrics_dict["initial"]  = init_num
        metrics_dict["policy"]   = policy
        dataframe.append(metrics_dict)

    return pd.DataFrame(dataframe)

def make_trajectory_viz_plot(results_dir, color1="r", color2="b", plot_init=1, plot_pol="no_switch"):
    scenario_dirs = sorted(glob.glob(results_dir + "*scenario*lk*"))

    if len(scenario_dirs) == 0:
        raise ValueError(f"Could not detect scenario results in directory: {results_dir}")

    # Assumption: format is *scenario_<scene_num>_ego_init_<init_num>_policy
    dataframe = []
    for scenario_dir in scenario_dirs:
        scene_num = 1#scenario_dir.split("scenario_")[-1].split("_")[0]
        init_num  = int( scenario_dir.split("ego_init_")[-1].split("_")[0])
        policy    = re.split("ego_init_[0-9]*_", scenario_dir)[-1]

        pkl_path = os.path.join(scenario_dir, "scenario_result.pkl")

        if not os.path.exists(pkl_path):
            raise RuntimeError(f"Unable to find a scenario_result.pkl in directory: {scenario_dir}")

        notv_pkl_path = os.path.join(re.split(f"{policy}", scenario_dir)[0] + "notv", "scenario_result.pkl")
        if not os.path.exists(notv_pkl_path):
            raise RuntimeError(f"Unable to find a notv scenario_result.pkl in location: {notv_pkl_path}")
        
        notv_cl_pkl_path = os.path.join(re.split(f"{policy}", scenario_dir)[0] + "notv_cl", "scenario_result.pkl")
        if not os.path.exists(notv_pkl_path):
            raise RuntimeError(f"Unable to find a notv_cl scenario_result.pkl in location: {notv_pkl_path}")

        # Load scenario dict for this policy and the notv case (for Hausdorff distance).
        if init_num==plot_init:
            if"no_switch" in scenario_dir:
                sr      = load_scenario_result(pkl_path)
                notv_sr = load_scenario_result(notv_pkl_path)
                notv_cl_sr = load_scenario_result(notv_cl_pkl_path)

                # Get time vs. frenet projection for this policy's ego trajectory vs the notv case.
                ts, s_wrt_notv, ey_wrt_notv, epsi_wrt_notv = sr.compute_ego_frenet_projection(notv_sr)

                # Get time vs. frenet projection for this policy's ego trajectory vs cl.
                ts_cl, s_wrt_cl, ey_wrt_cl, epsi_wrt_cl = sr.compute_ego_frenet_projection(notv_cl_sr)
                v=sr.ego_closed_loop_trajectory.state_trajectory[:,-1]
                a=sr.ego_closed_loop_trajectory.input_trajectory[:,0]
                steer=sr.ego_closed_loop_trajectory.input_trajectory[:,-1]

            elif "open_loop" in scenario_dir:

                sr_ol      = load_scenario_result(pkl_path)
                notv_sr = load_scenario_result(notv_pkl_path)
                notv_cl_sr = load_scenario_result(notv_cl_pkl_path)



                # Get time vs. frenet projection for this policy's ego trajectory vs cl.
                ts_cl, s_ol_wrt_cl, ey_ol_wrt_cl, epsi_ol_wrt_cl = sr_ol.compute_ego_frenet_projection(notv_cl_sr)
                v_ol=sr_ol.ego_closed_loop_trajectory.state_trajectory[:,-1]
                a_ol=sr_ol.ego_closed_loop_trajectory.input_trajectory[:,0]
                steer_ol=sr_ol.ego_closed_loop_trajectory.input_trajectory[:,-1]
        

            
            # # Get the closest distance to a TV across all timesteps identified above.
            # d_closest = np.ones(ts.shape) * np.inf
            # d_trajs_TV = sr.get_distances_to_TV()

            # for tv_ind in range(len(d_trajs_TV)):
            #     t_traj = d_trajs_TV[tv_ind][:,0]
            #     d_traj = d_trajs_TV[tv_ind][:,1]

            #     d_interp = np.interp(ts, t_traj, d_traj, left=np.inf, right=np.inf)

            #     d_closest = np.minimum(d_interp, d_closest)

            # Make the plots.
            # t0 = sr.ego_closed_loop_trajectory.state_trajectory[0, 0]
            # trel = ts - t0
            # ax1 = plt.gca()
            # ax3.plot(np.array(s_cl)-s_cl[0], v_cl, 'b', linewidth=2.0, label="Ours")
            # ax3.plot(np.array(s_ol)-s_ol[0], v_ol, 'r', linewidth=2.0, label="BL")
            # ax3.set_ylabel("Speed")
            # ax3.set_xlabel("$s$")
            # plt.legend()
            # ax1.set_xlabel("Time (s)")
            # ax1.set_ylabel("Route Progress (m)", color=color1)
            # ax1.plot(trel[::2], s_wrt_notv[::2], color=color1)
            # ax1.tick_params(axis="y", labelcolor=color1)
            # ax1.set_yticks(np.arange(0., 101., 10.))

            # ax2 = ax1.twinx()
            # ax2.set_ylabel("Closest TV distance (m)", color=color2)
            # ax2.plot(trel[::2], d_closest[::2], color=color2)
            # ax2.tick_params(axis="y", labelcolor=color2)
            # ax2.set_yticks(np.arange(0., 51., 5.))

            # ax1.plot(s_wrt_cl, ey_wrt_cl)

            # plt.tight_layout()
            # plt.savefig(f'{scenario_dir}/traj_viz.svg', bbox_inches='tight')
    fig=plt.figure(figsize=(10,15))
    
    
    data_cl={'s':np.array(s_wrt_cl)[:-64]-s_wrt_cl[0],
             'ey_ref':np.ones(len(s_wrt_cl)-64)*3.6,
             'ey':np.array(ey_wrt_cl)[:-64].squeeze(),
             'epsi':180/np.pi*np.array(epsi_wrt_cl)[:-64].squeeze(),
             'v':np.convolve(np.array(v).squeeze(),np.ones(20)*0.05,mode='same')[:-64],
             'a':np.convolve(np.array(a).squeeze(),np.ones(20)*0.05,mode='same')[:-64],
             'steer':np.convolve(180/np.pi*np.array(steer).squeeze(),np.ones(5)*0.2,mode='same')[:-64]}
    
    data_ol={'s':np.array(s_ol_wrt_cl)[:-2]-s_ol_wrt_cl[0],
             'ey_ref':np.ones(len(s_ol_wrt_cl)-2)*3.6,
             'ey':np.array(ey_ol_wrt_cl)[:-2].squeeze(),
             'epsi':180/np.pi*np.array(epsi_ol_wrt_cl)[:-2].squeeze(),
             'v':np.convolve(np.array(v_ol).squeeze(),np.ones(20)*0.05,mode='same')[:-2],
             'a':np.convolve(np.array(a_ol).squeeze(),np.ones(20)*0.05,mode='same')[:-2],
             'steer':np.convolve(180/np.pi*np.array(steer_ol).squeeze(),np.ones(5)*0.2,mode='same')[:-2]}
    
    # dicts=[data_cl, data_ol]
    # with open('cl_vs_ol_data.pkl', 'wb') as f: 
    #     pkl.dump(dicts, f, protocol=pkl.HIGHEST_PROTOCOL)
    
   

    ax1=plt.subplot(511)
    ax1.plot(np.array(s_wrt_cl)[:-64]-s_wrt_cl[0], np.ones(len(s_wrt_cl)-64)*3.6, 'k--', linewidth=1.5, label="$e_y^{ref}$")
    ax1.plot(np.array(s_wrt_cl)[:-64]-s_wrt_cl[0], np.convolve(np.array(ey_wrt_cl).squeeze(),np.ones(5)*0.2,mode='same')[:-64], 'b', linewidth=2.0, label="Proposed")
    ax1.plot(np.array(s_ol_wrt_cl)[:-2]-s_ol_wrt_cl[0], np.convolve(np.array(ey_ol_wrt_cl).squeeze(),np.ones(5)*0.2,mode='same')[:-2], 'r--', linewidth=2.0, label="OL")
    # ax1.plot(np.array(s_ol)-s_ol[0], np.array(ey_ol).squeeze(), 'r', linewidth=2.0, label="BL")
    ax1.set_ylabel("$e_y [m]$")
    plt.grid()
    plt.legend()
    ax2=plt.subplot(512)
    # ax1.plot(np.array(s_wrt_cl)-s_wrt_cl[0], np.ones(len(s_wrt_cl))*3.5, 'k--', linewidth=1.5, label="$e_y^{ref}$")
    ax2.plot(np.array(s_wrt_cl)[:-64]-s_wrt_cl[0], 180/np.pi*np.array(epsi_wrt_cl)[:-64].squeeze(), 'b', linewidth=2.0, label="Proposed")
    ax2.plot(np.array(s_ol_wrt_cl)[:-2]-s_ol_wrt_cl[0], 180/np.pi*np.array(epsi_ol_wrt_cl).squeeze()[:-2], 'r--', linewidth=2.0, label="OL")
    ax2.set_ylabel("$e_\psi [deg]$ ")
    plt.grid()
    # plt.legend()
    ax3=plt.subplot(513)
    ax3.plot(np.array(s_wrt_cl)[:-64]-s_wrt_cl[0], np.convolve(np.array(v).squeeze(),np.ones(20)*0.05,mode='same')[:-64], 'b', linewidth=2.0, label="Proposed")
    ax3.plot(np.array(s_ol_wrt_cl)[:-2]-s_ol_wrt_cl[0], np.convolve(np.array(v_ol).squeeze(),np.ones(20)*0.05,mode='same')[:-2], 'r--', linewidth=2.0, label="OL")
    ax3.set_ylabel("Speed $[m/s]$")
    plt.grid()
    ax4=plt.subplot(514)
    ax4.plot(np.array(s_wrt_cl)[:-64]-s_wrt_cl[0], np.convolve(180/np.pi*np.array(steer).squeeze(),np.ones(2)*0.5,mode='same')[:-64], 'b', linewidth=2.0, label="Proposed")
    ax4.plot(np.array(s_ol_wrt_cl)[:-2]-s_ol_wrt_cl[0], np.convolve(180/np.pi*np.array(steer_ol).squeeze(),np.ones(2)*0.5,mode='same')[:-2], 'r--', linewidth=2.0, label="OL")
    ax4.set_ylabel("Steering [deg]")
    plt.grid()
    ax5=plt.subplot(515)
    ax5.plot(np.array(s_wrt_cl)[:-64]-s_wrt_cl[0], np.convolve(np.array(a).squeeze(),np.ones(20)*0.05,mode='same')[:-64], 'b', linewidth=2.0, label="Proposed")
    ax5.plot(np.array(s_ol_wrt_cl)[:-2]-s_ol_wrt_cl[0], np.convolve(np.array(a_ol).squeeze(),np.ones(20)*0.05,mode='same')[:-2], 'r--', linewidth=2.0, label="OL")
    ax5.set_ylabel("$a [m/s^2]$")
    ax5.set_xlabel("$Station[m]$")
    plt.grid()
    

    plt.show()

    # fig.savefig('traj_viz.png', bbox_inches='tight')


def make_trajectory_map_plot(results_dir,
                             plot_scenario="scenario_01",
                             plot_init=1,
                             plot_policies=None,
                             tv_source_policy="smpc_var_risk",
                             out_name="trajectory_map"):
    if plot_policies is None:
        plot_policies = ["smpc_var_risk", "smpc_open_loop", "smpc_fixed_risk", "notv", "notv_cl"]

    all_dirs = sorted(glob.glob(os.path.join(results_dir, "scenario_*_ego_init_*")))
    if not all_dirs:
        raise RuntimeError(f"No scenario result folders found under: {results_dir}")

    matched = {}
    for d in all_dirs:
        parsed = _parse_scenario_dir_name(d)
        if parsed is None:
            continue
        scenario_name, init_num, policy = parsed
        if scenario_name == plot_scenario and init_num == plot_init:
            matched[policy] = d

    if not matched:
        raise RuntimeError(f"No matches for {plot_scenario}, ego_init_{plot_init:02d}")

    color_map = {
        "smpc_var_risk": "#1f77b4",
        "smpc_open_loop": "#d62728",
        "smpc_fixed_risk": "#2ca02c",
        "notv": "#7f7f7f",
        "notv_cl": "#9467bd",
    }
    label_map = {
        "smpc_var_risk": "Proposed",
        "smpc_open_loop": "Open-Loop",
        "smpc_fixed_risk": "Fixed-Risk",
        "notv": "No-TV",
        "notv_cl": "Centerline",
    }

    fig, ax = plt.subplots(figsize=(8, 8))
    plotted_any = False

    for policy in plot_policies:
        if policy not in matched:
            continue
        pkl_path = os.path.join(matched[policy], "scenario_result.pkl")
        if not os.path.exists(pkl_path):
            continue
        sr = load_scenario_result(pkl_path)
        xy = sr.ego_closed_loop_trajectory.state_trajectory[:, 1:3]
        ax.plot(xy[:, 0], xy[:, 1],
                linewidth=2.2,
                color=color_map.get(policy, None),
                label=label_map.get(policy, policy))
        plotted_any = True

    if not plotted_any:
        raise RuntimeError("No policy trajectories were plotted; check result folders and policy names.")

    if tv_source_policy in matched:
        pkl_path = os.path.join(matched[tv_source_policy], "scenario_result.pkl")
        if os.path.exists(pkl_path):
            sr_tv = load_scenario_result(pkl_path)
            for idx, tv in enumerate(sr_tv.tv_closed_loop_trajectories):
                xy = tv.state_trajectory[:, 1:3]
                ax.plot(xy[:, 0], xy[:, 1], "k--", linewidth=1.2, alpha=0.8,
                        label="Target vehicle" if idx == 0 else None)

    ax.set_title(f"{plot_scenario}, ego_init_{plot_init:02d}")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.grid(True, alpha=0.25)
    ax.axis("equal")
    ax.legend(loc="best")
    fig.tight_layout()

    out_png = os.path.join(results_dir, f"{out_name}.png")
    out_svg = os.path.join(results_dir, f"{out_name}.svg")
    fig.savefig(out_png, dpi=220, bbox_inches="tight")
    fig.savefig(out_svg, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved trajectory plots:\n- {out_png}\n- {out_svg}")


def _load_policy_data(matched, policy):
    pkl_path = os.path.join(matched[policy], "scenario_result.pkl")
    sr = load_scenario_result(pkl_path)
    return sr


def make_paper_timeseries_plot(results_dir,
                               plot_scenario="scenario_01",
                               plot_init=1,
                               proposed_policy="smpc_var_risk",
                               baseline_policy="smpc_open_loop",
                               cl_policy="notv_cl",
                               out_name="paper_timeseries"):
    all_dirs = sorted(glob.glob(os.path.join(results_dir, "scenario_*_ego_init_*")))
    if not all_dirs:
        raise RuntimeError(f"No scenario result folders found under: {results_dir}")

    matched = {}
    for d in all_dirs:
        parsed = _parse_scenario_dir_name(d)
        if parsed is None:
            continue
        scenario_name, init_num, policy = parsed
        if scenario_name == plot_scenario and init_num == plot_init:
            matched[policy] = d

    required = [proposed_policy, baseline_policy, cl_policy]
    missing = [p for p in required if p not in matched]
    if missing:
        raise RuntimeError(f"Missing required policies for panel plot: {missing}")

    sr_prop = _load_policy_data(matched, proposed_policy)
    sr_base = _load_policy_data(matched, baseline_policy)
    sr_cl = _load_policy_data(matched, cl_policy)

    _, s_prop, ey_prop, epsi_prop = sr_prop.compute_ego_frenet_projection(sr_cl)
    _, s_base, ey_base, epsi_base = sr_base.compute_ego_frenet_projection(sr_cl)

    v_prop = sr_prop.ego_closed_loop_trajectory.state_trajectory[:, -1]
    v_base = sr_base.ego_closed_loop_trajectory.state_trajectory[:, -1]
    a_prop = sr_prop.ego_closed_loop_trajectory.input_trajectory[:, 0]
    a_base = sr_base.ego_closed_loop_trajectory.input_trajectory[:, 0]
    st_prop = np.degrees(sr_prop.ego_closed_loop_trajectory.input_trajectory[:, -1])
    st_base = np.degrees(sr_base.ego_closed_loop_trajectory.input_trajectory[:, -1])

    # Align station to start at zero.
    s_prop = np.array(s_prop) - s_prop[0]
    s_base = np.array(s_base) - s_base[0]

    # Light smoothing for paper-style curves.
    def smooth(arr, k):
        if len(arr) < k:
            return arr
        ker = np.ones(k) / float(k)
        return np.convolve(np.array(arr).squeeze(), ker, mode="same")

    ey_prop_s = smooth(ey_prop, 5)
    ey_base_s = smooth(ey_base, 5)
    epsi_prop_s = np.degrees(smooth(epsi_prop, 5))
    epsi_base_s = np.degrees(smooth(epsi_base, 5))
    v_prop_s = smooth(v_prop, 20)
    v_base_s = smooth(v_base, 20)
    a_prop_s = smooth(a_prop, 20)
    a_base_s = smooth(a_base, 20)
    st_prop_s = smooth(st_prop, 5)
    st_base_s = smooth(st_base, 5)

    fig, axes = plt.subplots(5, 1, figsize=(9, 14), sharex=False)

    axes[0].plot(s_prop, np.ones_like(s_prop) * 3.6, "k--", linewidth=1.3, label=r"$e_y^{ref}$")
    axes[0].plot(s_prop, ey_prop_s, "b", linewidth=2.1, label="Proposed")
    axes[0].plot(s_base, ey_base_s, "r--", linewidth=2.1, label="Open-Loop")
    axes[0].set_ylabel(r"$e_y$ [m]")
    axes[0].grid(True, alpha=0.25)
    axes[0].legend(loc="best")

    axes[1].plot(s_prop, epsi_prop_s, "b", linewidth=2.1)
    axes[1].plot(s_base, epsi_base_s, "r--", linewidth=2.1)
    axes[1].set_ylabel(r"$e_\psi$ [deg]")
    axes[1].grid(True, alpha=0.25)

    axes[2].plot(s_prop, v_prop_s, "b", linewidth=2.1)
    axes[2].plot(s_base, v_base_s, "r--", linewidth=2.1)
    axes[2].set_ylabel("Speed [m/s]")
    axes[2].grid(True, alpha=0.25)

    axes[3].plot(s_prop, st_prop_s, "b", linewidth=2.1)
    axes[3].plot(s_base, st_base_s, "r--", linewidth=2.1)
    axes[3].set_ylabel("Steer [deg]")
    axes[3].grid(True, alpha=0.25)

    axes[4].plot(s_prop, a_prop_s, "b", linewidth=2.1)
    axes[4].plot(s_base, a_base_s, "r--", linewidth=2.1)
    axes[4].set_ylabel(r"$a$ [m/s$^2$]")
    axes[4].set_xlabel("Station [m]")
    axes[4].grid(True, alpha=0.25)

    fig.suptitle(f"{plot_scenario}, ego_init_{plot_init:02d}", y=0.995)
    fig.tight_layout()
    out_png = os.path.join(results_dir, f"{out_name}.png")
    out_svg = os.path.join(results_dir, f"{out_name}.svg")
    fig.savefig(out_png, dpi=220, bbox_inches="tight")
    fig.savefig(out_svg, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved paper panel plots:\n- {out_png}\n- {out_svg}")
            
def normalize_by_notv(df):
    # Compute metrics that involve normalizing by the notv scenario execution.
    # Right now, these metrics are completion_time and max_lateral_acceleration.

    # Add the new columns with normalized values.
    df = df.assign( max_lateral_acceleration_norm = df.max_lateral_acceleration,
                    completion_time_norm = df.completion_time)

    # Do the normalization per scenario / ego initial condition.
    scene_inits = set( [f"{s}_{i}" for (s,i) in zip(df.scenario, df.initial)])

    for scene_init in scene_inits:
        s, i = [int(float(x)) for x in scene_init.split("_")]
        s_i_inds = np.logical_and(df.scenario == s, df.initial == i)
        notv_inds = np.logical_and(s_i_inds, df.policy=="notv")

        if np.sum(notv_inds) != 1:
            raise RuntimeError(f"Unable to find a unique notv execution for scenario {s}, initialization {i}.")

        notv_ind       = np.where(notv_inds)[0].item()
        notv_lat_accel = df.max_lateral_acceleration[notv_ind]
        notv_time      = df.completion_time[notv_ind]

        lat_accel_normalized = df[s_i_inds].max_lateral_acceleration / notv_lat_accel
        df.loc[s_i_inds, "max_lateral_acceleration_norm"] = lat_accel_normalized

        time_normalized = df[s_i_inds].completion_time / notv_time
        df.loc[s_i_inds, "completion_time_norm"] = time_normalized

    return df

def aggregate(df):
    df_aggregate = []

    for scenario in set(df.scenario):
        for policy in set(df.policy):
            subset_inds = np.logical_and( df.scenario == scenario, df.policy == policy )

            res = df[subset_inds].mean(numeric_only=True)
            res.drop(["initial", "scenario"], inplace=True)

            res_dict = {"scenario": int(scenario), "policy": policy}
            res_dict.update(res.to_dict())
            df_aggregate.append(res_dict)

    return pd.DataFrame(df_aggregate)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Aggregate CARLA scenario results.")
    parser.add_argument("--results_dir", default=None, help="Results directory. Defaults to <core>/results.")
    parser.add_argument("--compute_metrics", action="store_true", help="Compute and save csv metrics.")
    parser.add_argument("--make_traj_viz", action="store_true", help="Render trajectory visualization.")
    parser.add_argument("--make_traj_map", action="store_true", help="Save paper-style XY trajectory map.")
    parser.add_argument("--make_paper_panel", action="store_true",
                        help="Save 5-panel paper-style curves (ey/epsi/v/steer/a).")
    parser.add_argument("--plot_scenario", default="scenario_01", help="Scenario name, e.g. scenario_01.")
    parser.add_argument("--plot_init", type=int, default=1, help="Init index, e.g. 1 for ego_init_01.")
    parser.add_argument("--plot_policies", nargs="+",
                        default=["smpc_var_risk", "smpc_open_loop", "smpc_fixed_risk", "notv", "notv_cl"],
                        help="Policies to render on trajectory map.")
    parser.add_argument("--tv_source_policy", default="smpc_var_risk",
                        help="Which policy result to use for target-vehicle trajectories.")
    parser.add_argument("--traj_map_name", default="trajectory_map", help="Output filename prefix.")
    parser.add_argument("--panel_proposed_policy", default="smpc_var_risk",
                        help="Proposed policy name for paper panel.")
    parser.add_argument("--panel_baseline_policy", default="smpc_open_loop",
                        help="Baseline policy name for paper panel.")
    parser.add_argument("--panel_centerline_policy", default="notv_cl",
                        help="Centerline/no-TV-CL policy name for Frenet reference.")
    parser.add_argument("--paper_panel_name", default="paper_panel", help="Paper panel output filename prefix.")
    args = parser.parse_args()

    results_dir = (
        os.path.join(os.path.abspath(__file__).split('scripts')[0], 'results/')
        if args.results_dir is None
        else os.path.abspath(args.results_dir)
    )
    compute_metrics = args.compute_metrics
    make_traj_viz = args.make_traj_viz

    if compute_metrics:
        dataframe = get_metric_dataframe(results_dir)
        dataframe.to_csv(os.path.join(results_dir, "df_full.csv"), sep=",")

        dataframe = normalize_by_notv(dataframe)
        dataframe.to_csv(os.path.join(results_dir, "df_norm.csv"), sep=",")

        dataframe  = aggregate(dataframe)
        dataframe.to_csv(os.path.join(results_dir, "df_final.csv"), sep=",")

    if make_traj_viz:
        make_trajectory_viz_plot(results_dir)

    if args.make_traj_map:
        make_trajectory_map_plot(
            results_dir=results_dir,
            plot_scenario=args.plot_scenario,
            plot_init=args.plot_init,
            plot_policies=args.plot_policies,
            tv_source_policy=args.tv_source_policy,
            out_name=args.traj_map_name,
        )

    if args.make_paper_panel:
        make_paper_timeseries_plot(
            results_dir=results_dir,
            plot_scenario=args.plot_scenario,
            plot_init=args.plot_init,
            proposed_policy=args.panel_proposed_policy,
            baseline_policy=args.panel_baseline_policy,
            cl_policy=args.panel_centerline_policy,
            out_name=args.paper_panel_name,
        )
