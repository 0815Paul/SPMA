import pandas as pd

from pyomo.environ import *
from pyomo.network import *

class Boiler:
    """Boiler class"""

    def __init__(self, name, filepath, index_col=0, **kwargs):
        self.name = name
        self.get_data(filepath, index_col)
        # leave **kwargs for future use

    def get_data(self, filepath, index_col):
        self.data = pd.read_csv(
            filepath,
            index_col=index_col
        )
    
    def add_to_model(self, model):
        model.add_component(
            self.name,
            Block(rule=self.boiler_block_rule)
        )

    def boiler_block_rule(self, asset):

        # Get index from model
        t = asset.model().t

        # Declare components
        asset.bin = Var(t, within=Binary)
        asset.heat = Var(t, domain=NonNegativeReals)
        asset.gas = Var(t, domain=NonNegativeReals)
        asset.eta_th = Var(t, domain=NonNegativeReals)

       # Binary variable for Big-M constraints
        asset.y1 = Var(t, domain=Binary)
        asset.y2 = Var(t, domain=Binary)

        asset.heat_out = Port()
        asset.heat_out.add(
            asset.heat,
            'heat',
            Port.Extensive,
            include_splitfrac=False
        )

        asset.gas_in = Port()
        asset.gas_in.add(
            asset.gas,
            'gas',
            Port.Extensive,
            include_splitfrac=False
        )

        boiler_op_data = self.data

        # Heat
        heat_1 = boiler_op_data.loc[1, 'heat']
        heat_2 = boiler_op_data.loc[2, 'heat']
        heat_3 = boiler_op_data.loc[3, 'heat']

        # eta_th
        eta_th_1 = boiler_op_data.loc[1, 'eta_th']
        eta_th_2 = boiler_op_data.loc[2, 'eta_th']
        eta_th_3 = boiler_op_data.loc[3, 'eta_th']

        # Gas
        gas_1 = heat_1 / eta_th_1
        gas_2 = heat_2 / eta_th_2
        gas_3 = heat_3 / eta_th_3

        print("Gas Boiler :", gas_1, gas_2, gas_3)
        print("Heat Boiler:", heat_1, heat_2, heat_3)
        print("eta_th Boiler:", eta_th_1, eta_th_2, eta_th_3)

        # Constraints

        def thermal_load_max_rule(asset, t):
            """Maximum heat production constraint"""
            return asset.heat[t] <= heat_3*asset.bin[t]
        asset.max_heat_constr = Constraint(t, rule=thermal_load_max_rule)

        def thermal_load_min_rule(asset, t):
            """Minimum heat production constraint"""
            return heat_1*asset.bin[t] <= asset.heat[t]
        asset.min_heat_constr = Constraint(t, rule=thermal_load_min_rule)


        # Helper function
        def linear_function(x, x1, x2, y1, y2):
            """Helper function for linear interpolation."""
            a = (y2 - y1) / (x2 - x1)
            b = y1 - a * x1
            return a * x + b 
        
        # Big-M
        M = 1e6

        # ______ For testing purposes ______

        # def y_constraint2(asset, t):
        #     pass
        #     return asset.y2[t] == 1
        # asset.y_constraint2 = Constraint(t, rule=y_constraint2)

        # __________________________________


        def y_constraint1_upper(asset, t):
            """Big-M constraint 1 - upper bound"""
            return asset.y1[t] + asset.y2[t] == asset.bin[t]
        asset.y_constr1_upper = Constraint(t, rule=y_constraint1_upper)

    
        # Big-M constraints for gas consumption depending on the thermal load

        def gas_depends_on_thermal_load_rule2(asset, t):
            return asset.heat[t] <= heat_2 *asset.y1[t]
        asset.gas_depends_on_thermal_load2 = Constraint(t, rule=gas_depends_on_thermal_load_rule2)

        def gas_depends_on_thermal_load_rule3(asset, t):
            return asset.heat[t] >= heat_2 * asset.y2[t]
        asset.gas_depends_on_thermal_load3 = Constraint(t, rule=gas_depends_on_thermal_load_rule3)
       

        # Upper bound
        def gas_depends_on_thermal_load_constr1(asset, t):
            return asset.gas[t] <= (linear_function(asset.heat[t], heat_1, heat_2, gas_1, gas_2)+ M * (1 - asset.y1[t])) *asset.bin[t]
        asset.gas_depends_on_thermal_load_constr1 = Constraint(t, rule=gas_depends_on_thermal_load_constr1)

        def gas_depends_on_thermal_load_constr2(asset, t):
            return asset.gas[t] <= (linear_function(asset.heat[t], heat_2, heat_3, gas_2, gas_3) + M * (1 - asset.y2[t]))*asset.bin[t]
        asset.gas_depends_on_thermal_constr2 = Constraint(t, rule=gas_depends_on_thermal_load_constr2)
        
        #Lower bound
        def gas_depends_on_thermal_load_constr1_lower(asset, t):
            return asset.gas[t] >= (linear_function(asset.heat[t], heat_1, heat_2, gas_1, gas_2)- M * (1 - asset.y1[t]))*asset.bin[t]
        asset.gas_depends_on_thermal_load1_lower = Constraint(t, rule=gas_depends_on_thermal_load_constr1_lower)

        def gas_depends_on_thermal_load_constr2_lower(asset, t):
            return asset.gas[t] >= (linear_function(asset.heat[t], heat_2, heat_3, gas_2, gas_3) - M * (1 - asset.y2[t]))*asset.bin[t]
        asset.gas_depends_on_thermal_load2_lower = Constraint(t, rule=gas_depends_on_thermal_load_constr2_lower)

        # Big M constraints for thermal efficiency depending on the thermal load
        
        # Upper bound
        def thermal_efficiency_depends_on_thermal_load_constr1(asset, t):
            return asset.eta_th[t] <= (linear_function(asset.heat[t], heat_1, heat_2, eta_th_1, eta_th_2)  + M * (1 - asset.y1[t]))* asset.bin[t]
        asset.thermal_efficiency_depends_on_thermal_load1 = Constraint(t, rule=thermal_efficiency_depends_on_thermal_load_constr1)
       
        def thermal_efficiency_depends_on_thermal_load_constr2(asset, t):
            return asset.eta_th[t] <= (linear_function(asset.heat[t], heat_2, heat_3, eta_th_2, eta_th_3) + M * (1 - asset.y2[t]))* asset.bin[t]
        asset.thermal_efficiency_depends_on_thermal_load2 = Constraint(t, rule=thermal_efficiency_depends_on_thermal_load_constr2)

        # Lower Bound 

        def thermal_efficiency_depends_on_thermal_load_constr1_lower(asset, t):
            return asset.eta_th[t] >= (linear_function(asset.heat[t], heat_1, heat_2, eta_th_1, eta_th_2)- M * (1 - asset.y1[t])) * asset.bin[t]
        asset.thermal_efficiency_depends_on_thermal_load1_lower = Constraint(t, rule=thermal_efficiency_depends_on_thermal_load_constr1_lower)

        def thermal_efficiency_depends_on_thermal_load_constr2_lower(asset, t):
            return asset.eta_th[t] >= (linear_function(asset.heat[t], heat_2, heat_3, eta_th_2, eta_th_3) - M * (1 - asset.y2[t]))* asset.bin[t]
        asset.thermal_efficiency_depends_on_thermal_load2_lower = Constraint(t, rule=thermal_efficiency_depends_on_thermal_load_constr2_lower)
        
       
