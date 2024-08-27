# Imports
from model import Model
import mpisppy.utils.sputils as sputils
import pyomo.environ as pyo

def main():
    
    # Some parameters 
    scen_count = 3
    solver_name = "gurobi"

    scenario_creator_kwargs = {
        "use_integer": False,
    }

    scenario_names = ['Scenario' + str(i) for i in range(scen_count)]


    print("Initializing model...")
    my_model = Model()

    print("Load timeseries data...")
    my_model.load_timeseries_data()

    # print("Load scenario data...")
    # my_model.load_stochastic_data()
    
    print("Setting Solver...")
    my_model.set_solver(solver_name=solver_name)

    print("Add objective...")
    my_model.add_objective()

    print("Creating Extensive Formulation...")
    #my_ef = my_model.create_extensive_form(scenario_names, scenario_creator_kwargs)
    
    options = {"solver": "gurobi"}

    my_ef = my_model.create_extensive_form2(options, scenario_names, scenario_creator_kwargs)



    print("Writing instance output.txt ...")
    with open('ef_output.txt', 'w') as f:
        my_ef.ef.pprint(ostream=f)
        

    print("Solving...")
    my_model.solve2()
    
    # print(f"EF objective: {pyo.value(my_ef.EF_Obj)}")

    print("Writing results...")
    my_model.write_results()

    # print("Saving results...")
    # my_model.save_results("results_test.csv")

if __name__ == "__main__":
    main()

    


