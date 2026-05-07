from policies.bl_smpc_agent import BLSMPCAgent


class IPOPTSMPCAgent(BLSMPCAgent):
    """IPOPT-based approximation of the paper's multimodal SMPC policies.

    The original SMPC_MMPreds formulation uses CasADi's conic stack with Gurobi.
    This approximation keeps the same CARLA interface, multimodal prediction
    inputs, kinematic vehicle model, and chance-constraint style obstacle terms,
    but solves the nonlinear program with IPOPT through BLSMPCAgent.
    """

    CONFIGS = {
        "var_risk": {"risk": 0.5, "d_min": 2.0, "c_obs_sl": 10000},
        "fixed_risk": {"risk": 0.2, "d_min": 2.2, "c_obs_sl": 15000},
        "open_loop": {"risk": 0.8, "d_min": 1.5, "c_obs_sl": 5000},
        "": {"risk": 0.5, "d_min": 2.0, "c_obs_sl": 10000},
    }

    def __init__(self, *args, approx_config="var_risk", **kwargs):
        config = self.CONFIGS.get(approx_config)
        if config is None:
            raise ValueError(f"Invalid IPOPT approximation config: {approx_config}")
        kwargs.update(config)
        super().__init__(*args, **kwargs)
        self.approx_config = approx_config
