import pyomo.environ as pyo
import matplotlib.pyplot as plt

# Szenarien und Wahrscheinlichkeiten
scenarios = [1, 2, 3]
timesteps = [1, 2, 3, 4, 5]
probabilities = {1: 1/3, 2: 1/3, 3: 1/3}
demand = {
    (1, 1): 50, (1, 2): 60, (1, 3): 55, (1, 4): 50, (1, 5): 45,
    (2, 1): 75, (2, 2): 85, (2, 3): 80, (2, 4): 75, (2, 5): 70,
    (3, 1): 100, (3, 2): 100, (3, 3): 95, (3, 4): 120, (3, 5): 90
}

# Parameter

# Prices in €/MWh
gas_price = {1:9.22, 2:8.84, 3:8.67, 4:8.12, 5:9.49} #per MWh
#gas_price_const = 8.5 #per MWh
power_price = {1:90.8, 2:96.2, 3:92.3, 4:88.7, 5:91.1} #per MWh
#power_price_const = 90 #per MWh	

# CHP
chp_power_max = 62.424 # in kW
chp_power_min = 13.410 # in kW
chp_gas_max = 156.328 # in kW
chp_gas_min = 64.794 # in kW
chp_heat_max = 82.000 # in kW
chp_heat_min = 41.000 # in kW



# Modell erstellen
model = pyo.ConcreteModel()

# CHP
model.chp_bin = pyo.Var(scenarios, timesteps, within=Binary)
model.chp_gas = pyo.Var(scenarios, timesteps, within=NonNegativeReals)
model.chp_power = pyo.Var(scenarios, timesteps, within=NonNegativeReals)
model.chp_heat = pyo.Var(scenarios, timesteps, within=NonNegativeReals)

# Heat Storage
model.storage_heat_charging = pyo.Var(scenarios, timesteps, within=NonNegativeReals)
model.storage_heat_discharging = pyo.Var(scenarios, timesteps, within=NonNegativeReals)
model.storage_content = pyo.Var(scenarios, timesteps, within=NonNegativeReals)


# bis hierhin bin ich gekommen
# ----------------------------------------------------------------------------------------------------------------------------

c_elek = 20  # Kosten des Strombezugs
c_gas = 10   # Kosten des Gasbezugs
c_bhkw = 5   # Kosten der BHKW-Wärmeerzeugung
c_kessel = 8 # Kosten der Kessel-Wärmeerzeugung
c_speicher = 2 # Kosten der Wärmespeicherung
y_bhkw_max = 80
y_kessel_max = 90
z_speicher_max = 50


# Variablen
model.x_elek = pyo.Var(scenarios, timesteps, within=pyo.NonNegativeReals)
model.x_gas = pyo.Var(scenarios, timesteps, within=pyo.NonNegativeReals)
model.y_bhkw = pyo.Var(scenarios, timesteps, within=pyo.NonNegativeReals)
model.y_kessel = pyo.Var(scenarios, timesteps, within=pyo.NonNegativeReals)
model.z_speicher = pyo.Var(scenarios, timesteps, within=pyo.NonNegativeReals)

# Zielfunktion
def objective_rule(model):
    return sum(probabilities[i] * (c_elek * model.x_elek[i,t] + c_gas * model.x_gas[i,t] + c_bhkw * model.y_bhkw[i,t] + c_kessel * model.y_kessel[i,t] + c_speicher * model.z_speicher[i,t]) for i in scenarios for t in timesteps)
model.objective = pyo.Objective(rule=objective_rule, sense=pyo.minimize)

# Nebenbedingungen

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

def heat_depends_on_power_rule(model, i, t):
    a = (chp_heat_max - chp_heat_min) / (chp_power_max - chp_power_min)
    b = chp_heat_max - a * chp_power_max
    return model.chp_heat[i,t] == a * model.chp_power[i,t] + b * model.chp_bin[i,t]



def demand_constraint_rule(model, i, t):
    return model.y_bhkw[i,t] + model.y_kessel[i,t] + model.z_speicher[i,t] >= demand[(i, t)]
model.demand_constraint = pyo.Constraint(scenarios, timesteps, rule=demand_constraint_rule)

def bhkw_limit_rule(model, i, t):
    return model.y_bhkw[i,t] <= y_bhkw_max
model.bhkw_limit = pyo.Constraint(scenarios, timesteps, rule=bhkw_limit_rule)

def kessel_limit_rule(model, i, t):
    return model.y_kessel[i,t] <= y_kessel_max
model.kessel_limit = pyo.Constraint(scenarios, timesteps, rule=kessel_limit_rule)

def speicher_limit_rule(model, i, t):
    return model.z_speicher[i,t] <= z_speicher_max
model.speicher_limit = pyo.Constraint(scenarios, timesteps, rule=speicher_limit_rule)

# Solver
solver = pyo.SolverFactory('gurobi')
result = solver.solve(model)

# Ergebnisse anzeigen
#model.display()

# Ergebnisse extrahieren
x_elek_values = {(i, t): pyo.value(model.x_elek[i, t]) for i in scenarios for t in timesteps}
x_gas_values = {(i, t): pyo.value(model.x_gas[i, t]) for i in scenarios for t in timesteps}
y_bhkw_values = {(i, t): pyo.value(model.y_bhkw[i, t]) for i in scenarios for t in timesteps}
y_kessel_values = {(i, t): pyo.value(model.y_kessel[i, t]) for i in scenarios for t in timesteps}
z_speicher_values = {(i, t): pyo.value(model.z_speicher[i, t]) for i in scenarios for t in timesteps}

# Ergebnisse visualisieren
for i in scenarios:
    plt.figure(figsize=(12, 6))
    plt.plot(timesteps, [x_elek_values[(i, t)] for t in timesteps], label='Strombezug')
    plt.plot(timesteps, [x_gas_values[(i, t)] for t in timesteps], label='Gasbezug')
    plt.plot(timesteps, [y_bhkw_values[(i, t)] for t in timesteps], label='BHKW Wärmeerzeugung')
    plt.plot(timesteps, [y_kessel_values[(i, t)] for t in timesteps], label='Kessel Wärmeerzeugung')
    plt.plot(timesteps, [z_speicher_values[(i, t)] for t in timesteps], label='Wärmespeicherung')
    plt.xlabel('Zeitschritt')
    plt.ylabel('Energie (Einheiten)')
    plt.title(f'Szenario {i}')
    plt.legend()
    plt.grid(True)
    plt.show()