# Imports
from model import Model, PATH_OUT_LOGS
import mpisppy.utils.sputils as sputils
import pyomo.environ as pyo
from datetime import datetime

def main():
    
    # Some parameters 
    scen_count = 1
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"{PATH_OUT_LOGS}logile_{timestamp}.log"
    options = {
        'solver': 'gurobi', 
        'TimeLimit':10.0, # TimeLimit Option added in ExtensiveForm Class
        'MIPGap':0.01, # MIPOpt Option added in ExtensiveForm Class
        'LogFile': log_filename # LogFile Option added in ExtensiveForm Class
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

    # Output the objective value for each scenario
    for sname, smodel in sputils.ef_scenarios(my_ef.ef):
        print(f"Scenario {sname}: {pyo.value(smodel.objective)}")


    print("Writing results...")
    my_model.write_results(my_ef.ef)

    my_model.write_objective_values(my_ef.ef)


    # Not needed for now
    # print("Saving results...")
    # my_model.save_results("results_test.csv")

if __name__ == "__main__":
    main()

    


