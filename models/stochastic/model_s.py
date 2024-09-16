import sys
import os
import json
import re

import pandas as pd
import pyomo.environ as pyo
from pyomo.opt import SolverFactory
from pyomo.environ import *
from pyomo.network import *

from mpisppy.opt.ph import PH
from mpisppy.opt.lshaped import LShapedMethod
from mpisppy.opt.ef import ExtensiveForm
from mpisppy.utils.sputils import scenario_tree
from mpisppy.utils import config

import mpisppy.utils.sputils as sputils
import mpisppy.utils.solver_spec as solver_spec

import assets.chp_s as chp
import assets.boiler_s as boiler
import assets.heat_storage_s as heat_storage
import assets.grid_s as grid

# Load the config.json
with open ('../config.json', 'r') as f:
    config = json.load(f)

# Model Config
model_type = 'stochastic'
model_config = config['stochastic']

# Global Config
global_config = config['global']

# Paths
data_path = global_config['data_path']

# Declare paths
PATH_IN = os.path.join(data_path, model_config['input_path'])
PATH_OUT = os.path.join(data_path, model_config['output_path'])
PATH_OUT_LOGS = os.path.join(data_path, model_config['log_path'])
PATH_OUT_TIMESERIES = os.path.join(data_path, model_config['timeseries_path'])
PATH_OUT_OBJECTIVES = os.path.join(data_path, model_config['objectives_path'])
PATH_OUT_ROOT = os.path.join(data_path, model_config['root_path'])

# Heat Demand Data
FILE_HEAT_DEMAND = global_config['heat_demand_file']
FILE_HEAT_DEMAND_SCENARIOS = global_config['heat_demand_scenario_file']
DUMMY_FILE_HEAT_DEMAND = global_config['dummy_heat_demand_file']
DUMMY_FILE_HEAT_DEMAND_SCENARIOS = global_config['dummy_heat_demand_scenario_file']

# Declare constants
GAS_PRICE = global_config['gas_price'] # €/kWh  (HS)
POWER_PRICE = global_config['power_price'] # €/kWh (el)
HEAT_PRICE = global_config['heat_price'] # €/kWh (th)
CALORIFIC_VALUE_NGAS = global_config['calorific_value_ngas'] # kWh/m3

# CHP 
CHP_BONUS_SELF_CONSUMPTION= global_config['chp_bonus_self_consumption']  # €/kWhel
CHP_BONUS= global_config['chp_bonus']  # €/kWhel
CHP_INDEX_EEX= global_config['chp_index_eex']  # €/kWhel
ENERGY_TAX_REFUND_GAS= global_config['energy_tax_refund_gas']  # €/kWhHS
AVOIDED_GRID_FEES= global_config['avoided_grid_fees']  # €/kWhel
SHARE_SELF_CONSUMPTION= global_config['share_self_consumption'] # %
SHARE_FEED_IN= global_config['share_feed_in'] # %

# Costs
MAINTENANCE_COSTS = global_config['maintenance_cost'] # €/kWh (HS)

class Model:
    """Model class."""
    
    def __init__(self):
        """Initialize the model."""
        self.model = AbstractModel()
        self.instance = None
        self.ef_instance = None
        self.solver = None
        self.timeseries_data = None
        self.scenario_data = None
        self.results = None
        self._initialize_model_components()

    def _initialize_model_components(self):
        """Initialize basic model components."""
        self.model.t = Set(ordered=True)
        self._define_parameters()
        self._load_scenario_data()        
        self._define_assets()
        self._define_expressions()
        self._define_objective()

    def _define_parameters(self):
        """Define model parameters."""
        # Load Constants and the heat demand
        self.model.GAS_PRICE = Param(initialize=GAS_PRICE)
        self.model.POWER_PRICE = Param(initialize=POWER_PRICE)
        self.model.HEAT_PRICE = Param(initialize=HEAT_PRICE)
        self.model.heat_demand = Param(self.model.t)
        self.model.heat_demand_scenario = Param(self.model.t)
        self.model.delta_heat_demand = Param(self.model.t)
        self.model.probability = Param()
        
    def _define_assets(self):
        self._add_chp_assets()
        self._add_boiler_assets()
        self._add_heat_storage_assets()
        self._add_grid_assets()
    
    def _add_chp_assets(self):
        """Define CHP assets."""
        chp1 = chp.Chp('chp1', PATH_IN + '/assets/chp_operation.csv')
        chp1.add_to_model(self.model)
        
        chp2 = chp.Chp('chp2', PATH_IN + '/assets/chp_operation.csv')
        chp2.add_to_model(self.model)

    def _add_boiler_assets(self):
        """Define Boiler assets."""
        boiler1 = boiler.Boiler('boiler1', PATH_IN + '/assets/boiler_operation.csv')
        boiler1.add_to_model(self.model)

    def _add_heat_storage_assets(self):
        """Define Heat Storage assets."""
        heat_storage1 = heat_storage.HeatStorage('heat_storage1', PATH_IN + '/assets/heat_storage.csv')
        heat_storage1.add_to_model(self.model)

    def _add_grid_assets(self):
        """Define Grid assets."""
        ngas_grid = grid.NGasGrid('ngas_grid')
        power_grid = grid.ElectricalGrid('power_grid', PATH_IN + '/assets/power_grid.csv')
        heat_grid = grid.HeatGrid('heat_grid', PATH_IN + '/assets/heat_grid.csv')

        for grid_assets in [ngas_grid, power_grid, heat_grid]:
            grid_assets.add_to_model(self.model)
    
    def _add_arcs(self):
        """Add arcs to the instance."""
        self.instance.arc01 = Arc(
            source=self.instance.chp1.power_out,
            destination=self.instance.power_grid.power_in
        )
        self.instance.arc02 = Arc(
            source=self.instance.chp1.heat_out,
            destination=self.instance.heat_storage1.heat_in
        )
        # New
        self.instance.arc03 = Arc(
            source=self.instance.chp2.power_out,
            destination=self.instance.power_grid.power_in
        )
        # New
        self.instance.arc04 = Arc(
            source=self.instance.chp2.heat_out,
            destination=self.instance.heat_storage1.heat_in
        )
        # Add the new Arcs for the heat to heat_grid
        # ....

        # Old
        self.instance.arc05 = Arc(
            source=self.instance.heat_storage1.heat_out,
            destination=self.instance.heat_grid.heat_in
        )
        self.instance.arc06 = Arc(
            source=self.instance.boiler1.heat_out,
            destination=self.instance.heat_grid.heat_in
        )
        self.instance.arc07 = Arc(
            source=self.instance.ngas_grid.gas_out,
            destination=self.instance.boiler1.gas_in
        )
        self.instance.arc08 = Arc(
            source=self.instance.ngas_grid.gas_out,
            destination=self.instance.chp1.gas_in
        )
        
        # Second Stage Arcs
        self.instance.arc09 = Arc(
            source = self.instance.heat_storage1.dispatch_secondstage,
            destination=self.instance.heat_grid.heat_in_secondstage
        )


    def _expand_arcs(self):
        """Expands arcs and generate connection constraints."""
        TransformationFactory('network.expand_arcs').apply_to(self.instance)
    
    def _define_expressions(self):
        """Define Model expressions."""
        self.model.first_stage_cost = Expression(rule=self._first_stage_cost_rule)
        self.model.second_stage_cost = Expression(rule=self._second_stage_cost_rule)

    def _first_stage_cost_rule(self, model):
        return (
            self._gas_costs(model) + 
            self._maintenance_costs(model) - 
            self._power_revenue(model) - 
            self._heat_revenue(model) - 
            self._chp_revenue(model)
        )

    def _second_stage_cost_rule(self, model):
        return quicksum(model.heat_storage1.dispatch[t] * 1 for t in model.t)

    def _gas_costs(self, model):
            """ Calculate gas costs for CHP and Boiler."""
            gas_costs = (
            quicksum(model.chp1.gas[t] * model.GAS_PRICE * CALORIFIC_VALUE_NGAS for t in model.t) +
            quicksum(model.chp2.gas[t] * model.GAS_PRICE * CALORIFIC_VALUE_NGAS for t in model.t) +  # New
            quicksum(model.boiler1.gas[t] * model.GAS_PRICE * CALORIFIC_VALUE_NGAS for t in model.t)
            )
            return gas_costs
    
    def _maintenance_costs(self, model):
        """Calculate maintenance costs for CHP."""
        maintenance_costs = (
            quicksum(model.chp1.bin[t] * MAINTENANCE_COSTS for t in model.t) + 
            quicksum(model.chp2.bin[t] * MAINTENANCE_COSTS for t in model.t) # New
        )	
        return maintenance_costs

    def _power_revenue(self, model):
        """Calculate power revenue for CHP."""
        power_revenue = (
            quicksum(model.chp1.power[t] * model.POWER_PRICE for t in model.t) + 
            quicksum(model.chp2.power[t] * model.POWER_PRICE for t in model.t) # New
        )
        return power_revenue
    
    def _heat_revenue(self, model):
        """Calculate heat revenue for CHP and Boiler."""
        heat_revenue = (
        quicksum(model.chp1.heat[t] * model.HEAT_PRICE for t in model.t) +
        quicksum(model.chp2.heat[t] * model.HEAT_PRICE for t in model.t) + # New
        quicksum(model.boiler1.heat[t] * model.HEAT_PRICE for t in model.t)
        )
        return heat_revenue
    
    def _chp_revenue(self, model):
        """Calculate CHP revenue."""
        chp_bonus_for_self_consumption = (
            quicksum(model.chp1.power[t] * CHP_BONUS_SELF_CONSUMPTION * SHARE_SELF_CONSUMPTION for t in model.t) +
            quicksum(model.chp2.power[t] * CHP_BONUS_SELF_CONSUMPTION * SHARE_SELF_CONSUMPTION for t in model.t) # New
        )
        chp_bonus_for_feed_in = (
            quicksum(model.chp1.power[t] * CHP_BONUS * SHARE_FEED_IN for t in model.t) +
            quicksum(model.chp2.power[t] * CHP_BONUS * SHARE_FEED_IN for t in model.t) # New
        )
        chp_index = (
            quicksum((model.chp1.power[t] - model.chp1.power[t] * SHARE_SELF_CONSUMPTION) * CHP_INDEX_EEX for t in model.t) +
            quicksum((model.chp2.power[t] - model.chp2.power[t] * SHARE_SELF_CONSUMPTION) * CHP_INDEX_EEX for t in model.t) # New
        )
        avoided_grid_fees = (
            quicksum((model.chp1.power[t] - model.chp1.power[t] * SHARE_SELF_CONSUMPTION) * AVOIDED_GRID_FEES for t in model.t) +
            quicksum((model.chp2.power[t] - model.chp2.power[t] * SHARE_SELF_CONSUMPTION) * AVOIDED_GRID_FEES for t in model.t) # New
        )
        energy_tax_refund = (
            quicksum(model.chp1.gas[t] * CALORIFIC_VALUE_NGAS * ENERGY_TAX_REFUND_GAS for t in model.t) +
            quicksum(model.chp2.gas[t] * CALORIFIC_VALUE_NGAS * ENERGY_TAX_REFUND_GAS for t in model.t) # New
        )
        
        chp_revenue = (
            chp_bonus_for_self_consumption +
            chp_bonus_for_feed_in +
            chp_index +
            avoided_grid_fees +
            energy_tax_refund
        )
        return chp_revenue
    
    def _define_objective(self):
        """Add objective function to model."""
        def objective_expression_rule(model):
            return model.first_stage_cost + model.second_stage_cost
        self.model.objective = Objective(rule=objective_expression_rule,sense=minimize)  
    
    #####################################################################################

    def _load_scenario_data(self):
        """Load scenario data from files and load it in a dictionary."""  

        with open(f'{PATH_IN}demands/{FILE_HEAT_DEMAND}') as f:
            heat_demand_data = json.load(f)

        with open(f'{PATH_IN}demands/{FILE_HEAT_DEMAND_SCENARIOS}') as f:
            scenario_data = json.load(f)

        ################### For Testing ###################

        # with open(f'{PATH_IN}demands/{DUMMY_FILE_HEAT_DEMAND}') as f:
        #     heat_demand_data = json.load(f)

        # with open(f'{PATH_IN}demands/{DUMMY_FILE_HEAT_DEMAND_SCENARIOS}') as f:
        #     scenario_data = json.load(f)

        ################### For Testing ###################


        # Extrahiere t-Werte und konvertiere sie in int
        t_values = list(map(int, heat_demand_data['heat_demand'].keys()))
        heat_demand = {int(k): v for k, v in heat_demand_data['heat_demand'].items()}

        # Initialisiere das Hauptdictionary
        self.scenario_data = {}

        for scenario_name, scenario_values in scenario_data.items():
            try:
                probability = scenario_values['Probability']
            
                heat_demand_scenario = {int(hour): scenario_values[str(hour)] for hour in t_values}
                delta_heat_demand = {
                    int(hour): heat_demand[hour] - heat_demand_scenario[hour] for hour in t_values
                }
                
                self.scenario_data[scenario_name] = {
                    't': {None: t_values},
                    'heat_demand': heat_demand,
                    'heat_demand_scenario': heat_demand_scenario,
                    'delta_heat_demand': delta_heat_demand,
                    'probability': {None: probability}
                }
            except KeyError as e:
                print(f"Fehler im Szenario {scenario_name}: fehlender Schlüssel {e}")
            except Exception as e:
                print(f"Allgemeiner Fehler im Szenario {scenario_name}: {e}")

    
    def _scenario_creator(self, scenario_name):
        """Create a scenario model."""
        print("=" * 40)
        print(f"Creating scenario: {scenario_name}...")
        print("=" * 40)
        self.instance = self._build_scenario_model(scenario_name)
        
        # Variable mit Index t anlegen
        
        # varlist = [self.instance.chp1.gas]
        
        varlist = [self.instance.chp1.bin, 
                   self.instance.chp1.power,
                   self.instance.chp1.gas,
                   self.instance.chp1.heat,
                   self.instance.chp1.eta_th,
                   self.instance.chp1.eta_el,
                   self.instance.boiler1.bin,
                   self.instance.boiler1.heat,
                   self.instance.boiler1.gas,
                   self.instance.boiler1.eta_th,
                   self.instance.boiler1.y1,
                   self.instance.boiler1.y2,
                   self.instance.heat_storage1.heat_charge,
                   self.instance.heat_storage1.bin_charge,
                   self.instance.heat_storage1.heat_discharge,
                   self.instance.heat_storage1.bin_discharge,
                   self.instance.heat_storage1.heat_balance,
                   self.instance.heat_storage1.heat_capacity,
                   self.instance.power_grid.power_balance,
                   self.instance.power_grid.power_supply,
                   self.instance.power_grid.power_feedin,
                   self.instance.ngas_grid.gas_balance,
                   self.instance.heat_grid.heat_balance,
                   self.instance.heat_grid.heat_supply,
                   self.instance.heat_grid.heat_feedin
        ]

        # Add the root node to the instance
        sputils.attach_root_node(self.instance, self.instance.first_stage_cost, varlist)

        # Add Probability to the instance
        self.instance._mpisppy_probability = value(self.instance.probability)

        ###################### Start Debugging Print ######################

        # output_filename = f'output_{scenario_name}.txt'

        # print(f"Writing instance {output_filename} ...")
        # with open(output_filename, 'w') as f:
        #     self.instance.pprint(ostream=f)

        # for t in self.instance.t:
        #     print(f"Time {t}: {pyo.value(self.instance.heat_demand_scenario[t])}")

        # with open('constraints_output.txt', 'w') as f:
        #     # Iteriere über alle aktiven Constraints in der Modellinstanz
        #     for con in self.instance.component_objects(Constraint, active=True):
        #         # Schreibe den Namen der Constraint-Komponente in die Datei
        #         f.write(f"Constraint: {con.name}\n")
        #         f.write("Details:\n")
        #         # Nutze pprint, um die Details der Constraint in die Datei zu schreiben
        #         con.pprint(ostream=f)
        #         f.write("____________________________________\n")

        ###################### End Debugging Print ######################

        return self.instance

    def _build_scenario_model(self, scenario_name):
        """Build the scenario model. Each scenario has its own model."""

        # Load the dictionary with the heat demand scenarios
        if scenario_name in self.scenario_data:
            scenario_data = self.scenario_data[scenario_name]
            # Importent for the needed format for instance creation
            scenario_data = {
                None: scenario_data
            }
        else:
            raise RuntimeError(f"Scenario: {scenario_name} not found in scenario data")
        
        # Create the model instance
        self.instance = self.model.create_instance(data=scenario_data, name=scenario_name)    
        
        # Add Arcs to the model
        self._add_arcs()

        # Expand arcs and generate connection constraints
        self._expand_arcs()
        
        ###################### Start Debugging Print ######################

        # output_filename = f'output_model_{scenario_name}.txt'

        # with open(output_filename, 'w') as f:
        #     self.instance.pprint(ostream=f)

        ###################### End Debugging Print ######################

        return self.instance

    # Not needed for now
    def set_solver(self, solver_name, **kwargs):
        """Set solver for the model."""
        self.solver = SolverFactory(solver_name)
        for key in kwargs:
            self.solver.options[key] = kwargs[key]    
    

    def create_extensive_form(self, options , all_scenario_names, scenario_creator_kwargs):
        """Create the extensive form."""
        self.ef_instance = ExtensiveForm(
            options,
            all_scenario_names,
            scenario_creator=self._scenario_creator,
            model_name='4DEnergie',
            scenario_creator_kwargs=scenario_creator_kwargs
        )
        return self.ef_instance

    def solve(self):
        """Solve the model."""
        self.results = self.ef_instance.solve_extensive_form(tee=True)

    def _extract_scenario_date(self, file):
        """Extract Heat Demand date from the file name."""
        numbers = re.findall(r'\d+', file)
        extracted_numbers = ''.join(numbers)
        return int(extracted_numbers)

    def write_results(self, ef):
        """Write results to file."""

        # Extract the Date from the file name
        extracted_date = self._extract_scenario_date(FILE_HEAT_DEMAND)

        # Root solution extraction
        root_solution = self.ef_instance.get_root_solution()

        # Initialize a dictionary to store variables by their time index
        root_solution_dict = {}

        # Process the root solution to organize it in a tabular format
        for var_name, value_root in root_solution.items():
            # Extract variable name and time index (e.g., 'chp1.gas[1]' -> 'chp1.gas' and '1')
            base_name, index = var_name.split('[')
            index = index.strip(']')
            
            if base_name not in root_solution_dict:
                root_solution_dict[base_name] = {}
            
            # Store the value in the dictionary with the time index
            root_solution_dict[base_name][int(index)] = value_root

        # Convert the dictionary into a DataFrame for tabular representation
        df_root_solution = pd.DataFrame(root_solution_dict)
        df_root_solution.index.name = 't'  # Setting 't' as the name of the index
        df_root_solution = df_root_solution.sort_index()

        # Save the root solution to a CSV file
        root_output_file = f's_{extracted_date}_rs.csv'
        df_root_solution.to_csv(PATH_OUT_ROOT + root_output_file)


        for sname, smodel in sputils.ef_scenarios(self.ef_instance.ef):
            df_params = pd.DataFrame()
            df_vars = pd.DataFrame()
            df_output = pd.DataFrame()
        
            for params in smodel.component_objects(Param, active=True):
                name = params.name
                if len(params) == 1:
                    single_value = value(list(params.values())[0])
                    df_params[name]= [single_value for t in smodel.t]
                else:
                    df_params[name] = [value(params[t]) for t in smodel.t]
            
            for vars in smodel.component_objects(Var, active = True):
                name = vars.name
                df_vars[name] = [value(vars[t]) for t in smodel.t]

            df_output = pd.concat([df_params, df_vars], axis=1)
            df_output.index = smodel.t
            df_output.index.name = 't'
            

            output_file = f's_{sname}_{extracted_date}_ts.csv'
            df_output.to_csv(PATH_OUT_TIMESERIES + output_file)
            #print(f'Results for {sname} written to {output_file}')

            
    
    def write_objective_values(self, ef):
        """Writes he Objective-Value for each scenario."""
        results = []
        
        for sname, smodel in sputils.ef_scenarios(ef):
            objective_value = pyo.value(smodel.objective)
            results.append({'Scenario:': sname, 'ObjectiveValue': objective_value})

        # Creates a DataFrame from the results list
        df_results = pd.DataFrame(results)

        if not os.path.exists(PATH_OUT_OBJECTIVES):
            os.makedirs(PATH_OUT_OBJECTIVES)
        
        extracted_numbers = self._extract_scenario_date(FILE_HEAT_DEMAND)

        # Speichere den DataFrame als CSV-Datei
        output_filename = f"{PATH_OUT_OBJECTIVES}s_{extracted_numbers}_obj.csv"
        df_results.to_csv(output_filename, index=False)