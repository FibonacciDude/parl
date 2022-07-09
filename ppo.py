import core
import numpy as np
import torch
import mpi4py as MPI
from mpi_tools import *

# TODO
# add logger
# add mpi (for gradients) - parallel rather than sequential

def ppo_clip(ac, traj, pi_optim, vf_optim, pi_iters=80, vf_iters=80, targ_kl=.003, eps=.2, gamma=.99, lam=.95):

    core.gae(traj, gamma, lam)
    sync_params(ac)

    # TODO: why .copy() error (negative stride)
    def pi_loss(ac, traj):
        obs, act, adv, logp_old = traj['obs'], traj['act'], traj['adv'], traj['logp']
        adv = torch.tensor(adv.copy(), device=ac.device)

        logp = ac.logprob(obs, act)
        log_ratio = logp - logp_old
        ratio = torch.exp(log_ratio)
        clip_adv = (ratio*adv.reshape(-1,1)).clamp(min=1-eps, max=1+eps)
        loss = -torch.min(ratio*adv.reshape(-1,1), clip_adv).mean()
        approx_kl = ((ratio-1) - log_ratio).mean().item()
        return loss, approx_kl

    def vf_loss(ac, traj):
        ret = torch.tensor(traj['ret'].copy(), device=ac.device)
        loss = .5 * (ac.predict(traj['obs']) - ret)**2
        return loss.mean()

    for _ in range(pi_iters):
        pi_optim.zero_grad()
        # average losses on trajectories
        loss, pi_kl = pi_loss(ac, traj)
        pi_kl = mpi_avg(pi_kl)
        if pi_kl > 1.5 * targ_kl:
            # print("Finished due to too great of a KL %d" % _) # put this in log
            break
        loss.backward()
        torch.nn.utils.clip_grad_norm_(ac.actor.parameters(), .5)
        mpi_avg_grads(ac.actor)
        pi_optim.step()

    for _ in range(vf_iters):
        vf_optim.zero_grad()
        loss = vf_loss(ac, traj)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(ac.critic.parameters(), .5)
        mpi_avg_grads(ac.critic)
        vf_optim.step()
