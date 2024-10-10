# Imports
from model_s import Model, PATH_OUT_LOGS
import mpisppy.utils.sputils as sputils
import pyomo.environ as pyo
from datetime import datetime

def main():
    
    # Some parameters 
    scen_count = 10
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"{PATH_OUT_LOGS}logile_{timestamp}.log"
    options = {
        'solver': 'gurobi', 
        'MIPGap':0.015, # MIPOpt Option added in ExtensiveForm Class
        'TimeLimit':100, # TimeLimit Option added in ExtensiveForm Class
        'LogFile': log_filename # LogFile Option added in ExtensiveForm Class
        }

    scenario_creator_kwargs = {}

    # Create scenario names
    scenario_names = ['Scenario' + str(i+1) for i in range(scen_count)]

    # Create the model
    my_model = Model()

    # Not needed for now, because Solver is defined through Extensive Form
    #print("Setting Solver...")
    #my_model.set_solver(solver_name=solver_name, **solver_kwargs)

    # Create the extensive form
    my_ef = my_model.create_extensive_form(options, scenario_names, scenario_creator_kwargs)
   
    # Write the extensive form to a file
    # with open('ef_output.txt', 'w') as f:
    #      my_ef.ef.pprint(ostream=f)
        
    # Solve the extensive form
    my_model.solve()
    
    # Output the objective value for the extensive form
    print(f"EF objective: {pyo.value(my_ef.ef.EF_Obj)}")

    # Output the root solution
    # print(my_ef.get_root_solution())

    # Output the objective value for each scenario
    for sname, smodel in sputils.ef_scenarios(my_ef.ef):
        print(f"Objectiv Value for {sname}: {pyo.value(smodel.objective)}")

    # Write the results to a file
    my_model.write_results(my_ef.ef)

    my_model.write_objective_values(my_ef.ef)

if __name__ == "__main__":
    main()

    


