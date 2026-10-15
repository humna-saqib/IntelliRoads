"""IntelliRoads FYP – training pipeline for the corrected environment (Stage 3).

Modules
-------
seeds        reproducible seeding and the disjoint train / validation / protected seed ranges
replay       replay buffer that stores current- and next-state action masks
double_dqn   mask-aware Double DQN (target action chosen among legal next actions only)
runs         dedicated output directories, checkpoint format and validation-only checkpoint selection
trainer      the training loop, greedy validation and the ``TrainConfig`` hyper-parameters
"""
