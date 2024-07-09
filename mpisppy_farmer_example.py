from pyomo.environ import *
from mpisppy.opt.ph import PH
from mpisppy.opt.lshaped import LShapedMethod
from mpisppy.utils.sputils import scenario_tree
import mpisppy.utils.sputils as sputils
import numpy as np

# Daten

# Land
land_total = 500 # in ha

# Mindestanforderungen
min_wheat = 200 # in t
min_corn = 240 # in t

# Verkaufspreis in €/t
price_wheat = 170
price_corn = 150 
price_beet = 36 
price_beet_excess = 10 

# Kaufpreise in €/t
purchase_price_wheat = 238
purchase_price_corn = 210 


# Anpflanzungskosten in €/ha
cost_wheat = 150
cost_corn = 230
cost_beet = 260

# Szenarien
scenarios = {
    'good': {'prob': 1/10, 'yield_wheat': 3.0, 'yield_corn': 3.6, 'yield_beet': 24},
    'average': {'prob': 1/5, 'yield_wheat': 2.5, 'yield_corn': 3.0, 'yield_beet': 20},
    'bad': {'prob': 1/3, 'yield_wheat': 2.0, 'yield_corn': 2.4, 'yield_beet': 16},
}

# Szenario-Erstellungsfunktion
def scenario_creator(scenario_name, node_names=None, cb_data=None):
    scenario_data = scenarios[scenario_name]
    model = ConcreteModel()

    # First-Stage Variablen
    model.x_wheat_flaeche = Var(within=NonNegativeReals)
    model.x_corn_flaeche = Var(within=NonNegativeReals)
    model.x_beet_flaeche = Var(within=NonNegativeReals)

    # Second-Stage Variablen - Verkaufsmengen
    model.w_wheat_verkauf = Var(within=NonNegativeReals)
    model.w_corn_verkauf = Var(within=NonNegativeReals)
    model.w_beet_verkauf = Var(within=NonNegativeReals)
    model.w_beet_excess_verkauf = Var(within=NonNegativeReals)
    
    # Second-Stage Variablen - Ankaufsmengen
    model.y_wheat_ankauf = Var(within=NonNegativeReals)
    model.y_corn_ankauf = Var(within=NonNegativeReals)

    # Nebenbedingungen
    model.land_constraint = Constraint(expr=model.x_wheat_flaeche + model.x_corn_flaeche + model.x_beet_flaeche <= land_total)
    
    model.wheat_constraint = Constraint(expr=scenario_data['yield_wheat'] * model.x_wheat_flaeche + model.y_wheat_ankauf - model.w_wheat_verkauf >= min_wheat)
    model.corn_constraint = Constraint(expr=scenario_data['yield_corn'] * model.x_corn_flaeche + model.y_corn_ankauf - model.w_corn_verkauf >= min_corn)
    model.beet_constraint = Constraint(expr=model.w_beet_verkauf + model.w_beet_excess_verkauf <= scenario_data['yield_beet'] * model.x_beet_flaeche)
    model.beet_quota_constraint = Constraint(expr=model.w_beet_verkauf <= 6000)

    print("Ausgabe:")
    print(scenario_data['yield_wheat'], scenario_data['yield_corn'], scenario_data['yield_beet'])

    # First-Stage Kosten
    model.first_stage_cost = cost_wheat * model.x_wheat_flaeche + cost_corn * model.x_corn_flaeche + cost_beet * model.x_beet_flaeche

    # Second-Stage Kosten
    model.second_stage_cost = (purchase_price_wheat * model.y_wheat_ankauf - price_wheat * model.w_wheat_verkauf +
                         purchase_price_corn * model.y_corn_ankauf - price_corn * model.w_corn_verkauf -
                         price_beet * model.w_beet_verkauf - price_beet_excess * model.w_beet_excess_verkauf)

    # Zielfunktion
    model.objective = Objective(expr=model.first_stage_cost + model.second_stage_cost, sense=minimize)

    sputils.attach_root_node(model, model.first_stage_cost, [model.x_wheat_flaeche, model.x_corn_flaeche, model.x_beet_flaeche])
    model._mpisppy_probability = scenario_data['prob']

    return model

# Erstellen der Szenarien
all_scenario_names = list(scenarios.keys())

#----------------------------------------------------------------------------------------------------------------------------

# L-Shaped Method Optionen
bounds = {name: -432000 for name in all_scenario_names}
options = {
    "root_solver": "gurobi",
    "sp_solver": "gurobi",
    "sp_solver_options" : {"threads" : 2},
    "valid_eta_lb": bounds,
    "max_iter": 10,
}

ls = LShapedMethod(options, all_scenario_names, scenario_creator)
result = ls.lshaped_algorithm()

variables = ls.gather_var_values_to_rank0()
for ((scen_name, var_name), var_value) in variables.items():
    print(scen_name, var_name, var_value)


ls.write_tree_solution("output/data/lshaped_res_all_stages")
ls.write_first_stage_solution("output/data/lshaped_res_first_stage/lshaped_res_first_stage.csv")



#----------------------------------------------------------------------------------------------------------------------------

# # Progressive Hedging Optionen
# ph_options = {
#     "solver_name": "gurobi",
#     "PHIterLimit": 100,
#     "defaultPHrho": 10,
#     "convthresh": 1e-7,
#     "verbose": False,
#     "display_progress": False,
#     "display_timing": False,
#     "iter0_solver_options": dict(),
#     "iterk_solver_options": dict(),
# }

# # PH Solver aufrufen
# ph = PH(ph_options, 
#         all_scenario_names, 
#         scenario_creator
# )

# ph.ph_main()

# variables = ph.gather_var_values_to_rank0()
# for (scenario_name, variable_name) in variables:
#     variable_value = variables[scenario_name, variable_name]
#     print(scenario_name, variable_name, variable_value)

# ph.write_first_stage_solution("first_stage_sol")

# # # Ergebnisse anzeigen
# # for sn in all_scenario_names:
# #     print(f"Scenario {sn}:")
# #     for var in ph.local_scenarios[sn].component_data_objects(Var, descend_into=True):
# #         print(f"  {var.name} = {var.value}")

# # # Objektivwert
# # print("Objective value:", ph.Eobjective)

