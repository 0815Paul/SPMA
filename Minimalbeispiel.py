import pyomo.environ as pyo
import matplotlib.pyplot as plt
from pyomo.environ import Binary, NonNegativeReals
import sys

# Szenarien und Wahrscheinlichkeiten
scenarios = [1, 2, 3]
timesteps = [1, 2, 3, 4, 5]
probabilities = {1: 1/3, 2: 1/3, 3: 1/3}
demand = {
    (1, 1): 90, (1, 2): 96, (1, 3): 92, (1, 4): 94, (1, 5): 88,
    (2, 1): 75, (2, 2): 85, (2, 3): 80, (2, 4): 75, (2, 5): 70,
    (3, 1): 100, (3, 2): 100, (3, 3): 95, (3, 4): 120, (3, 5): 90
}

# Parameter
gas_price = {1:9.22, 2:8.84, 3:8.67, 4:8.12, 5:9.49}
power_price = {1:90.8, 2:96.2, 3:92.3, 4:88.7, 5:91.1}
heat_price = {1:50, 2:50, 3:50, 4:50, 5:50}

# CHP parameters
chp_power_max = 63
chp_power_min = 10
chp_gas_max = 160
chp_gas_min = 66
chp_heat_max = 82
chp_heat_min = 41

# Heat Storage parameters
storage_heat_max = 50
storage_heat_min = 0
storage_content_max = 150

# Model erstellen
model = pyo.ConcreteModel()

# Variables
model.chp_bin = pyo.Var(scenarios, timesteps, within=Binary)
model.chp_gas = pyo.Var(scenarios, timesteps, within=NonNegativeReals)
model.chp_power = pyo.Var(scenarios, timesteps, within=NonNegativeReals)
model.chp_heat = pyo.Var(scenarios, timesteps, within=NonNegativeReals)

model.storage_heat = pyo.Var(scenarios, timesteps, within=NonNegativeReals)
model.storage_content = pyo.Var(scenarios, timesteps, within=NonNegativeReals)
model.storage_bin_discharging = pyo.Var(scenarios, timesteps, within=Binary)
model.storage_bin_charging = pyo.Var(scenarios, timesteps, within=Binary)

# Constraints
# CHP Constraints
def power_max_rule(model, i, t):
    return model.chp_power[i,t] <= chp_power_max * model.chp_bin[i,t]
model.power_max = pyo.Constraint(scenarios, timesteps, rule=power_max_rule)

def power_min_rule(model, i, t):
    return model.chp_power[i,t] >= chp_power_min * model.chp_bin[i,t]
model.power_min = pyo.Constraint(scenarios, timesteps, rule=power_min_rule)

def gas_depends_on_power_rule(model, i, t):
    a = (chp_gas_max - chp_gas_min) / (chp_power_max - chp_power_min)
    b = chp_gas_max - a * chp_power_max
    return model.chp_gas[i,t] == a * model.chp_power[i,t] + b * model.chp_bin[i,t]
model.gas_depends_on_power = pyo.Constraint(scenarios, timesteps, rule=gas_depends_on_power_rule)

def heat_depends_on_power_rule(model, i, t):
    a = (chp_heat_max - chp_heat_min) / (chp_power_max - chp_power_min)
    b = chp_heat_max - a * chp_power_max
    return model.chp_heat[i,t] == a * model.chp_power[i,t] + b * model.chp_bin[i,t]
model.heat_depends_on_power = pyo.Constraint(scenarios, timesteps, rule=heat_depends_on_power_rule)

# Heat Storage Constraints
def storage_balance_rule(model, i, t):
    if t == 1:
        return model.storage_content[i,t] == 0 - model.storage_heat[i,t]
    else:
        return model.storage_content[i,t] == model.storage_content[i,t-1] - model.storage_heat[i,t] 
model.storage_balance = pyo.Constraint(scenarios, timesteps, rule=storage_balance_rule)

def storage_initial_rule(model, i):
    return model.storage_content[i,1] == 0
model.storage_initial = pyo.Constraint(scenarios, rule=storage_initial_rule)

def max_storage_rule(model, i, t):
    return model.storage_content[i,t] <= storage_content_max
model.max_storage = pyo.Constraint(scenarios, timesteps, rule=max_storage_rule)

def min_storage_rule(model, i, t):
    return model.storage_content[i,t] >= storage_heat_min
model.min_storage = pyo.Constraint(scenarios, timesteps, rule=min_storage_rule)

def storage_heat_charging_rule(model, i, t):
    return model.storage_heat[i,t] <= -storage_heat_max
model.storage_heat_charging_rule = pyo.Constraint(scenarios, timesteps, rule=storage_heat_charging_rule)

def storage_heat_discharging_rule(model, i, t):
    return model.storage_heat[i,t] <= +storage_heat_max
model.storage_heat_discharging_rule = pyo.Constraint(scenarios, timesteps, rule=storage_heat_discharging_rule)


def storage_bin_rule(model, i, t):
    return model.storage_bin_discharging[i,t] + model.storage_bin_charging[i,t] <= 1
model.storage_bin_rule = pyo.Constraint(scenarios, timesteps, rule=storage_bin_rule)
 
# Heat Balance Constraint

def demand_constraint_rule(model, i, t):
    return model.chp_heat[i,t] + model.storage_heat_discharging[i,t] >= demand[(i, t)]
model.demand_constraint = pyo.Constraint(scenarios, timesteps, rule=demand_constraint_rule)

# Objective function
def objective_function(model):
    return sum(probabilities[s] * sum(
        gas_price[t] * model.chp_gas[s, t] -  # Kosten für Gas
        heat_price[t] * model.storage_heat_discharging[s, t]  # Einnahmen aus Verkauf von Wärme
        for t in timesteps) for s in scenarios)
model.obj = pyo.Objective(rule=objective_function, sense=pyo.minimize)

# Solver
solver = pyo.SolverFactory('gurobi')
result = solver.solve(model)

# Ergebnisse anzeigen
model.display()

# Extract results for plotting
chp_power_results = {s: [pyo.value(model.chp_power[s, t]) for t in timesteps] for s in scenarios}
chp_heat_results = {s: [pyo.value(model.chp_heat[s, t]) for t in timesteps] for s in scenarios}
heat_demand_results = {s: [demand[(s, t)] for t in timesteps] for s in scenarios}
storage_heat_discharging_results = {s: [pyo.value(model.storage_heat_discharging[s, t]) for t in timesteps] for s in scenarios}
storage_content_results = {s: [pyo.value(model.storage_content[s, t]) for t in timesteps] for s in scenarios}

# Plotting CHP heat output, heat demand, and storage heat discharging for each scenario in separate plots
for s in scenarios:
    plt.figure(figsize=(12, 6))
    plt.plot(timesteps, chp_heat_results[s], label=f'Scenario {s} - Heat Output CHP', linestyle='--', marker='x')
    plt.plot(timesteps, heat_demand_results[s], label=f'Scenario {s} - Heat Demand Consumer', linestyle=':', marker='s')
    plt.plot(timesteps, storage_heat_discharging_results[s], label=f'Scenario {s} - Storage Heat Discharging', linestyle='-.', marker='o')
    plt.plot(timesteps, storage_content_results[s], label=f'Scenario {s} - Storage Content', linestyle='-', marker='d')
    plt.xlabel('Timesteps')
    plt.ylabel('Output / Demand (kW)')
    plt.title(f'Heat Output, Heat Demand, Storage Discharging, and Storage Content for Scenario {s}')
    plt.legend()
    plt.grid(True)
    plt.show()
