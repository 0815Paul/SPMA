from pyomo.environ import *
import numpy as np

# Daten

# Land
land_total = 500 # in ha

# Anpflanzungskosten in €/ha
cost_wheat = 150
cost_corn = 230
cost_beet = 260

# Ertrag in Tonnen/ha
yield_wheat = 5
yield_corn = 8
yield_beet = 12

# Minimaler Gesamtbedarf in Tonnen
min_wheat_demand = 600
min_corn_demand = 1000
min_beet_demand = 1200

# Modell erstellen
model = ConcreteModel()

# Entscheidungsvariablen
model.x_wheat_flaeche = Var(within=NonNegativeReals)
model.x_corn_flaeche = Var(within=NonNegativeReals)
model.x_beet_flaeche = Var(within=NonNegativeReals)

# Nebenbedingungen
model.land_constraint = Constraint(expr=model.x_wheat_flaeche + model.x_corn_flaeche + model.x_beet_flaeche <= land_total)
model.wheat_demand_constraint = Constraint(expr=model.x_wheat_flaeche * yield_wheat >= min_wheat_demand)
model.corn_demand_constraint = Constraint(expr=model.x_corn_flaeche * yield_corn >= min_corn_demand)
model.beet_demand_constraint = Constraint(expr=model.x_beet_flaeche * yield_beet >= min_beet_demand)

# Zielfunktion
model.objective = Objective(expr= cost_wheat * model.x_wheat_flaeche + cost_corn * model.x_corn_flaeche + cost_beet * model.x_beet_flaeche, sense=minimize)

# Solver aufrufen
solver = SolverFactory('gurobi')
results = solver.solve(model, tee=True)

# Ergebnisse ausgeben
print("Optimale Flächenzuteilung:")
print(f"Weizenfläche: {model.x_wheat_flaeche():.2f} ha")
print(f"Maisfläche: {model.x_corn_flaeche():.2f} ha")
print(f"Zuckerrübenfläche: {model.x_beet_flaeche():.2f} ha")
print(f"Minimale Kosten: {model.objective():.2f} €")