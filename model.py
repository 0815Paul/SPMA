import sys
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
import os
import json

import mpisppy.utils.sputils as sputils
import mpisppy.utils.solver_spec as solver_spec

import assets.chp as chp
import assets.boiler as boiler
import assets.heat_storage as heat_storage
import assets.grid as grid




# Path
PATH_IN = 'data/input/'
PATH_IN_PP = 'data/preprocessing/'
PATH_OUT = 'data/output/'
PATH_OUT_LOGS = 'data/output/logs/'
PATH_OUT_TIMESERIES = 'data/output/timeseries/'
PATH_OUT_OBJECTIVES = 'data/output/objectives/'

# Declare constants
GAS_PRICE = 0.1543 # €/kWh  (HS)
POWER_PRICE = 0.251 # €/kWh (el)
HEAT_PRICE = 0.105 # €/kWh (th)
CALORIFIC_VALUE_NGAS = 10 # kWh/m3

# CHP 
CHP_BONUS_SELF_CONSUMPTION= 0.08  # €/kWhel
CHP_BONUS= 0.16  # €/kWhel
CHP_INDEX_EEX= 0.1158  # €/kWhel
ENERGY_TAX_REFUND_GAS= 0.0055  # €/kWhHS
AVOIDED_GRID_FEES= 0.0097  # €/kWhel
SHARE_SELF_CONSUMPTION= 0.03 # %
SHARE_FEED_IN= 0.97 # %

# Costs
MAINTENANCE_COSTS = 1.8 # €/kWh (HS)


class Model:
    """Model class."""
    
    def __init__(self):
        """Initialize the model."""
        print("Initializing model...")
        self.PATH_IN = PATH_IN
        self.PATH_IN_PP= PATH_IN_PP
        self.PATH_OUT = PATH_OUT
        self.PATH_OUT_LOGS = PATH_OUT_LOGS
        self.PATH_OUT_TIMESERIES = PATH_OUT_TIMESERIES
        self.PATH_OUT_OBJECTIVES = PATH_OUT_OBJECTIVES
        self.model = AbstractModel()
        self.instance = None
        self.ef_instance = None
        self.solver = None
        self.timeseries_data = None
        self.results = None
        self.results_data = None
        self._initialize_model_components()

    def _initialize_model_components(self):
        """Initialize basic model components."""
        self.model.t = Set(ordered=True)
        self._define_parameters()
        self._define_assets()
        self._define_expressions()
        self._calculate_delta_heat_demand()
        # self._define_stochastic_parameters()


    def _define_parameters(self):
        """Define model parameters."""
        # Load Constants and the heat demand
        self.model.GAS_PRICE = Param(initialize=GAS_PRICE)
        self.model.POWER_PRICE = Param(initialize=POWER_PRICE)
        self.model.HEAT_PRICE = Param(initialize=HEAT_PRICE)
        self.model.heat_demand = Param(self.model.t)
        
    def _define_assets(self):
        self._add_chp_assets()
        self._add_boiler_assets()
        self._add_heat_storage_assets()
        self._add_grid_assets()
    
    def _add_chp_assets(self):
        """Define CHP assets."""
        chp_filepaths = [self.PATH_IN + '/assets/chp_operation.csv']
        chp1 = chp.Chp('chp1', chp_filepaths)
        chp1.add_to_model(self.model)

    def _add_boiler_assets(self):
        """Define Boiler assets."""
        boiler_filepaths = [self.PATH_IN + '/assets/boiler_operation.csv']
        boiler1 = boiler.Boiler('boiler1', boiler_filepaths)
        boiler1.add_to_model(self.model)

    def _add_heat_storage_assets(self):
        """Define Heat Storage assets."""
        heat_storage1 = heat_storage.HeatStorage('heat_storage1', self.PATH_IN + '/assets/heat_storage.csv')
        heat_storage1.add_to_model(self.model)

    def _add_grid_assets(self):
        """Define Grid assets."""
        ngas_grid = grid.NGasGrid('ngas_grid')
        power_grid = grid.ElectricalGrid('power_grid', self.PATH_IN + '/assets/power_grid.csv')
        heat_grid = grid.HeatGrid('heat_grid', self.PATH_IN + '/assets/heat_grid.csv')

        for grid_assets in [ngas_grid, power_grid, heat_grid]:
            grid_assets.add_to_model(self.model)

    def _json_to_csv(self, json_file, csv_file):
        """Convert JSON to CSV."""
        with open(json_file) as f:
            data = json.load(f)
        df = pd.DataFrame(data)
        df.to_csv(csv_file, index_label='t')

    def _load_timeseries_data(self):
        """Load timeseries data from file."""
        filename = 'heat_demand_20230402'
        self._json_to_csv(f'{self.PATH_IN_PP}demands/{filename}.json', f'{self.PATH_IN}demands/{filename}.csv')
        self.timeseries_data = DataPortal()
        self.timeseries_data.load(
            filename=f'{self.PATH_IN}demands/{filename}.csv',
            index='t',
            param='heat_demand'
        )

    
        
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
        self.instance.arc03 = Arc(
            source=self.instance.heat_storage1.heat_out,
            destination=self.instance.heat_grid.heat_in
        )
        self.instance.arc04 = Arc(
            source=self.instance.boiler1.heat_out,
            destination=self.instance.heat_grid.heat_in
        )
        self.instance.arc05 = Arc(
            source=self.instance.ngas_grid.gas_out,
            destination=self.instance.boiler1.gas_in
        )
        self.instance.arc06 = Arc(
            source=self.instance.ngas_grid.gas_out,
            destination=self.instance.chp1.gas_in
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
        #return (self.model.prob[s] * self.model.delta_cost[s] for s in self.model.scenarios)
        return 0
    
    def _conditional_value_at_risk(self, model):
        """Calculate Conditional Value at Risk."""
        # CVaR = VaR + (1 / (1 - RHO)) * quicksum(model.prob[s] * model.eta_s for s in model.scenarios)
        # return CVaR
        return 0



    def _gas_costs(self, model):
            """ Calculate gas costs for CHP and Boiler."""
            gas_costs = (
            quicksum(model.chp1.gas[t] * model.GAS_PRICE * CALORIFIC_VALUE_NGAS for t in model.t) + 
            quicksum(model.boiler1.gas[t] * model.GAS_PRICE * CALORIFIC_VALUE_NGAS for t in model.t)
            )
            return gas_costs
    
    def _maintenance_costs(self, model):
        """Calculate maintenance costs for CHP."""
        maintenance_costs = quicksum(model.chp1.bin[t] * MAINTENANCE_COSTS for t in model.t)
        return maintenance_costs

    def _power_revenue(self, model):
        """Calculate power revenue for CHP."""
        power_revenue = quicksum(model.chp1.power[t] * model.POWER_PRICE for t in model.t)
        return power_revenue
    
    def _heat_revenue(self, model):
        """Calculate heat revenue for CHP and Boiler."""
        heat_revenue = (
        quicksum(model.chp1.heat[t] * model.HEAT_PRICE for t in model.t) +
        quicksum(model.boiler1.heat[t] * model.HEAT_PRICE for t in model.t)
        )
        return heat_revenue
    
    def _chp_revenue(self, model):
        """Calculate CHP revenue."""
        chp_bonus_for_self_consumption = quicksum(model.chp1.power[t] * CHP_BONUS_SELF_CONSUMPTION * SHARE_SELF_CONSUMPTION for t in model.t)
        chp_bonus_for_feed_in = quicksum(model.chp1.power[t] * CHP_BONUS * SHARE_FEED_IN for t in model.t)
        chp_index = quicksum((model.chp1.power[t] - model.chp1.power[t] * SHARE_SELF_CONSUMPTION) * CHP_INDEX_EEX for t in model.t)
        avoided_grid_fees = quicksum((model.chp1.power[t] - model.chp1.power[t] * SHARE_SELF_CONSUMPTION) * AVOIDED_GRID_FEES for t in model.t)
        energy_tax_refund = quicksum(model.chp1.gas[t] * CALORIFIC_VALUE_NGAS * ENERGY_TAX_REFUND_GAS for t in model.t)
        
        chp_revenue = (
            chp_bonus_for_self_consumption +
            chp_bonus_for_feed_in +
            chp_index +
            avoided_grid_fees +
            energy_tax_refund
        )
        return chp_revenue

    def _calculate_delta_heat_demand(self):
        """Calculate the difference between the heat demand and the heat demand scenario."""

        # Load the heat demand data
        with open(f'{self.PATH_IN_PP}demands/heat_demand_20230402.json') as f:
            heat_demand_data = json.load(f)
        
        with open(f'{self.PATH_IN_PP}demands/heat_demand_scenarios_20230402.json') as f:
            heat_demand_scenarios = json.load(f)

        # Day Ahead demand
        heat_demand = heat_demand_data['heat_demand']

        # Initialize the delta heat demand dictionary
        delta_heat_demand = {}

        # Loop over all scenarios

        for scenario, values in heat_demand_scenarios.items():
            delta_heat_demand[scenario] = {}
            for t, value in values.items():
                if t != 'Probability':
                    heat_d = heat_demand[t]
                    delta_heat_demand[scenario][int(t)] = heat_d - value
        
        print(delta_heat_demand)

        return delta_heat_demand

    def _load_stochastic_data(self):
        filename = 'heat_demand_scenarios_20230402' 
        with open(f'{self.PATH_IN_PP}demands/{filename}.json') as f:
            data = json.load(f)

        # # Create a dictionary
        # self.model.heat_demand.pprint()

        heat_demand_scenarios = {}

        for scenario, values in data.items():
            heat_demand_scenarios[scenario] = {
                'Probability': values['Probability']
            }
            for t, value in values.items():
                if t != 'Probability':
                    heat_demand_scenarios[scenario][int(t)] = value

        return heat_demand_scenarios
    
    def _initialize_scenario_parameters(self, heat_demand_scenario, probability, delta_heat_demand_scenario):
        """Initialize scenario parameters."""
        
        print("Initializing scenario parameters...")
        
        def heat_demand_init(m, t):
            if t in heat_demand_scenario:
                # print("heat_demand_scenario[t]: ", heat_demand_scenario[t])
                return heat_demand_scenario[t]
            else:
                raise KeyError(f"Key {t} not found in scenario")
        
        # Initialize heat demand scenario
        self.model.heat_demand_scenario = Param(self.model.t, initialize=heat_demand_init, mutable=True)

        def delta_heat_demand_init(m, t):
            if t in delta_heat_demand_scenario:
                return delta_heat_demand_scenario[t]
            else:
                raise KeyError(f"Key {t} not found in delta heat demand scenario")
       
       # Initialize delta heat demand scenario
        self.model.delta_heat_demand_scenario = Param(self.model.t, initialize=delta_heat_demand_init, mutable=True)

        # Initialize probability
        self.model.probability = Param(initialize=probability)


    def _build_scenario_model(self, scenario_name):
        """Build the scenario model. Each scenario has a different heat demand and its own model."""
        # Load timeseries data
        print("Building scenario model...")

        # Load the dictionary with the heat demand scenarios
        heat_demand_scenarios = self._load_stochastic_data() 

        scenario_key = f"{scenario_name}"

        if scenario_key in heat_demand_scenarios:
            scenario_data = heat_demand_scenarios[scenario_key]
            probability = scenario_data.pop('Probability',0)
            # print("Probability: ", probability)
            heat_demand_scenario = scenario_data
        else:
            raise RuntimeError(f"Scenario {scenario_key} not found in heat demand scenarios")

        #print(self.model.heat_demand[t] for t in self.model.t)
        #print(f"Heat demand scenario for {scenario_key}: {heat_demand_scenario}")
        
        
        # Load the dictionary with delta heat demand 
        delta_heat_demand = self._calculate_delta_heat_demand()
        
        if scenario_key in delta_heat_demand:
            delta_heat_demand_scenario = delta_heat_demand[scenario_key]
        else:
            raise RuntimeError(f"Scenario {scenario_key} not found in delta heat demand scenarios")
        
        self._load_timeseries_data()
      

        # Initialize scenario parameters
        self._initialize_scenario_parameters(heat_demand_scenario, probability, delta_heat_demand_scenario)
        
        # self._define_assets()
        # self._define_expressions()
        
        ###################### Start Debugging Print ######################

        # output_filename = f'output_model_{scenario_name}.txt'

        # with open(output_filename, 'w') as f:
        #     self.model.pprint(ostream=f)

        ###################### End Debugging Print ######################

        # Create a concrete instance of the model
        print("Creating instance...")
        self.instance = self.model.create_instance(self.timeseries_data)
        
        # Add Arcs to the model
        self._add_arcs()

        # Expand arcs and generate connection constraints
        self._expand_arcs()

        return self.instance
    



    # Not needed for now
    def set_solver(self, solver_name, **kwargs):
        """Set solver for the model."""
        self.solver = SolverFactory(solver_name)
        for key in kwargs:
            self.solver.options[key] = kwargs[key]    
    
    def add_objective(self):
        """Add objective function to model."""
        def objective_expression_rule(model):
            return model.first_stage_cost + model.second_stage_cost
        self.model.objective = Objective(rule=objective_expression_rule,sense=maximize)  

    
    def _scenario_creator(self, scenario_name):
        """Create a scenario model."""
        print("Creating scenario: ", scenario_name)
        self.instance = self._build_scenario_model(scenario_name)
        
        # Variable mit Index t anlegen
        varlist = [self.instance.chp1.gas]
        print("Attaching scenario tree node...")
        sputils.attach_root_node(self.instance, self.instance.first_stage_cost, varlist)

        # Add Probability to the instance
        #self.instance._mpisppy_probability = 1.0

        
        ###################### Start Debugging Print ######################

        output_filename = f'output_{scenario_name}.txt'

        print(f"Writing instance {output_filename} ...")
        with open(output_filename, 'w') as f:
            self.instance.pprint(ostream=f)

        for t in self.instance.t:
            print(f"Time {t}: {pyo.value(self.instance.heat_demand_scenario[t])}")

        with open('constraints_output.txt', 'w') as f:
            # Iteriere über alle aktiven Constraints in der Modellinstanz
            for con in self.instance.component_objects(Constraint, active=True):
                # Schreibe den Namen der Constraint-Komponente in die Datei
                f.write(f"Constraint: {con.name}\n")
                f.write("Details:\n")
                # Nutze pprint, um die Details der Constraint in die Datei zu schreiben
                con.pprint(ostream=f)
                f.write("____________________________________\n")

        ###################### End Debugging Print ######################

        return self.instance

       
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


    def write_results(self, ef):
        """Write results to file."""

        solution = self.ef_instance.get_root_solution()
        for [var_name, var_val] in solution.items():
            print(var_name, var_val)

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
            
            # Save results to file
            output_file = f'{sname}_results.csv'
            df_output.to_csv(self.PATH_OUT_TIMESERIES + output_file)
            #print(f'Results for {sname} written to {output_file}')
            
    
    def write_objective_values(self, ef):
        """Writes he Objective-Value for each scenario."""
        results = []

        
        for sname, smodel in sputils.ef_scenarios(ef):
            objective_value = pyo.value(smodel.objective)
            results.append({'Scenario:': sname, 'ObjectiveValue': objective_value})

        # Creates a DataFrame from the results list
        df_results = pd.DataFrame(results)

        if not os.path.exists(self.PATH_OUT_OBJECTIVES):
            os.makedirs(self.PATH_OUT_OBJECTIVES)

        # Speichere den DataFrame als CSV-Datei
        output_filename = f"{self.PATH_OUT_OBJECTIVES}scenario_objectives.csv"
        df_results.to_csv(output_filename, index=False)