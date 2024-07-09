import pandas as pd

from pyomo.environ import *
from pyomo.network import *

class Boiler:
    """Boiler class"""

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
        # ...
        
