# Imports
from model import Model
import mpisppy.utils.sputils as sputils
import pyomo.environ as pyo

def main():
    
    # Some parameters 
    crops_multiplier = 1
    scen_count = 3

    scenario_creator_kwargs = {
        "use_integer": False,
        "crops_multiplier": crops_multiplier
    }

    scenario_names = ['Scenario' + str(i) for i in range(scen_count)]


    print("Initializing model...")
    my_model = Model()

    print("Load timeseries data...")
    my_model.load_timeseries_data()

    print("Setting Solver...")
    my_model.set_solver(solver_name="gurobi")

    print("Add objective...")
    my_model.add_objective()

    print("Creating model instance...")
    scenario_creator = my_model.scenario_creator

    print("Creating Extensive Formulation...")
    my_ef = sputils.create_EF(
        scenario_names = scenario_names,
        scenario_creator = scenario_creator,
        scenario_creator_kwargs=scenario_creator_kwargs
    )
    
    with open('output.txt', 'w') as f:
        my_ef.pprint(ostream=f)

    solver = pyo.SolverFactory("gurobi")
    solver.solve(my_ef, tee=True, symbolic_solver_labels=True, logfile='logfile.txt', load_solutions=True, report_timing=True)

    print("Solving...")
    print(f"EF objective: {pyo.value(my_ef.EF_Obj)}")

if __name__ == "__main__":
    main()

    


