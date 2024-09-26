import pandas as pd

from pyomo.environ import *
from pyomo.network import *

class Chp:
    """Combined Heat and Power Plant (CHP) class"""

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
            Block(rule=self.chp_block_rule)
        )
    
    def chp_block_rule(self, asset):

        # Get index fom model
        t = asset.model().t

        # Declare components
        asset.bin = Var(t, within=Binary)
        asset.power = Var(t, domain=NonNegativeReals)
        asset.gas = Var(t, domain=NonNegativeReals)
        asset.heat = Var(t, domain=NonNegativeReals)
        asset.eta_th = Var(t, domain=NonNegativeReals)
        asset.eta_el = Var(t, domain=NonNegativeReals)
        
        # Binary variable for Big-M constraints
        asset.y1 = Var(t, domain=Binary)
        asset.y2 = Var(t, domain=Binary)

        asset.power_out = Port()
        asset.power_out.add(
            asset.power,
            'power',
            Port.Extensive,
            include_splitfrac=False
        )

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
        

        chp_op_data = self.data

        # Heat
        heat_1 = chp_op_data.loc[1, 'heat']
        heat_2 = chp_op_data.loc[2, 'heat']
        heat_3 = chp_op_data.loc[3, 'heat']

        # eta_th
        eta_th_1 = chp_op_data.loc[1, 'eta_th']
        eta_th_2 = chp_op_data.loc[2, 'eta_th']
        eta_th_3 = chp_op_data.loc[3, 'eta_th']

        # eta_el
        eta_el_1 = chp_op_data.loc[1, 'eta_el']
        eta_el_2 = chp_op_data.loc[2, 'eta_el']
        eta_el_3 = chp_op_data.loc[3, 'eta_el']

        # Power 
        power_1 = eta_el_1 * (heat_1/eta_th_1)
        power_2 = eta_el_2 * (heat_2/eta_th_2)
        power_3 = eta_el_3 * (heat_3/eta_th_3)
            
        # Gas 
        gas_1 = heat_1/eta_th_1
        gas_2 = heat_2/eta_th_2
        gas_3 = heat_3/eta_th_3

        # print("Gas CHP :", gas_1, gas_2, gas_3)
        # print("Power CHP:", power_1, power_2, power_3)
        # print("Heat CHP:", heat_1, heat_2, heat_3)

        # Constraints

        def thermal_load_max_rule(asset, t):
            """Rule for the maximum thermal load."""
            thermal_load_max = chp_op_data.loc[3, 'heat']
            return asset.heat[t] <= thermal_load_max * asset.bin[t]
        asset.thermal_load_max_constr = Constraint(t, rule=thermal_load_max_rule)
    
        def thermal_load_min_rule(asset, t):
            """Rule for the minimum thermal load."""
            thermal_load_min = chp_op_data.loc[1, 'heat']
            return thermal_load_min * asset.bin[t] <= asset.heat[t]
        asset.thermal_load_min_constr = Constraint(t, rule=thermal_load_min_rule)

        def linear_function(x, x1, x2, y1, y2):
            """Helper function for linear interpolation."""
            a = (y2 - y1) / (x2 - x1)
            b = y1 - a * x1
            return a * x + b
            
        
        # Big-M Parameter
        M = 1e5

        def y_activation_constraint(asset, t):
            """Ensures that y1 and y2 sum up to bin"""
            return asset.y1[t] + asset.y2[t] == asset.bin[t]
        asset.y_activation_constr = Constraint(t, rule=y_activation_constraint)

        # Constraints for heat depending on y1 and y2
        def heat_upper_bound_y1_constraint(asset, t):
            """Upper bound on heat when y1 is active"""
            return asset.heat[t] <= heat_2 * asset.y1[t]
        asset.heat_upper_bound_y1_constr = Constraint(t, rule=heat_upper_bound_y1_constraint)

        def heat_lower_bound_y2_constraint(asset, t):
            """Lower bound on heat when y2 is active"""
            return asset.heat[t] >= heat_2 * asset.y2[t]
        asset.heat_lower_bound_y2_constr = Constraint(t, rule=heat_lower_bound_y2_constraint)

        # Constraints for power depending on thermal load

        # Upper bounds
        def power_upper_bound_y1_constraint(asset, t):
            """Upper bound on power in region 1"""
            return asset.power[t] <= (linear_function(asset.heat[t], heat_1, heat_2, power_1, power_2) + M * (1 - asset.y1[t])) * asset.bin[t]
        asset.power_upper_bound_y1_constr = Constraint(t, rule=power_upper_bound_y1_constraint)

        def power_upper_bound_y2_constraint(asset, t):
            """Upper bound on power in region 2"""
            return asset.power[t] <= (linear_function(asset.heat[t], heat_2, heat_3, power_2, power_3) + M * (1 - asset.y2[t])) * asset.bin[t]
        asset.power_upper_bound_y2_constr = Constraint(t, rule=power_upper_bound_y2_constraint)

        # Lower bounds
        def power_lower_bound_y1_constraint(asset, t):
            """Lower bound on power in region 1"""
            return asset.power[t] >= (linear_function(asset.heat[t], heat_1, heat_2, power_1, power_2) - M * (1 - asset.y1[t])) * asset.bin[t]
        asset.power_lower_bound_y1_constr = Constraint(t, rule=power_lower_bound_y1_constraint)

        def power_lower_bound_y2_constraint(asset, t):
            """Lower bound on power in region 2"""
            return asset.power[t] >= (linear_function(asset.heat[t], heat_2, heat_3, power_2, power_3) - M * (1 - asset.y2[t])) * asset.bin[t]
        asset.power_lower_bound_y2_constr = Constraint(t, rule=power_lower_bound_y2_constraint)

        # Constraints for gas depending on thermal load

        # Upper bounds
        def gas_upper_bound_y1_constraint(asset, t):
            """Upper bound on gas consumption in region 1"""
            return asset.gas[t] <= (linear_function(asset.heat[t], heat_1, heat_2, gas_1, gas_2) + M * (1 - asset.y1[t])) * asset.bin[t]
        asset.gas_upper_bound_y1_constr = Constraint(t, rule=gas_upper_bound_y1_constraint)

        def gas_upper_bound_y2_constraint(asset, t):
            """Upper bound on gas consumption in region 2"""
            return asset.gas[t] <= (linear_function(asset.heat[t], heat_2, heat_3, gas_2, gas_3) + M * (1 - asset.y2[t])) * asset.bin[t]
        asset.gas_upper_bound_y2_constr = Constraint(t, rule=gas_upper_bound_y2_constraint)

        # Lower bounds
        def gas_lower_bound_y1_constraint(asset, t):
            """Lower bound on gas consumption in region 1"""
            return asset.gas[t] >= (linear_function(asset.heat[t], heat_1, heat_2, gas_1, gas_2) - M * (1 - asset.y1[t])) * asset.bin[t]
        asset.gas_lower_bound_y1_constr = Constraint(t, rule=gas_lower_bound_y1_constraint)

        def gas_lower_bound_y2_constraint(asset, t):
            """Lower bound on gas consumption in region 2"""
            return asset.gas[t] >= (linear_function(asset.heat[t], heat_2, heat_3, gas_2, gas_3) - M * (1 - asset.y2[t])) * asset.bin[t]
        asset.gas_lower_bound_y2_constr = Constraint(t, rule=gas_lower_bound_y2_constraint)

        # Constraints for thermal efficiency depending on thermal load

        # Upper bounds
        def eta_th_upper_bound_y1_constraint(asset, t):
            """Upper bound on thermal efficiency in region 1"""
            return asset.eta_th[t] <= (linear_function(asset.heat[t], heat_1, heat_2, eta_th_1, eta_th_2) + M * (1 - asset.y1[t])) * asset.bin[t]
        asset.eta_th_upper_bound_y1_constr = Constraint(t, rule=eta_th_upper_bound_y1_constraint)

        def eta_th_upper_bound_y2_constraint(asset, t):
            """Upper bound on thermal efficiency in region 2"""
            return asset.eta_th[t] <= (linear_function(asset.heat[t], heat_2, heat_3, eta_th_2, eta_th_3) + M * (1 - asset.y2[t])) * asset.bin[t]
        asset.eta_th_upper_bound_y2_constr = Constraint(t, rule=eta_th_upper_bound_y2_constraint)

        # Lower bounds
        def eta_th_lower_bound_y1_constraint(asset, t):
            """Lower bound on thermal efficiency in region 1"""
            return asset.eta_th[t] >= (linear_function(asset.heat[t], heat_1, heat_2, eta_th_1, eta_th_2) - M * (1 - asset.y1[t])) * asset.bin[t]
        asset.eta_th_lower_bound_y1_constr = Constraint(t, rule=eta_th_lower_bound_y1_constraint)

        def eta_th_lower_bound_y2_constraint(asset, t):
            """Lower bound on thermal efficiency in region 2"""
            return asset.eta_th[t] >= (linear_function(asset.heat[t], heat_2, heat_3, eta_th_2, eta_th_3) - M * (1 - asset.y2[t])) * asset.bin[t]
        asset.eta_th_lower_bound_y2_constr = Constraint(t, rule=eta_th_lower_bound_y2_constraint)

        # Constraints for electrical efficiency depending on thermal load

        # Upper bounds
        def eta_el_upper_bound_y1_constraint(asset, t):
            """Upper bound on electrical efficiency in region 1"""
            return asset.eta_el[t] <= (linear_function(asset.heat[t], heat_1, heat_2, eta_el_1, eta_el_2) + M * (1 - asset.y1[t])) * asset.bin[t]
        asset.eta_el_upper_bound_y1_constr = Constraint(t, rule=eta_el_upper_bound_y1_constraint)

        def eta_el_upper_bound_y2_constraint(asset, t):
            """Upper bound on electrical efficiency in region 2"""
            return asset.eta_el[t] <= (linear_function(asset.heat[t], heat_2, heat_3, eta_el_2, eta_el_3) + M * (1 - asset.y2[t])) * asset.bin[t]
        asset.eta_el_upper_bound_y2_constr = Constraint(t, rule=eta_el_upper_bound_y2_constraint)

        # Lower bounds
        def eta_el_lower_bound_y1_constraint(asset, t):
            """Lower bound on electrical efficiency in region 1"""
            return asset.eta_el[t] >= (linear_function(asset.heat[t], heat_1, heat_2, eta_el_1, eta_el_2) - M * (1 - asset.y1[t])) * asset.bin[t]
        asset.eta_el_lower_bound_y1_constr = Constraint(t, rule=eta_el_lower_bound_y1_constraint)

        def eta_el_lower_bound_y2_constraint(asset, t):
            """Lower bound on electrical efficiency in region 2"""
            return asset.eta_el[t] >= (linear_function(asset.heat[t], heat_2, heat_3, eta_el_2, eta_el_3) - M * (1 - asset.y2[t])) * asset.bin[t]
        asset.eta_el_lower_bound_y2_constr = Constraint(t, rule=eta_el_lower_bound_y2_constraint)


        



        