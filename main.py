# Imports
from model import Model
import mpisppy.utils.sputils as sputils
import pyomo.environ as pyo

def main():
    
    # Some parameters 
    scen_count = 3
    options = {
        "solver": "gurobi",
        'MIPGap':0.5, 
        'TimeLimit':30
        }
    solver_kwargs = {
        'MIPGap':0.5, 
        'TimeLimit':30
        }
    scenario_creator_kwargs = {}

    # Create scenario names
    scenario_names = ['Scenario' + str(i+1) for i in range(scen_count)]

    print("Initializing model...")
    my_model = Model()

    # Not needed for now, because Solver is defined through Extensive Form
    #print("Setting Solver...")
    #my_model.set_solver(solver_name=solver_name, **solver_kwargs)

    print("Add objective...")
    my_model.add_objective()

    print("Creating Extensive Formulation...")
    my_ef = my_model.create_extensive_form(options, scenario_names, scenario_creator_kwargs)
   
    print("Writing instance output.txt ...")
    with open('ef_output.txt', 'w') as f:
        my_ef.ef.pprint(ostream=f)
        
    print("Solving...")
    my_model.solve()
    
    print(f"EF objective: {pyo.value(my_ef.ef.EF_Obj)}")

    print("Writing results...")
    my_model.write_results()

    # Not needed for now
    # print("Saving results...")
    # my_model.save_results("results_test.csv")

if __name__ == "__main__":
    main()

    


