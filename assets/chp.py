import pandas as pd

from pyomo.environ import *
from pyomo.network import *

class Chp:
    """Combined Heat and Power Plant (CHP) class"""

    def __init__(self, name, filepath, index_col=0, **kwargs):
        self.name = name
        self.get_data = (filepath, index_col)
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
        asset.power = Var(t, within=NonNegativeReals)
        asset.heat = Var(t, within=NonNegativeReals)
        asset.gas = Var(t, within=NonNegativeReals)

        asset.power_out = Port()
        asset.power_out_add(
            asset.power,
            'power',
            Port.Extensive,
            include_splitfrac=True
        )

        asset.heat_out = Port()
        asset.heat_out_add(
            asset.heat,
            'heat',
            Port.Extensive,
            include_splitfrac=True
        )

        asset.natural_gas_in = Port()
        asset.natural_gas_in_add(
            asset.gas,
            'gas',
            Port.Extensive,
            include_splitfrac=True
        )

        # Declare construction rules for components
        def power_max_rule(asset, t):
            """ Rule for maximum power output of CHP """
            return asset.power[t] <= self.data.loc['max', 'power'] * asset.bin[t]
        asset.power_max_constr = Constraint(t, rule=power_max_rule)


        def power_in_rule(asset, t):
            """ Rule for power input of CHP """
            return self.data.loc['min', 'power'] * asset.bin[t] <= asset.power[t]
        asset.power_in_constr = Constraint(t, rule=power_in_rule)


        def power_depends_on_heat_rule(asset, t):
            """ Rule for gas consumption depending on heat output (gas = a*heat + b*bin)"""
            heat_max = self.data.loc['max', 'gas']
            heat_min = self.data.loc['min', 'gas']
            power_max = self.data.loc['max', 'heat']
            power_min = self.data.loc['min', 'heat']
            
            a = (power_max - power_min)/(heat_max - heat_min)
            b = power_min - a*heat_min

            return asset.power[t] == a*asset.heat[t] + b*asset.bin[t]
        asset.power_depends_on_heat_constr = Constraint(t, rule=power_depends_on_heat_rule)


        def gas_depends_on_heat_rule(asset, t):
            """ Rule for gas consumption depending on heat output (gas = a*heat + b*bin)"""
            heat_max = self.data.loc['max', 'gas']
            heat_min = self.data.loc['min', 'gas']
            gas_max = self.data.loc['max', 'heat']
            gas_min = self.data.loc['min', 'heat']
            
            a = (gas_max - gas_min)/(heat_max - heat_min)
            b = gas_min - a*heat_min

            return asset.gas[t] == a*asset.heat[t] + b*asset.bin[t]
        asset.gas_depends_on_heat_constr = Constraint(t, rule=gas_depends_on_heat_rule)
