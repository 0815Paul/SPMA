# Standard library imports
import os
import glob
from datetime import datetime

# Third-party imports
import pyomo.environ as pyo
import mpisppy.utils.sputils as sputils

# Local imports
from model_s import Model, PATH_IN, FILE_HEAT_DEMAND, FILE_HEAT_DEMAND_SCENARIOS


def extract_scenario_info(file):
    """Extract the start date, end date, and period from the file name."""
    base_name = os.path.basename(file)
    if base_name.startswith('heat_demand_') and base_name.endswith('.json'):
        extracted = base_name[len('heat_demand_') : -len('.json')]
        # Split the string
        try:
            start_to_end, period = extracted.rsplit('_', 1)
            start_date, end_date = start_to_end.split('_to_')
            return start_date, end_date, period
        except ValueError:
            # Error during splitting
            return None, None, None
    else:
        return None, None, None


def main():
    """Main function to run the model."""
    
    ####################### Options ########################

    # Set to True to enable automatic processing
    automate_processing = True 

    # Do you want to use the weighted heat demand?
    Model.USE_WEIGHTED_HEAT_DEMAND = False

    # Do you want to use a special case?
    USE_SPECIAL_CASE = False

    # Define the number of scenarios (only relevant if automate_processing = False)
    scen_count = 10

    #################### End of Options ####################    
 

    # Define the solver and options
    solver_name = 'gurobi'
    solver_options = {
        'MIPGap': 0.01,
        'TimeLimit': 1000,
    }

    if USE_SPECIAL_CASE:
        Model.SPECIAL_CASE = '_USE_EXT_COST_10'
    else:
        Model.SPECIAL_CASE = ''

    if automate_processing:
        # Path to the directory containing heat demand files
        heat_demand_files = glob.glob(
            os.path.join(PATH_IN, 'demands', 'heat_demand_*.json')
        )

        # Dictionary to store matched files
        matched_files = {}

        for heat_demand_file in heat_demand_files:
            # Extract the key part of the filename
            base_name = os.path.basename(heat_demand_file)
            key = base_name[len('heat_demand_') : -len('.json')]

            # Corresponding scenario file
            scenario_file = os.path.join(
                PATH_IN, 'demands', f'reduced_heat_demand_scenarios_{key}.json'
            )
            if os.path.exists(scenario_file):
                matched_files[heat_demand_file] = scenario_file
            else:
                print(f"Warning: Scenario file for {heat_demand_file} not found.")

        # Iterate over the matched files
        for heat_demand_file, scenario_file in matched_files.items():
            # Extract scenario information from the filename
            start_date, end_date, period = extract_scenario_info(heat_demand_file)

            print(f"Processing scenario from {start_date} to {end_date} ({period})")

            # Create a model instance
            model = Model(heat_demand_file, scenario_file)

            # Set solver options
            solver_options_with_log = solver_options.copy()
            solver_options_with_log['LogFile'] = model.logfile_name

            # Create scenario creator arguments
            scenario_creator_kwargs = {}

            # Create a list of scenario names
            scenario_names = [f'Scenario{i + 1}' for i in range(scen_count)]

            # Create the extensive form
            options = {
                'solver': solver_name,
                'solver_options': solver_options_with_log,
            }
            ef_instance = model.create_extensive_form(
                options, scenario_names, scenario_creator_kwargs
            )

            # Solve the model
            model.solve()

            # Output the objective value for the extensive form
            print(f"EF objective: {pyo.value(ef_instance.ef.EF_Obj)}")

            # Output the objective value for each scenario
            for sname, smodel in sputils.ef_scenarios(ef_instance.ef):
                print(f"Objective Value for {sname}: {pyo.value(smodel.objective)}")

            # Write results
            model.write_results(ef_instance.ef)

            # Write objective values
            model.write_objective_values(ef_instance.ef)

            print(
                f"\n### Scenario {start_date}_to_{end_date}_{period} has been processed. ###"
            )

    else:
        # Specify the filenames of the desired files here
        heat_demand_filename = FILE_HEAT_DEMAND  # or directly specify the filename as a string
        scenario_filename = FILE_HEAT_DEMAND_SCENARIOS  # or directly specify the filename as a string

        # Construct paths
        heat_demand_file = os.path.join(PATH_IN, 'demands', heat_demand_filename)
        scenario_file = os.path.join(PATH_IN, 'demands', scenario_filename)

        # Check if the files exist
        if not os.path.exists(heat_demand_file):
            print(f"The file {heat_demand_file} was not found.")
            return
        if not os.path.exists(scenario_file):
            print(f"The file {scenario_file} was not found.")
            return

        # Create a model instance and pass the filenames
        model = Model(heat_demand_file, scenario_file)

        # Set solver options
        solver_options_with_log = solver_options.copy()
        solver_options_with_log['LogFile'] = model.logfile_name

        # Create scenario creator arguments
        scenario_creator_kwargs = {}

        # Create a list of scenario names
        all_scenario_names = list(model.scenario_data.keys())

        # Create the extensive form
        options = {
            'solver': solver_name,
            'solver_options': solver_options_with_log,
        }
        ef_instance = model.create_extensive_form(
            options, all_scenario_names, scenario_creator_kwargs
        )

        # Solve the model
        model.solve()

        # Write results
        model.write_results(ef_instance)

        # Write objective values
        model.write_objective_values(ef_instance.ef)

        print(
            f"\n### Scenario {model.start_date}_to_{model.end_date}_{model.period} has been processed. ###"
        )


if __name__ == "__main__":
    main()
