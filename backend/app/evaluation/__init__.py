"""IntelliRoads FYP – fair evaluation protocol for the corrected environment (Stage 4).

Modules
-------
seeds        matched evaluation seeds; final-evaluation and smoke-check ranges, strictly separate from training/validation
metrics      per-episode measurement of all 16 incoming lanes and of every trip (identical code for every controller)
controllers  fixed-time (SUMO's own programme), rule-based, actuated-style and DQN controllers acting through the safe action layer
protocol     the ``EvalProtocol`` definition, signal-timing verification, validation-selected checkpoint loading, evaluation ledger
runner       runs controllers on matched seeds, checks every episode, writes a NEW output directory
"""
