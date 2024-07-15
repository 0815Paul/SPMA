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
        asset.heat = Var(t, within=NonNegativeReals)
        asset.gas = Var(t, within=NonNegativeReals)

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

        # Declare construction rules for components
        
        def max_heat_rule(asset, t):
            """Maximum heat production constraint"""
            return asset.heat[t] <= self.data.loc['max', 'heat']*asset.bin[t]
        asset.max_heat_constr = Constraint(t, rule=max_heat_rule)

        def min_heat_rule(asset, t):
            """Minimum heat production constraint"""
            return self.data.loc['min', 'heat']*asset.bin[t] <= asset.heat[t]
        asset.min_heat_constr = Constraint(t, rule=min_heat_rule)

        def gas_depends_on_heat_rule(asset, t):
            """Gas consumption depends on heat production"""
            return asset.gas[t] == asset.heat[t] * self.data.loc['efficiency', 'heat'] # fehlt hier noch *asset.bin[t]?
        asset.gas_depends_on_heat_constr = Constraint(t, rule=gas_depends_on_heat_rule)        
