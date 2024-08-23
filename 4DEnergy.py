import pandas as pd

from pyomo.opt import SolverFactory
from pyomo.environ import *
from pyomo.network import *

import assets.chp as chp
import assets.boiler as boiler
import assets.heat_storage as heat_storage
import assets.grid as grid


# Path
PATH_IN = 'data/input/'
PATH_OUT = 'data/output/'

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
        self.model = AbstractModel()
        self.instance = None
        self.solver = None
        self.timeseries_data = None
        self.results = None
        self.results_data = None

    def set_solver(self, solver_name, **kwargs):
        self.solver = SolverFactory(solver_name)
        
        for key in kwargs:
            self.solver.options[key] = kwargs[key]
    
    def load_timeseries_data(self):
        """Load timeseries data from file."""
        self.timeseries_data = DataPortal()

        self.timeseries_data.load(
            filename=PATH_IN + '/demands/heat_demand_20230401.csv',
            index='t',
            param='heat_demand'
        )

        #_____ In case of power price is not constant _____#

        # self.timeseries_data.load(
        #     filename=PATH_IN + '/prices/power_price.csv',
        #     index='t',
        #     param='power_price'
        # )

        #_________________________________________________#

        #_____ In case of heat price is not constant _____#

        # self.timeseries_data.load(
        #     filename=PATH_IN + '/prices/heat_price.csv',
        #     index='t',
        #     param='heat_price'
        # )

        #_________________________________________________#

        #_____ In case of gas price is not constant _____#
    
        # self.timeseries_data.load(
        #     filename=PATH_IN + '/prices/gas_price.csv',
        #     index='t',
        #     param='gas_price'
        # )

        #_________________________________________________#


    def add_components(self):
        """Add components to the model."""

        # Sets
        self.model.t = Set(ordered=True)

        # Parameters
        self.model.GAS_PRICE = Param(initialize=GAS_PRICE)
        self.model.POWER_PRICE = Param(initialize=POWER_PRICE)
        self.model.HEAT_PRICE = Param(initialize=HEAT_PRICE)
        self.model.heat_demand = Param(self.model.t)

        #_____ In case of power price is not constant _____#
        
        #self.model.power_price = Param(self.model.t)

        #_________________________________________________#
        
        #_____ In case of heat price is not constant _____#

        #self.model.heat_price = Param(self.model.t)

        #_________________________________________________#

        #_____ In case of gas price is not constant _____#

        #self.model.gas_price = Param(self.model.t)

        #_________________________________________________#

        # Assets

        chp_filepaths = [
            PATH_IN + '/assets/chp.csv',
            PATH_IN + '/assets/chp_operation.csv'
        ]

        boiler_filepaths = [
            PATH_IN + '/assets/boiler.csv',
            PATH_IN + '/assets/boiler_operation.csv'
        ]

        chp1 = chp.Chp(
            'chp1', chp_filepaths
        )


        # chp1 = chp.Chp(
        #     'chp1', PATH_IN + '/assets/chp.csv'
        # )

        boiler1 = boiler.Boiler(
            'boiler1', boiler_filepaths
        )

        #boiler1 = boiler.Boiler(
        #    'boiler1', PATH_IN + '/assets/boiler.csv'
        #)

        heat_storage1 = heat_storage.HeatStorage(
            'heat_storage1', PATH_IN + '/assets/heat_storage.csv'
        )

        ngas_grid = grid.NGasGrid('ngas_grid')

        power_grid = grid.ElectricalGrid(
            'power_grid', PATH_IN + '/assets/power_grid.csv'
        )

        heat_grid = grid.HeatGrid(
            'heat_grid', PATH_IN + '/assets/heat_grid.csv'
        )

        chp1.add_to_model(self.model)
        boiler1.add_to_model(self.model)
        heat_storage1.add_to_model(self.model)
        ngas_grid.add_to_model(self.model)
        power_grid.add_to_model(self.model)
        heat_grid.add_to_model(self.model)


    def add_objective(self):
        """Add objective function to model."""
        self.model.objective = Objective(
            rule=self.objective_expr,
            sense=minimize
        )
    
    def instantiate_model(self):
        """Create a concrete instance of the model."""
        self.instance = self.model.create_instance(self.timeseries_data)
        with open('output.txt', 'w') as f:
            self.instance.pprint(ostream=f)

    
    def expand_arcs(self):
        """Expands arcs and generate connection constraints."""
        TransformationFactory('network.expand_arcs').apply_to(self.instance)
    
    def add_instance_components(self, component_name, component):
        """Add components to the instance."""
        self.instance.add_component(component_name, component)

    def add_arcs(self):
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

    def solve(self):
        """Solve the model."""
        self.results =self.solver.solve(
            self.instance,
            symbolic_solver_labels=True,
            tee=True,
            logfile=PATH_OUT + 'logfile.txt',
            load_solutions=True,
            report_timing=True,
        )
    
    def write_results(self):
        """Write results to file."""
        self.results.write()

        df_params = pd.DataFrame()
        df_variables = pd.DataFrame()
        df_output = pd.DataFrame()

        for params in self.instance.component_objects(Param, active=True):
            name = params.name
            if len(params) == 1:
                single_value = value(list(params.values())[0])
                df_params[name]= [single_value for t in self.instance.t]
            else:                        
                df_params[name] = [value(params[t]) for t in self.instance.t]
        
        for variables in self.instance.component_objects(Var, active=True):
            name = variables.name
            df_variables[name] = [value(variables[t]) for t in self.instance.t]

        df_output = pd.concat([df_params, df_variables], axis=1)
        df_output.index = self.instance.t
        df_output.index.name = 't'

        self.results_data = df_output


    def save_results(self, filepath):
        """Save results to object."""
        self.results_data.to_csv(filepath)

    def objective_expr(self, model):
        """Objective function expression."""
        objective_expr = (
            self._gas_costs(model) +
            self._maintenance_costs(model) -
            self._power_revenue(model) -
            self._heat_revenue(model) -
            self._chp_revenue(model)
        )
        return objective_expr

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

if __name__ == "__main__":
    model = Model()

    print('Setting solver...')
    model.set_solver(
        solver_name= 'gurobi',
        MIPGap=0.015,
        TimeLimit=30
        )

    print('Loading timeseries data...')
    model.load_timeseries_data()

    print('Adding components...')
    model.add_components()

    print('Adding objective...')
    model.add_objective()

    print('Instantiating model...')
    model.instantiate_model()

    print('Declairing arcs...')
    model.add_arcs()
    model.expand_arcs()

    print('Solving model...')
    model.solve()
    
    print('Writing results...')
    model.write_results()
    model.save_results(PATH_OUT + 'results.csv')
    